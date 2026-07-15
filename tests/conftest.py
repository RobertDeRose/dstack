"""Shared pytest fixtures for dstack repository validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support import copy_repository_fixture, initialize_git, run_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return REPOSITORY_ROOT


@pytest.fixture
def tagged_template_source(tmp_path: Path, repository_root: Path) -> Path:
    source = tmp_path / "source"
    copy_repository_fixture(repository_root, source)
    initialize_git(source, "dstack v1", "v0.0.1")
    # Copier adds --filter to local clones; packing avoids Git's flaky loose-object copy path.
    run_command(["git", "repack", "-ad"], cwd=source)
    return source
