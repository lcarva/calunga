"""Tests for the generate command."""

import subprocess
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import typer
from typer.testing import CliRunner

from calunga.cli import app
from calunga.commands.generate import (
    load_additional_requirements,
    find_packages,
    generate_package_wrapper,
    generate_konflux_resources,
    generate_pac_resources,
    update_all_kustomization,
    compile_requirements,
    compile_build_requirements,
)


runner = CliRunner()


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with basic structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)

        # Create packages directory
        packages_dir = workspace / "packages"
        packages_dir.mkdir()

        # Create test packages
        test_packages = ["test-pkg-1", "test-pkg-2", "existing-pkg"]
        for pkg_name in test_packages:
            pkg_dir = packages_dir / pkg_name
            pkg_dir.mkdir()

        # Create additional-requirements.yaml
        additional_requirements = {
            "packages": {
                "test-pkg-1": {
                    "requirements_in": ["setuptools"],
                    "package_name": "test_pkg_1"
                },
                "existing-pkg": {
                    "requirements_in": ["wheel", "setuptools"]
                }
            }
        }

        with open(packages_dir / "additional-requirements.yaml", "w") as f:
            yaml.dump(additional_requirements, f)

        # Create existing file in one package to test skip behavior
        existing_pkg_dir = packages_dir / "existing-pkg"
        with open(existing_pkg_dir / "pyproject.toml", "w") as f:
            f.write('[project]\nname = "existing-pkg"\nversion = "1.0.0"\n')

        # Create konflux base directory
        konflux_dir = workspace / "konflux" / "components"
        konflux_dir.mkdir(parents=True)

        base_dir = konflux_dir / "base"
        base_dir.mkdir()

        # Create base kustomization template
        with open(base_dir / "pkg-kustomization.yaml", "w") as f:
            f.write("""---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../base
patches:
  - target:
      kind: Component
      name: .*
    path: set-resource-name.yaml
""")

        # Create .tekton directory with templates
        tekton_dir = workspace / ".tekton"
        tekton_dir.mkdir()

        with open(tekton_dir / "on-push.yaml.template", "w") as f:
            f.write("""---
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${name}-on-push
spec:
  params:
  - name: dockerfile
    value: ${containerfile}
""")

        with open(tekton_dir / "on-pull-request.yaml.template", "w") as f:
            f.write("""---
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${name}-on-pr
spec:
  params:
  - name: dockerfile
    value: ${containerfile}
""")

        yield workspace


def test_load_additional_requirements(temp_workspace):
    """Test loading additional requirements from YAML file."""
    requirements = load_additional_requirements(temp_workspace)

    assert "packages" in requirements
    assert "test-pkg-1" in requirements["packages"]
    assert requirements["packages"]["test-pkg-1"]["package_name"] == "test_pkg_1"
    assert "setuptools" in requirements["packages"]["test-pkg-1"]["requirements_in"]


def test_load_additional_requirements_missing_file():
    """Test loading additional requirements when file doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        requirements = load_additional_requirements(Path(temp_dir))
        assert requirements == {}


def test_find_packages(temp_workspace):
    """Test finding packages in the packages directory."""
    packages_dir = temp_workspace / "packages"
    packages = find_packages(packages_dir)

    assert len(packages) == 3
    package_names = [p.name for p in packages]
    assert "test-pkg-1" in package_names
    assert "test-pkg-2" in package_names
    assert "existing-pkg" in package_names


def test_find_packages_missing_directory():
    """Test finding packages when packages directory doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        packages_dir = Path(temp_dir) / "nonexistent"

        with pytest.raises(typer.Exit):
            find_packages(packages_dir)


def test_generate_package_wrapper(temp_workspace):
    """Test generating package wrapper files."""
    additional_requirements = load_additional_requirements(temp_workspace)
    pkg_path = temp_workspace / "packages" / "test-pkg-1"

    # Mock subprocess calls
    with patch('calunga.commands.generate.compile_requirements') as mock_compile:
        mock_compile.return_value = None
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock()
            generate_package_wrapper("test-pkg-1", pkg_path, additional_requirements, temp_workspace)

    # Check that files were created
    assert (pkg_path / "pyproject.toml").exists()
    assert (pkg_path / "requirements.in").exists()

    # Check pyproject.toml content
    with open(pkg_path / "pyproject.toml") as f:
        content = f.read()
        assert "test-pkg-1_placeholder_wrapper" in content

    # Check requirements.in content
    with open(pkg_path / "requirements.in") as f:
        content = f.read()
        assert "test-pkg-1" in content
        assert "setuptools" in content


