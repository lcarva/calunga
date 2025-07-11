"""Tests for the generate command."""

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
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock()
        generate_package_wrapper("test-pkg-1", pkg_path, additional_requirements)

    # Check that files were created
    assert (pkg_path / "pyproject.toml").exists()
    assert (pkg_path / "requirements.in").exists()
    assert (pkg_path / "argfile.conf").exists()

    # Check pyproject.toml content
    with open(pkg_path / "pyproject.toml") as f:
        content = f.read()
        assert "test-pkg-1_placeholder_wrapper" in content

    # Check requirements.in content
    with open(pkg_path / "requirements.in") as f:
        content = f.read()
        assert "test-pkg-1" in content
        assert "setuptools" in content

    # Check argfile.conf content
    with open(pkg_path / "argfile.conf") as f:
        content = f.read()
        assert "PACKAGE_NAME=test_pkg_1" in content


def test_generate_package_wrapper_skip_existing(temp_workspace):
    """Test that existing files are not overwritten."""
    additional_requirements = load_additional_requirements(temp_workspace)
    pkg_path = temp_workspace / "packages" / "existing-pkg"

    # Read original content
    with open(pkg_path / "pyproject.toml") as f:
        original_content = f.read()

    generate_package_wrapper("existing-pkg", pkg_path, additional_requirements)

    # Check that existing file was not overwritten
    with open(pkg_path / "pyproject.toml") as f:
        current_content = f.read()
        assert current_content == original_content


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