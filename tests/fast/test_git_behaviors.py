from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
from dstack_commands import DstackError
from dstacklib import commit_footer_ids, ensure_clean_tracked, worktree_records


def test_commit_footer_audit_handles_multiple_footers(git_repo: Path) -> None:
    path = git_repo / "change.py"
    path.write_text("pass\n")
    subprocess.run(["git", "add", "change.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "change\n\nBeads: task-1\nBeads: task-2"],
        cwd=git_repo,
        check=True,
    )
    result = commit_footer_ids(git_repo, "HEAD~1..HEAD")
    assert set(result) == {"task-1", "task-2"}
    assert result["task-1"][0]["paths"] == ["change.py"]


def test_clean_tracked_ignores_untracked_but_rejects_tracked(git_repo: Path) -> None:
    (git_repo / "untracked").write_text("ignored by this guard\n")
    ensure_clean_tracked(git_repo)
    tracked = git_repo / "tracked"
    tracked.write_text("dirty\n")
    subprocess.run(["git", "add", "tracked"], cwd=git_repo, check=True)
    with pytest.raises(DstackError, match="tracked worktree changes"):
        ensure_clean_tracked(git_repo)


def test_worktree_records_parse_native_porcelain(git_repo: Path) -> None:
    records = worktree_records(git_repo)
    assert records and records[0]["worktree"] == str(git_repo)