def test_generate_package_wrapper_skip_existing(temp_workspace):
    """Test that existing files are not overwritten."""
    additional_requirements = load_additional_requirements(temp_workspace)
    pkg_path = temp_workspace / "packages" / "existing-pkg"

    # Read original content
    with open(pkg_path / "pyproject.toml") as f:
        original_content = f.read()

    # Mock compile_requirements and subprocess calls
    with patch('calunga.commands.generate.compile_requirements') as mock_compile:
        mock_compile.return_value = None
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock()
            generate_package_wrapper("existing-pkg", pkg_path, additional_requirements, temp_workspace)

    # Check that existing file was not overwritten
    with open(pkg_path / "pyproject.toml") as f:
        current_content = f.read()
        assert current_content == original_content


def test_compile_requirements_programmatically_success(temp_workspace):
    """Test successful compilation of requirements using pip-tools."""
    # Create test files
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_in = pkg_path / "requirements.in"
    requirements_txt = pkg_path / "requirements.txt"

    # Create requirements.in
    with open(requirements_in, "w") as f:
        f.write("requests\nclick\n")

    # Mock subprocess.run
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()

        compile_requirements(
            requirements_in,
            requirements_txt,
            temp_workspace,
            allow_unsafe=True,
            generate_hashes=True
        )

        mock_run.assert_called_once()
        # Check that the correct arguments were passed
        call_args = mock_run.call_args[0][0]
        assert "piptools" in call_args[2]
        assert "compile" in call_args[3]
        assert "--allow-unsafe" in call_args
        assert "--generate-hashes" in call_args


def test_compile_requirements_programmatically_with_options(temp_workspace):
    """Test compilation with different options."""
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_in = pkg_path / "requirements.in"
    requirements_txt = pkg_path / "requirements.txt"

    with open(requirements_in, "w") as f:
        f.write("requests\n")

    # Mock subprocess.run
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()

        # Test with different options
        compile_requirements(
            requirements_in,
            requirements_txt,
            temp_workspace,
            allow_unsafe=False,
            generate_hashes=False
        )

        mock_run.assert_called_once()
        # Check that the correct arguments were passed
        call_args = mock_run.call_args[0][0]
        assert "piptools" in call_args[2]
        assert "compile" in call_args[3]
        # When False, these options should not be included
        assert "--allow-unsafe" not in call_args
        assert "--generate-hashes" not in call_args


def test_compile_requirements_programmatically_exception(temp_workspace):
    """Test handling of exceptions during compilation."""
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_in = pkg_path / "requirements.in"
    requirements_txt = pkg_path / "requirements.txt"

    with open(requirements_in, "w") as f:
        f.write("invalid-package-name-that-does-not-exist\n")

    # Mock subprocess.run to raise CalledProcessError
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "pip-compile", "Error: Package not found")

        with pytest.raises(subprocess.CalledProcessError):
            compile_requirements(
                requirements_in,
                requirements_txt,
                temp_workspace,
                allow_unsafe=True,
                generate_hashes=True
            )


def test_compile_requirements_programmatically_runtime_exception(temp_workspace):
    """Test handling of runtime exceptions during compilation."""
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_in = pkg_path / "requirements.in"
    requirements_txt = pkg_path / "requirements.txt"

    with open(requirements_in, "w") as f:
        f.write("requests\n")

    # Mock subprocess.run to raise a general exception
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = Exception("Runtime error")

        with pytest.raises(Exception):
            compile_requirements(
                requirements_in,
                requirements_txt,
                temp_workspace,
                allow_unsafe=True,
                generate_hashes=True
            )


def test_compile_requirements_programmatically_directory_change(temp_workspace):
    """Test that directory changes are handled correctly."""
    import os

    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_in = pkg_path / "requirements.in"
    requirements_txt = pkg_path / "requirements.txt"

    with open(requirements_in, "w") as f:
        f.write("requests\n")

    original_cwd = os.getcwd()

    # Mock subprocess.run
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()

        compile_requirements(
            requirements_in,
            requirements_txt,
            temp_workspace,
            allow_unsafe=True,
            generate_hashes=True
        )

        mock_run.assert_called_once()
        # Check that subprocess.run was called with the correct keyword arguments
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get('check') is True
        assert call_kwargs.get('capture_output') is True
        assert call_kwargs.get('text') is True

    # Ensure we're back to the original directory
    assert os.getcwd() == original_cwd


