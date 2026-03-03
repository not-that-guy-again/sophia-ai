"""Tests for the constitution loader."""

from pathlib import Path

from sophia.core.constitution import load_constitution


def test_load_constitution_returns_file_contents():
    """load_constitution() returns the contents of sophia/constitution.md."""
    text = load_constitution()
    assert len(text) > 0
    assert "Sophia" in text


def test_load_constitution_explicit_path():
    """Passing an explicit valid path works."""
    path = str(Path(__file__).resolve().parent.parent.parent / "sophia" / "constitution.md")
    text = load_constitution(path)
    assert "Sophia" in text


def test_load_constitution_missing_file_returns_empty():
    """A nonexistent path returns an empty string without raising."""
    text = load_constitution("/nonexistent/path.md")
    assert text == ""
