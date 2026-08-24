from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_commands
from dstack_commands import DstackError
import dstacklib
from dstacklib import (
    CommandResult,
    commit_footer_ids,
    conventional_worktree,
    ensure_clean_tracked,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_records,
)


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


def test_run_reports_timeout_and_mutation_risk(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(dstacklib.subprocess, "run", timed_out)
    with pytest.raises(DstackError, match=r"timed out.*may have changed state"):
        dstacklib.run(["git", "merge", "topic"], cwd=git_repo, timeout=1)


def test_command_timeout_env_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSTACK_COMMAND_TIMEOUT_SECONDS", "0")
    with pytest.raises(DstackError, match="must be positive"):
        dstacklib.command_timeout(["git", "status"])


def test_clean_worktree_rejects_untracked_files(git_repo: Path) -> None:
    (git_repo / "untracked.txt").write_text("not deliverable\n")
    with pytest.raises(DstackError, match="worktree changes"):
        dstacklib.ensure_clean_worktree(git_repo)


def test_ready_claim_timeout_is_reported_as_potentially_mutating() -> None:
    assert dstacklib.command_may_mutate(["bd", "ready", "--claim", "--json"])
    assert not dstacklib.command_may_mutate(["bd", "ready", "--json"])


def test_fetch_timeout_is_reported_as_potentially_mutating() -> None:
    assert dstacklib.command_may_mutate(["git", "fetch", "origin", "--prune"])


def test_git_inputs_reject_invalid_and_option_like_values(git_repo: Path) -> None:
    for value in ("--help", "bad ref", "topic..other"):
        with pytest.raises(DstackError, match="invalid"):
            validate_git_branch(git_repo, value)
    for value in ("--help", "missing", "HEAD\nmain"):
        with pytest.raises(DstackError, match="invalid|does not resolve"):
            validate_git_revision(git_repo, value)
    assert validate_git_branch(git_repo, "topic") == "topic"
    assert validate_git_revision(git_repo, "HEAD") == "HEAD"


def test_worktree_identity_rejects_wrong_branch_at_conventional_path(
    git_repo: Path,
) -> None:
    path = conventional_worktree(git_repo, "topic")
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "other", str(path), "HEAD"],
        cwd=git_repo,
        check=True,
    )
    with pytest.raises(DstackError, match="identity mismatch"):
        verify_worktree_identity(git_repo, path, "topic")


def test_reused_worktree_rejects_invalid_base_ancestry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    root.mkdir()
    worktree.mkdir()
    monkeypatch.setattr(dstack_commands, "validate_git_branch", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "validate_git_revision", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "worktree_for_branch", lambda *args: worktree)
    monkeypatch.setattr(dstack_commands, "verify_worktree_identity", lambda *args: worktree)
    monkeypatch.setattr(dstack_commands, "ancestry", lambda *args: False)
    with pytest.raises(DstackError, match="does not contain base"):
        dstack_commands.ensure_feature_worktree(SimpleNamespace(root=root), "topic", "main")


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_created_worktree_verification_failure_cleans_without_hiding_primary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cleanup_fails: bool,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    worktree = conventional_worktree(root, "feat/topic")
    calls: list[tuple[str, ...]] = []
    branches = {"main"}

    monkeypatch.setattr(dstack_commands, "validate_git_branch", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "validate_git_revision", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "ancestry", lambda *args: True)
    monkeypatch.setattr(
        dstack_commands,
        "branch_exists",
        lambda root, branch: branch in branches,
    )
    monkeypatch.setattr(
        dstack_commands,
        "worktree_for_branch",
        lambda root, branch: worktree if worktree.exists() else None,
    )
    monkeypatch.setattr(
        dstack_commands,
        "verify_worktree_identity",
        lambda *args, **kwargs: (_ for _ in ()).throw(DstackError("primary verification failure")),
    )

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        if command[:3] == ["git", "branch", "--"]:
            branches.add(command[3])
            return CommandResult(0, "", "")
        if command[:3] == ["bd", "worktree", "create"]:
            worktree.mkdir(parents=True)
            return CommandResult(0, "", "")
        if command[:3] == ["bd", "worktree", "remove"]:
            if cleanup_fails:
                return CommandResult(1, "", "remove failed")
            worktree.rmdir()
            return CommandResult(0, "", "")
        if command[:3] == ["git", "branch", "-D"]:
            branches.discard(command[-1])
            return CommandResult(0, "", "")
        raise AssertionError(command)

    monkeypatch.setattr(dstack_commands, "run", fake_run)
    client = SimpleNamespace(root=root)
    message = "primary verification failure.*cleanup failed" if cleanup_fails else "primary verification failure"
    with pytest.raises(DstackError, match=message):
        dstack_commands.ensure_feature_worktree(client, "topic", "main")
    assert any(call[:3] == ("bd", "worktree", "remove") for call in calls)
    if not cleanup_fails:
        assert not worktree.exists()
        assert "feat/topic" not in branches