def test_compile_build_requirements_success(temp_workspace):
    """Test successful compilation of build requirements using pybuild-deps."""
    # Create test files
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_txt = pkg_path / "requirements.txt"
    requirements_build_txt = pkg_path / "requirements-build.txt"

    # Create requirements.txt
    with open(requirements_txt, "w") as f:
        f.write("requests==2.28.0\nclick==8.0.0\n")

    # Mock subprocess.run
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()

        compile_build_requirements(
            requirements_txt,
            requirements_build_txt,
            temp_workspace
        )

        mock_run.assert_called_once()
        # Check that the correct arguments were passed
        call_args = mock_run.call_args[0][0]
        assert "pybuild_deps" in call_args[2]
        assert "compile" in call_args[3]
        assert "--generate-hashes" in call_args

        # Check that subprocess.run was called with the correct keyword arguments
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get('check') is True
        assert call_kwargs.get('capture_output') is True
        assert call_kwargs.get('cwd') == temp_workspace


def test_compile_build_requirements_subprocess_error(temp_workspace):
    """Test that subprocess errors are propagated (not caught)."""
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_txt = pkg_path / "requirements.txt"
    requirements_build_txt = pkg_path / "requirements-build.txt"

    with open(requirements_txt, "w") as f:
        f.write("requests==2.28.0\n")

    # Mock subprocess.run to raise CalledProcessError
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "pybuild-deps")

        # The exception should propagate (not be caught)
        with pytest.raises(subprocess.CalledProcessError):
            compile_build_requirements(
                requirements_txt,
                requirements_build_txt,
                temp_workspace
            )


def test_compile_build_requirements_file_not_found(temp_workspace):
    """Test that FileNotFoundError is propagated when pybuild-deps is not found."""
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_txt = pkg_path / "requirements.txt"
    requirements_build_txt = pkg_path / "requirements-build.txt"

    with open(requirements_txt, "w") as f:
        f.write("requests==2.28.0\n")

    # Mock subprocess.run to raise FileNotFoundError
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError("pybuild-deps command not found")

        # The exception should propagate (not be caught)
        with pytest.raises(FileNotFoundError):
            compile_build_requirements(
                requirements_txt,
                requirements_build_txt,
                temp_workspace
            )


def test_compile_build_requirements_correct_paths(temp_workspace):
    """Test that correct relative paths are used in the command."""
    pkg_path = temp_workspace / "packages" / "test-pkg"
    pkg_path.mkdir()

    requirements_txt = pkg_path / "requirements.txt"
    requirements_build_txt = pkg_path / "requirements-build.txt"

    with open(requirements_txt, "w") as f:
        f.write("requests==2.28.0\n")

    # Mock subprocess.run
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()

        compile_build_requirements(
            requirements_txt,
            requirements_build_txt,
            temp_workspace
        )

        mock_run.assert_called_once()
        # Check the command arguments
        call_args = mock_run.call_args[0][0]

        # Find the input and output file arguments
        input_file_arg = call_args[5]  # After "pybuild_deps", "compile", "--generate-hashes"
        output_file_arg = call_args[7]  # After "--output-file"

        # Check that relative paths are used
        assert input_file_arg == str(requirements_txt.relative_to(temp_workspace))
        assert output_file_arg == str(requirements_build_txt.relative_to(temp_workspace))


def test_generate_package_wrapper_with_programmatic_compilation(temp_workspace):
    """Test that generate_package_wrapper uses both compilation functions."""
    additional_requirements = load_additional_requirements(temp_workspace)
    pkg_path = temp_workspace / "packages" / "test-pkg-1"

    # Mock the compilation functions
    with patch('calunga.commands.generate.compile_requirements') as mock_compile, \
         patch('calunga.commands.generate.compile_build_requirements') as mock_compile_build:
        mock_compile.return_value = None
        mock_compile_build.return_value = None

        generate_package_wrapper("test-pkg-1", pkg_path, additional_requirements, temp_workspace)

        # Check that compilation was called
        mock_compile.assert_called_once()
        call_args = mock_compile.call_args
        assert call_args[0][0] == pkg_path / "requirements.in"  # requirements_in_path
        assert call_args[0][1] == pkg_path / "requirements.txt"  # requirements_txt_path
        assert call_args[0][2] == temp_workspace  # base_path
        assert call_args[1]['allow_unsafe'] is True
        assert call_args[1]['generate_hashes'] is True

        # Check that build compilation was called
        mock_compile_build.assert_called_once()
        build_call_args = mock_compile_build.call_args
        assert build_call_args[0][0] == pkg_path / "requirements.txt"  # requirements_txt_path
        assert build_call_args[0][1] == pkg_path / "requirements-build.txt"  # requirements_build_path
        assert build_call_args[0][2] == temp_workspace  # base_path


