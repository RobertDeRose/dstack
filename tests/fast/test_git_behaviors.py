from __future__ import annotations

import subprocess
import threading
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import commands as dstack_commands
from dstack.commands import DstackError
from dstack import core as dstacklib
from dstack.core import (
    CommandResult,
    canonical_positive_integer,
    commit_footer_ids,
    commits_for_bead,
    conventional_worktree,
    ensure_clean_tracked,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_records,
)


def test_read_only_client_does_not_initialize_beads(git_repo: Path) -> None:
    assert not (git_repo / ".beads").exists()
    with pytest.raises(DstackError, match="Beads is not initialized"):
        dstack_commands.client_for(git_repo, initialize=False)
    assert not (git_repo / ".beads").exists()


@pytest.mark.parametrize("value", ["0", "-1", "+1", "01", " 1", "1 "])
def test_positive_integer_parser_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(DstackError, match="positive canonical integer"):
        canonical_positive_integer(value, field="PR number")


def test_positive_integer_parser_accepts_canonical_value() -> None:
    assert canonical_positive_integer("42", field="PR number") == 42


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


def test_targeted_commit_evidence_uses_fixed_footer_query(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    output = (
        "\x1eabc123\x00exact\x00exact\n\nBeads: task-1\n\x00\nfile.py\n"
        "\x1edef456\x00prefix\x00prefix\n\nBeads: task-10\n\x00\nother.py\n"
    )

    def fake_run(command, *, cwd, check=True, **kwargs):
        del cwd, check, kwargs
        calls.append(tuple(command))
        if command[:2] == ["git", "rev-parse"]:
            return CommandResult(0, "resolved\n", "")
        if command[:2] == ["git", "log"]:
            assert "--fixed-strings" in command
            assert "--grep=Beads: task-1" in command
            return CommandResult(0, output, "")
        raise AssertionError(command)

    monkeypatch.setattr(dstacklib, "run", fake_run)
    assert commits_for_bead(tmp_path, "main..feature", "task-1") == [
        {"commit": "abc123", "subject": "exact", "paths": ["file.py"]}
    ]
    assert sum(call[:2] == ("git", "log") for call in calls) == 1


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


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_command_timeout_env_must_be_finite(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DSTACK_COMMAND_TIMEOUT_SECONDS", value)
    with pytest.raises(DstackError, match="finite"):
        dstacklib.command_timeout(["git", "status"])


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), 0.0])
def test_explicit_command_timeout_must_be_finite_and_positive(git_repo: Path, timeout: float) -> None:
    with pytest.raises(DstackError, match="positive and finite"):
        dstacklib.run(["git", "status"], cwd=git_repo, timeout=timeout)


def test_repository_mutation_lock_is_reentrant(git_repo: Path) -> None:
    with dstacklib.repository_mutation_lock(git_repo):
        with dstacklib.repository_mutation_lock(git_repo):
            pass


def test_repository_mutation_lock_serializes_threads(git_repo: Path) -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first() -> None:
        with dstacklib.repository_mutation_lock(git_repo):
            first_entered.set()
            assert release_first.wait(1)

    def second() -> None:
        assert first_entered.wait(1)
        with dstacklib.repository_mutation_lock(git_repo):
            second_entered.set()

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    second_thread.start()
    try:
        assert first_entered.wait(1)
        assert not second_entered.wait(0.05)
    finally:
        release_first.set()
    assert second_entered.wait(1)
    first_thread.join()
    second_thread.join()


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


def test_worktree_identity_rejects_symlinked_conventional_path(git_repo: Path, tmp_path: Path) -> None:
    path = conventional_worktree(git_repo, "topic")
    outside = tmp_path / "outside"
    outside.mkdir()
    path.symlink_to(outside, target_is_directory=True)
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "topic", str(path), "HEAD"],
        cwd=git_repo,
        check=True,
    )

    with pytest.raises(DstackError, match="worktree must not be a symlink"):
        verify_worktree_identity(git_repo, path, "topic")


def test_worktree_identity_rejects_independent_repository_at_conventional_path(
    git_repo: Path,
) -> None:
    path = conventional_worktree(git_repo, "topic")
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--initial-branch=topic"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    (path / "independent.txt").write_text("independent\n")
    subprocess.run(["git", "add", "independent.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "independent"], cwd=path, check=True)

    with pytest.raises(DstackError, match="repository identity"):
        verify_worktree_identity(git_repo, path, "topic")


def test_worktree_creation_rejects_symlinked_parent_before_native_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    link = tmp_path / "link"
    root.mkdir()
    outside.mkdir()
    link.symlink_to(outside, target_is_directory=True)
    expected = link / "worktree"
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(dstack_commands, "validate_git_branch", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "validate_git_revision", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "worktree_for_branch", lambda *args: None)
    monkeypatch.setattr(dstack_commands, "conventional_worktree", lambda *args: expected)
    monkeypatch.setattr(dstack_commands, "branch_exists", lambda *args: False)
    monkeypatch.setattr(
        dstack_commands,
        "run",
        lambda command, **kwargs: calls.append(tuple(command)) or pytest.fail("native mutation ran"),
    )

    with pytest.raises(DstackError, match="worktree must not be a symlink"):
        dstack_commands.ensure_branch_worktree(SimpleNamespace(root=root), "topic", "main")
    assert calls == []


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


def test_failed_creator_does_not_remove_concurrent_worker_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    worktree = conventional_worktree(root, "feat/topic")
    registered = False
    branches = {"main"}
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(dstack_commands, "validate_git_branch", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "validate_git_revision", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(dstack_commands, "ancestry", lambda *args: True)
    monkeypatch.setattr(dstack_commands, "branch_exists", lambda root, branch: branch in branches)

    def worktree_for_branch(root: Path, branch: str) -> Path | None:
        del root, branch
        return worktree if registered else None

    monkeypatch.setattr(dstack_commands, "worktree_for_branch", worktree_for_branch)

    def fake_run(command, **kwargs):
        nonlocal registered
        del kwargs
        calls.append(tuple(command))
        if command[:3] == ["git", "branch", "--"]:
            branches.add(command[3])
            return CommandResult(0, "", "")
        if command[:3] == ["bd", "worktree", "create"]:
            worktree.mkdir(parents=True)
            registered = True
            raise DstackError("another worker created the worktree")
        raise AssertionError(command)

    monkeypatch.setattr(dstack_commands, "run", fake_run)
    with pytest.raises(DstackError, match="another worker") as raised:
        dstack_commands.ensure_feature_worktree(SimpleNamespace(root=root), "topic", "main")

    assert "retained_path=" in str(raised.value)
    assert "git worktree list --porcelain" in str(raised.value)
    assert worktree.exists()
    assert "feat/topic" in branches
    assert not any(call[:3] == ("bd", "worktree", "remove") for call in calls)
    assert not any(call[:3] == ("git", "branch", "-D") for call in calls)
