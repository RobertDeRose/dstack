from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dstack.core import DstackError, commit_records
from dstack.git_ops import _commit, _verify_head_message, build_commit_message, reject_beads_paths


def test_build_commit_message_adds_exactly_one_footer() -> None:
    message = build_commit_message("fix(core): preserve evidence", "Explain the change.", "ds-123")
    assert message == "fix(core): preserve evidence\n\nExplain the change.\n\nBeads: ds-123\n"
    with pytest.raises(DstackError):
        build_commit_message("fix: x", "Beads: wrong", "ds-123")


def test_commit_creates_reachable_evidence(git_repo: Path) -> None:
    (git_repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    commit = _commit(git_repo, build_commit_message("feat: add change", "", "ds-123"), amend=False)
    records = commit_records(git_repo, "HEAD~1..HEAD")
    assert records[0]["commit"] == commit
    assert records[0]["footer_ids"] == ("ds-123",)


def test_implementation_commit_rejects_beads_state() -> None:
    with pytest.raises(DstackError):
        reject_beads_paths(["src/app.py", ".beads/config.yaml"])


def test_verify_head_message_rejects_multiple_beads_owners(git_repo: Path) -> None:
    (git_repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            "feat: add change",
            "-m",
            "Beads: ds-123\nBeads: ds-456",
        ],
        cwd=git_repo,
        check=True,
    )
    with pytest.raises(DstackError):
        _verify_head_message(git_repo, subject="feat: add change", bead_id="ds-123")
