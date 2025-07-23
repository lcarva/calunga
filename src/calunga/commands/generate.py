"""Generate command for Calunga CLI."""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TaskID


console = Console()

def load_additional_requirements(path: Path) -> Dict[str, Any]:
    """Load additional requirements from YAML file."""
    additional_requirements_path = path / "packages" / "additional-requirements.yaml"
    if additional_requirements_path.exists():
        with open(additional_requirements_path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def find_packages(packages_dir: Path) -> List[Path]:
    """Find all package directories."""
    if not packages_dir.exists():
        console.print(f"[red]Error: packages directory not found at {packages_dir}[/red]")
        raise typer.Exit(1)

    packages = []
    for item in packages_dir.iterdir():
        if item.is_dir():
            packages.append(item)

    return sorted(packages)


def compile_requirements(
    requirements_in_path: Path,
    requirements_txt_path: Path,
    base_path: Path,
    allow_unsafe: bool = True,
    generate_hashes: bool = True
):
    """Compile requirements using pip-tools."""
    # Ideally, this would be done as a python module call, but it doesn't seem possible. At least
    # the same python environment is used. This should work if all the dependencies are installed.
    command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        str(requirements_in_path.relative_to(base_path)),
        "--output-file",
        str(requirements_txt_path.relative_to(base_path)),
        "--allow-unsafe" if allow_unsafe else "--no-allow-unsafe",
        "--generate-hashes" if generate_hashes else "--no-generate-hashes",
        "--index-url",
        "http://localhost:8080/simple/"
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Error running pip-tools compile:[/red]\n{exc.stdout}\n{exc.stderr}")
        raise


def compile_build_requirements(
    requirements_txt_path: Path,
    requirements_build_path: Path,
    base_path: Path
) -> None:
    """Compile build requirements using pybuild-deps."""
    command = [
        sys.executable,
        "-m",
        "pybuild_deps",
        "compile",
        "--generate-hashes",
        str(requirements_txt_path.relative_to(base_path)),
        "--output-file",
        str(requirements_build_path.relative_to(base_path))
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=base_path
        )
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Error running pybuild-deps compile:[/red]\n{exc.stdout}\n{exc.stderr}")
        raise


def generate_package_wrapper(
    name: str,
    path: Path,
    additional_requirements: Dict[str, Any],
    base_path: Path
) -> None:
    """Generate package wrapper files."""
    console.print(f"  [blue]Generating package wrapper for {name}[/blue]")

    # Generate pyproject.toml
    pyproject_path = path / "pyproject.toml"
    if not pyproject_path.exists():
        pyproject_content = f"""[project]
name = "{name}_placeholder_wrapper"
version = "0.0.1"
"""
        with open(pyproject_path, "w") as f:
            f.write(pyproject_content)

    # Generate requirements.in
    requirements_in_path = path / "requirements.in"
    if not requirements_in_path.exists():
        console.print(f"    Creating requirements.in file for {name}")
        requirements_in_content = [name]

        # Add additional requirements from YAML
        package_config = additional_requirements.get("packages", {}).get(name, {})
        additional_reqs = package_config.get("requirements_in", [])
        requirements_in_content.extend(additional_reqs)

        with open(requirements_in_path, "w") as f:
            f.write("\n".join(requirements_in_content) + "\n")

    # Generate requirements.txt using pip-tools programmatically
    requirements_txt_path = path / "requirements.txt"
    if not requirements_txt_path.exists():
        console.print(f"    Creating requirements.txt file for {name}")
        compile_requirements(
            requirements_in_path,
            requirements_txt_path,
            base_path,
            allow_unsafe=True,
            generate_hashes=True
        )

    # Generate requirements-build.txt
    requirements_build_path = path / "requirements-build.txt"
    if not requirements_build_path.exists():
        console.print(f"    Creating requirements-build.txt for {name}")
        compile_build_requirements(
            requirements_txt_path,
            requirements_build_path,
            base_path
        )

    # Generate argfile.conf
    argfile_path = path / "argfile.conf"
    if not argfile_path.exists():
        package_config = additional_requirements.get("packages", {}).get(name, {})
        package_name = package_config.get("package_name", name.replace("-", "_"))

        argfile_content = f"PACKAGE_NAME={package_name}\n"
        with open(argfile_path, "w") as f:
            f.write(argfile_content)


def generate_konflux_resources(name: str, base_path: Path) -> None:
    """Generate Konflux resources for a package."""
    console.print(f"  [blue]Generating Konflux resources for {name}[/blue]")

    # Create component directory
    component_dir = base_path / "konflux" / "components" / name
    component_dir.mkdir(parents=True, exist_ok=True)

    # Copy base kustomization
    base_kustomization_path = base_path / "konflux" / "components" / "base" / "pkg-kustomization.yaml"
    target_kustomization_path = component_dir / "kustomization.yaml"

    if base_kustomization_path.exists():
        with open(base_kustomization_path, "r") as f:
            content = f.read()
        with open(target_kustomization_path, "w") as f:
            f.write(content)

    # Generate set-resource-name.yaml
    set_resource_name_path = component_dir / "set-resource-name.yaml"
    set_resource_name_content = f"""- op: replace
  path: /metadata/name
  value: {name}
"""
    with open(set_resource_name_path, "w") as f:
        f.write(set_resource_name_content)

    # Generate set-package-name.yaml
    set_package_name_path = component_dir / "set-package-name.yaml"
    set_package_name_content = f"""---
apiVersion: appstudio.redhat.com/v1alpha1
kind: ImageRepository
metadata:
  labels:
    appstudio.redhat.com/component: {name}
  name: {name}
spec:
  image:
    name: calunga-tenant/{name}

---
apiVersion: appstudio.redhat.com/v1alpha1
kind: Component
metadata:
  name: {name}
spec:
  componentName: {name}
  containerImage: quay.io/redhat-user-workloads/calunga-tenant/{name}
"""
    with open(set_package_name_path, "w") as f:
        f.write(set_package_name_content)


def generate_pac_resources(name: str, path: Path, base_path: Path) -> None:
    """Generate Pipeline as Code resources."""
    console.print(f"  [blue]Generating Pipeline as Code resources for {name}[/blue]")

    # Determine containerfile
    containerfile = "Containerfile"
    pkg_containerfile = path / containerfile
    if pkg_containerfile.exists():
        containerfile = str(pkg_containerfile.relative_to(base_path))

    # Read templates and substitute variables
    templates = [
        (".tekton/on-push.yaml.template", ".tekton/packages-on-push.yaml"),
        (".tekton/on-pull-request.yaml.template", ".tekton/packages-on-pull-request.yaml")
    ]

    for template_path, output_path in templates:
        template_file = base_path / template_path
        output_file = base_path / output_path

        if template_file.exists():
            with open(template_file, "r") as f:
                template_content = f.read()

            # Simple variable substitution
            substituted_content = template_content.replace("${name}", name)
            substituted_content = substituted_content.replace("${containerfile}", containerfile)

            # Append to output file
            with open(output_file, "a") as f:
                f.write(substituted_content)


def update_all_kustomization(base_path: Path, package_names: List[str]) -> None:
    """Update the main kustomization.yaml file."""
    all_kustomization_path = base_path / "konflux" / "components" / "kustomization.yaml"

    content = """---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
"""

    for name in sorted(package_names):
        content += f"  - {name}\n"

    with open(all_kustomization_path, "w") as f:
        f.write(content)


def generate(
    path: Optional[str] = typer.Argument(
        default=".",
        help="Path to work on (default: current directory)"
    ),
    skip_wrapper: bool = typer.Option(
        False,
        "--skip-wrapper",
        help="Skip package wrapper generation"
    ),
    skip_konflux: bool = typer.Option(
        False,
        "--skip-konflux",
        help="Skip Konflux resource generation"
    ),
    skip_pac: bool = typer.Option(
        False,
        "--skip-pac",
        help="Skip Pipeline as Code generation"
    ),
) -> None:
    """Generate package wrappers, Konflux resources, and Pipeline as Code configurations."""

    base_path = Path(path).resolve()
    packages_dir = base_path / "packages"

    console.print(Panel(
        f"[bold blue]Calunga Generator[/bold blue]\n"
        f"Working directory: {base_path}\n"
        f"Packages directory: {packages_dir}",
        title="🔧 Generate",
        border_style="blue",
    ))

    # Load additional requirements
    additional_requirements = load_additional_requirements(base_path)

    # Find all packages
    packages = find_packages(packages_dir)

    if not packages:
        console.print("[yellow]No packages found in the packages directory.[/yellow]")
        return

    # Clear PAC output files if not skipping
    if not skip_pac:
        for pac_file in [".tekton/packages-on-push.yaml", ".tekton/packages-on-pull-request.yaml"]:
            pac_path = base_path / pac_file
            if pac_path.exists():
                pac_path.unlink()

    # Process each package
    with Progress() as progress:
        task = progress.add_task("Processing packages...", total=len(packages))

        package_names = []
        for package_path in packages:
            name = package_path.name
            package_names.append(name)

            console.print(f"[green]Processing {name}[/green]")

            if not skip_wrapper:
                generate_package_wrapper(name, package_path, additional_requirements, base_path)
            else:
                console.print("  [dim]Skipping package wrapper generation[/dim]")

            if not skip_konflux:
                generate_konflux_resources(name, base_path)
            else:
                console.print("  [dim]Skipping Konflux resource generation[/dim]")

            if not skip_pac:
                generate_pac_resources(name, package_path, base_path)
            else:
                console.print("  [dim]Skipping Pipeline as Code generation[/dim]")

            progress.update(task, advance=1)

    # Update main kustomization file
    if not skip_konflux:
        update_all_kustomization(base_path, package_names)

    console.print(Panel(
        f"[bold green]✅ Successfully processed {len(packages)} packages[/bold green]",
        title="Complete",
        border_style="green",
    ))