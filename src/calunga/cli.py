"""Main CLI module for Calunga."""

import typer
from rich.console import Console
from rich.panel import Panel

from calunga import __version__
from calunga.commands.generate import generate
from calunga.commands.find_issues import find_issues

console = Console()

app = typer.Typer(
    name="calunga",
    help="CLI for managing Calunga - a library of Python packages built from source",
    add_completion=False,
    no_args_is_help=True,
)

# Add subcommands
app.command(name="generate")(generate)
app.command(name="find-issues")(find_issues)


@app.callback(invoke_without_command=False)
def main_callback() -> None:
    """CLI for managing Calunga - a library of Python packages built from source."""
    pass


@app.command()
def version() -> None:
    """Display the version of Calunga CLI."""
    console.print(
        Panel(
            f"[bold blue]Calunga CLI[/bold blue]\n[dim]Version: {__version__}[/dim]",
            title="📦 Calunga",
            border_style="blue",
        )
    )


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()