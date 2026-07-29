# ruff: noqa: EM102, S603

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("skills/dstack-core/scripts/reconcile-beads-interactions.py")
INTERACTIONS = Path(".beads/interactions.jsonl")


def run(*args: str | Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(arg) for arg in args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise AssertionError(f"command failed: {args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def interaction(interaction_id: str, issue_id: str) -> str:
    return json.dumps(
        {
            "id": interaction_id,
            "kind": "field_change",
            "created_at": "2026-07-29T12:00:00Z",
            "issue_id": issue_id,
        },
        separators=(",", ":"),
    )


@pytest.fixture
def interaction_worktrees(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "project"
    feature = tmp_path / "project.feature"
    run("git", "init", "-b", "main", base)
    run("git", "-C", base, "config", "user.name", "Test User")
    run("git", "-C", base, "config", "user.email", "test@example.com")
    path = base / INTERACTIONS
    path.parent.mkdir()
    path.write_text(interaction("int-base", "project-old") + "\n", encoding="utf-8")
    run("git", "-C", base, "add", INTERACTIONS)
    run("git", "-C", base, "commit", "-m", "initial")
    run("git", "-C", base, "branch", "feat/example")
    run("git", "-C", base, "worktree", "add", feature, "feat/example")

    feature_path = feature / INTERACTIONS
    feature_path.write_text(
        feature_path.read_text(encoding="utf-8") + interaction("int-spec", "project-a.1") + "\n",
        encoding="utf-8",
    )
    run("git", "-C", feature, "add", INTERACTIONS)
    run("git", "-C", feature, "commit", "-m", "record spec state")

    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-close", "project-a.7") + "\n",
        encoding="utf-8",
    )
    return base, feature


def test_reconciles_only_committed_feature_interactions(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    base, feature = interaction_worktrees
    script = repository_root / SCRIPT
    common = (
        "--base-worktree",
        base,
        "--feature-worktree",
        feature,
        "--root-id",
        "project-a",
    )

    run(sys.executable, script, "prepare", *common)
    assert "int-spec" in (feature / INTERACTIONS).read_text(encoding="utf-8")
    assert "int-close" in (feature / INTERACTIONS).read_text(encoding="utf-8")
    assert run(sys.executable, script, "finalize", *common, check=False).returncode != 0

    run("git", "-C", feature, "add", INTERACTIONS)
    run("git", "-C", feature, "commit", "-m", "record close state")
    run(sys.executable, script, "finalize", *common)
    assert run("git", "-C", base, "status", "--porcelain").stdout == ""

    run("git", "-C", base, "merge", "--ff-only", "feat/example")
    base_path = base / INTERACTIONS
    base_path.write_text(
        base_path.read_text(encoding="utf-8") + interaction("int-delivery", "project-a") + "\n",
        encoding="utf-8",
    )
    run(
        sys.executable,
        script,
        "verify-post-merge",
        "--base-worktree",
        base,
        "--root-id",
        "project-a",
    )

    base_path.write_text(
        base_path.read_text(encoding="utf-8") + interaction("int-foreign", "project-b.1") + "\n",
        encoding="utf-8",
    )
    result = run(
        sys.executable,
        script,
        "verify-post-merge",
        "--base-worktree",
        base,
        "--root-id",
        "project-a",
        check=False,
    )
    assert result.returncode != 0
    assert "outside selected feature molecule" in result.stderr
