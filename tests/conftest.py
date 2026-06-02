"""Shared pytest configuration for the ttrpg-gm plugin tests.

Adds the repo root to `sys.path` so individual test modules can import
helpers if any get factored out, and exposes the repo root and templates
directory as fixtures so test files don't recompute paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the plugin repo root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def templates_dir(repo_root: Path) -> Path:
    """Absolute path to the plugin's `templates/` directory.

    The scaffolder phase of `/ingest` reads from here when it writes the
    seven template files into a new campaign repo.
    """
    return repo_root / "templates"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the test fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"
