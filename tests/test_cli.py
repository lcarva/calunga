"""Tests for the main CLI module."""

import pytest
from typer.testing import CliRunner

from calunga import __version__
from calunga.cli import app


runner = CliRunner()


def test_version_command():
    """Test the version command displays the correct version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "Calunga CLI" in result.stdout


def test_version_command_contains_expected_elements():
    """Test the version command contains all expected UI elements."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    # Check for the panel title
    assert "📦 Calunga" in result.stdout
    # Check for version info
    assert f"Version: {__version__}" in result.stdout


def test_help_command():
    """Test the help command works and shows available commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage: calunga [OPTIONS] COMMAND [ARGS]..." in result.stdout
    assert "CLI for managing Calunga" in result.stdout
    assert "version" in result.stdout
    assert "generate" in result.stdout


def test_invalid_command():
    """Test that invalid commands return proper error codes."""
    result = runner.invoke(app, ["invalid-command"])
    assert result.exit_code != 0


def test_app_is_callable():
    """Test that the app object is properly configured."""
    assert callable(app)
    assert hasattr(app, "registered_commands")
    assert len(app.registered_commands) > 0
    # Check that the version command is registered
    version_command = next(
        (cmd for cmd in app.registered_commands if cmd.callback.__name__ == "version"),
        None
    )
    assert version_command is not None