def test_generate_konflux_resources(temp_workspace):
    """Test generating Konflux resources."""
    generate_konflux_resources("test-pkg-1", temp_workspace)

    component_dir = temp_workspace / "konflux" / "components" / "test-pkg-1"
    assert component_dir.exists()

    # Check that files were created
    assert (component_dir / "kustomization.yaml").exists()
    assert (component_dir / "set-resource-name.yaml").exists()
    assert (component_dir / "set-package-name.yaml").exists()

    # Check set-resource-name.yaml content
    with open(component_dir / "set-resource-name.yaml") as f:
        content = f.read()
        assert "test-pkg-1" in content

    # Check set-package-name.yaml content
    with open(component_dir / "set-package-name.yaml") as f:
        content = f.read()
        assert "test-pkg-1" in content
        assert "calunga-tenant/test-pkg-1" in content


def test_generate_pac_resources(temp_workspace):
    """Test generating Pipeline as Code resources."""
    pkg_path = temp_workspace / "packages" / "test-pkg-1"

    generate_pac_resources("test-pkg-1", pkg_path, temp_workspace)

    # Check that output files were created
    assert (temp_workspace / ".tekton" / "packages-on-push.yaml").exists()
    assert (temp_workspace / ".tekton" / "packages-on-pull-request.yaml").exists()

    # Check content substitution
    with open(temp_workspace / ".tekton" / "packages-on-push.yaml") as f:
        content = f.read()
        assert "test-pkg-1-on-push" in content
        assert "Containerfile" in content


def test_update_all_kustomization(temp_workspace):
    """Test updating the main kustomization.yaml file."""
    package_names = ["pkg-a", "pkg-b", "pkg-c"]

    update_all_kustomization(temp_workspace, package_names)

    kustomization_path = temp_workspace / "konflux" / "components" / "kustomization.yaml"
    assert kustomization_path.exists()

    with open(kustomization_path) as f:
        content = f.read()
        assert "pkg-a" in content
        assert "pkg-b" in content
        assert "pkg-c" in content


def test_generate_command_help():
    """Test the generate command help output."""
    result = runner.invoke(app, ["generate", "--help"])
    assert result.exit_code == 0
    assert "Generate package wrappers" in result.stdout
    assert "--skip-wrapper" in result.stdout
    assert "--skip-konflux" in result.stdout
    assert "--skip-pac" in result.stdout


def test_generate_command_basic_execution(temp_workspace):
    """Test basic execution of the generate command."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()

        result = runner.invoke(app, ["generate", str(temp_workspace)])
        assert result.exit_code == 0
        assert "Processing test-pkg-1" in result.stdout
        assert "Processing test-pkg-2" in result.stdout
        assert "Successfully processed 3 packages" in result.stdout


def test_generate_command_skip_options(temp_workspace):
    """Test generate command with skip options."""
    result = runner.invoke(app, [
        "generate",
        str(temp_workspace),
        "--skip-wrapper",
        "--skip-konflux",
        "--skip-pac"
    ])
    assert result.exit_code == 0
    assert "Skipping package wrapper generation" in result.stdout
    assert "Skipping Konflux resource generation" in result.stdout
    assert "Skipping Pipeline as Code generation" in result.stdout


def test_generate_command_default_path():
    """Test generate command with default path (current directory)."""
    # Change to a temporary directory without packages dir for this test
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        # Save current directory
        original_cwd = os.getcwd()
        try:
            # Change to temp directory
            os.chdir(temp_dir)
            result = runner.invoke(app, ["generate"])
            assert result.exit_code == 1
        finally:
            # Restore original directory
            os.chdir(original_cwd)


def test_generate_command_nonexistent_path():
    """Test generate command with non-existent path."""
    result = runner.invoke(app, ["generate", "/nonexistent/path"])
    assert result.exit_code == 1


def test_generate_command_no_packages():
    """Test generate command when no packages are found."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create empty packages directory
        packages_dir = Path(temp_dir) / "packages"
        packages_dir.mkdir()

        result = runner.invoke(app, ["generate", temp_dir])
        assert result.exit_code == 0
        assert "No packages found" in result.stdout