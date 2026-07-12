"""Shared subprocess and Git helpers for the pytest suite."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Run a command and raise an assertion with captured output on failure."""
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=None if env is None else dict(env),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, (
        f"Command returned {result.returncode}, expected {expected}: "
        f"{shlex.join(command)}\n"
        f"cwd: {cwd}\n"
        f"stdout:\n{result.stdout or '<empty>'}\n"
        f"stderr:\n{result.stderr or '<empty>'}"
    )
    return result


def initialize_git(repository: Path, message: str, tag: str | None = None) -> None:
    """Initialize a deterministic local Git repository and create its first commit."""
    run_command(["git", "init", "-b", "main"], cwd=repository)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=repository)
    run_command(["git", "config", "user.name", "dstack Test"], cwd=repository)
    commit_repository(repository, message, tag)


def commit_repository(repository: Path, message: str, tag: str | None = None) -> None:
    """Commit all repository changes and optionally create a tag."""
    run_command(["git", "add", "."], cwd=repository)
    run_command(["git", "commit", "-m", message], cwd=repository)
    if tag is not None:
        run_command(["git", "tag", tag], cwd=repository)


def copy_repository_fixture(source: Path, destination: Path) -> None:
    """Copy repository content without VCS metadata or generated caches."""
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            ".hg",
            ".svn",
            ".pytest_cache",
            ".venv",
            "__pycache__",
            "*.pyc",
            "*.pyo",
        ),
    )


def merged_environment(**updates: str) -> dict[str, str]:
    """Return the current process environment with explicit overrides."""
    return os.environ | updates
