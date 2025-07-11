"""Tests for version and package metadata."""

import re

from calunga import __version__


def test_version_format():
    """Test that the version follows semantic versioning format."""
    # Basic semver pattern (major.minor.patch)
    semver_pattern = r"^\d+\.\d+\.\d+$"
    assert re.match(semver_pattern, __version__)


def test_version_is_string():
    """Test that the version is a string."""
    assert isinstance(__version__, str)


def test_version_is_not_empty():
    """Test that the version is not empty."""
    assert __version__.strip() != ""


def test_version_expected_value():
    """Test that the version matches the expected initial value."""
    assert __version__ == "0.0.1"


def test_version_parts():
    """Test that the version has the expected parts."""
    parts = __version__.split(".")
    assert len(parts) == 3
    assert parts[0] == "0"  # major
    assert parts[1] == "0"  # minor
    assert parts[2] == "1"  # patch