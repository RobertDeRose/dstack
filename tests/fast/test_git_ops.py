from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dstack import git_ops as subject
from dstack.core import DstackError, commit_records
from dstack.git_ops import (
    _autosquash_correction,
    _commit,
    _require_in_progress,
    _require_registered_feature_worktree,
    _verify_head_message,
    build_commit_message,
    canonical_docs_message,
    reject_beads_paths,
    task_commit_body,
)


def task(*, status: str = "in_progress") -> dict[str, object]:
    return {
        "id": "ds-123",
        "title": "Preserve evidence",
        "description": (
            "Planned outcome: preserve task identity across every correction.\n\n"
            "Non-goal: describe completed implementation work here."
        ),
        "notes": (
            "Implementation: Preserve task identity across corrections.\n"
            "Implementation: Keep commit body useful without planning prose."
        ),
        "status": status,
    }


def test_build_commit_message_adds_exactly_one_task_footer() -> None:
    message = build_commit_message("feat(example): preserve evidence", "- Preserve identity.", "ds-123")
    assert message == "feat(example): preserve evidence\n\n- Preserve identity.\n\nTask: ds-123\n"
    with pytest.raises(DstackError):
        build_commit_message("feat: x", "Task: wrong", "ds-123")
    with pytest.raises(DstackError):
        build_commit_message("feat: x", "Beads: wrong", "ds-123")


def test_canonical_docs_message_uses_human_feature_title_without_a_body() -> None:
    message = canonical_docs_message(
        {"title": "Feature: Lean workflow and documentation lifecycle"},
        "lean-workflow-refinement",
        "ds-close",
    )
    assert message == ("docs(lean-workflow-refinement): Lean workflow and documentation lifecycle\n\nTask: ds-close\n")


def test_task_commit_body_uses_ordered_implementation_notes() -> None:
    issue = task()
    issue["notes"] = (
        "Question: ignore this prose.\n"
        "Implementation: Preserve task identity across corrections.\n"
        "Implementation: Keep commit body useful without planning prose."
    )

    assert task_commit_body(issue) == (
        "- Preserve task identity across corrections.\n- Keep commit body useful without planning prose."
    )


def test_task_commit_body_rejects_missing_or_malformed_implementation_notes() -> None:
    missing = task()
    missing["notes"] = "A completed change without the required prefix."
    with pytest.raises(DstackError, match="Implementation"):
        task_commit_body(missing)

    for notes in ("Implementation:", "Implementation: Include Task: ds-123", "Implementation: Include Beads: ds-123"):
        malformed = task()
        malformed["notes"] = notes
        with pytest.raises(DstackError, match="note"):
            task_commit_body(malformed)


def test_task_commit_body_preserves_punctuation_and_keeps_each_bullet_on_one_line() -> None:
    issue = task()
    issue["notes"] = "Implementation:   Add compact output.  \nImplementation: Remove Rich!\n"

    assert task_commit_body(issue) == "- Add compact output.\n- Remove Rich!"


def test_task_commit_body_does_not_rewrite_prose() -> None:
    issue = task()
    issue["notes"] = "Implementation: The output is compact."

    assert task_commit_body(issue) == "- The output is compact."


def test_task_commit_body_rejects_unbounded_implementation_notes() -> None:
    oversized = task()
    oversized["notes"] = "\n".join("Implementation: Add completed increment" for _ in range(101))

    with pytest.raises(DstackError, match="bounded"):
        task_commit_body(oversized)


def test_task_commit_body_stops_at_note_bound_before_scanning_trailing_input() -> None:
    oversized = task()
    oversized["notes"] = "\n".join(
        ["Implementation: Add completed increment" for _ in range(101)]
        + ["Task: trailing-owner-must-not-be-scanned"]
        + ["ignored trailing context" for _ in range(1500)]
    )

    with pytest.raises(DstackError, match="bounded limit of 100 entries"):
        task_commit_body(oversized)


def test_task_commit_body_enforces_note_and_body_boundaries() -> None:
    at_note_limit = task()
    at_note_limit["notes"] = "Implementation: Add " + ("x" * 92)
    assert len(task_commit_body(at_note_limit).splitlines()[0]) == 98

    over_note_limit = task()
    over_note_limit["notes"] = "Implementation: Add " + ("x" * 93)
    with pytest.raises(DstackError, match="96"):
        task_commit_body(over_note_limit)

    at_body_limit = task()
    at_body_limit["notes"] = "\n".join("Implementation: Add " + ("x" * 92) for _ in range(40))
    assert len(task_commit_body(at_body_limit)) == 3959

    over_body_limit = task()
    over_body_limit["notes"] = "\n".join("Implementation: Add " + ("x" * 92) for _ in range(41))
    with pytest.raises(DstackError, match="commit body exceeds"):
        task_commit_body(over_body_limit)


def test_task_commit_body_rejects_an_oversized_notes_field_before_scanning_lines() -> None:
    oversized = task()
    oversized["notes"] = "\n".join("irrelevant context" for _ in range(5000))

    with pytest.raises(DstackError, match="notes field exceeds the bounded limit"):
        task_commit_body(oversized)


def test_commit_creates_reachable_task_evidence(git_repo: Path) -> None:
    (git_repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    commit = _commit(git_repo, build_commit_message("feat(example): add change", "", "ds-123"))
    records = commit_records(git_repo, "HEAD~1..HEAD")
    assert records[0]["commit"] == commit
    assert records[0]["footer_ids"] == ("ds-123",)
    assert records[0]["footer_kind"] == "Task"


def test_commit_rejects_beads_state_and_unstaged_changes(git_repo: Path) -> None:
    with pytest.raises(DstackError):
        reject_beads_paths(["src/app.py", ".beads/config.yaml"])

    (git_repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    (git_repo / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=git_repo, check=True)
    with pytest.raises(DstackError, match="unstaged or untracked"):
        _commit(git_repo, build_commit_message("feat(example): change", "", "ds-123"))


def test_commit_requires_the_registered_feature_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registered = tmp_path / "repo.feat-example"
    current = tmp_path / "other"

    class FakeClient:
        root = current

    monkeypatch.setattr(subject, "worktree_for_branch", lambda client, branch: registered)
    monkeypatch.setattr(subject, "verify_worktree_identity", lambda root, worktree, branch: registered)
    monkeypatch.setattr(subject, "git_root", lambda root: current)

    with pytest.raises(DstackError, match="registered feature worktree"):
        _require_registered_feature_worktree(FakeClient(), "feat/example")  # type: ignore[arg-type]


def test_native_in_progress_status_is_required() -> None:
    _require_in_progress(task())
    for status in ("open", "blocked", "closed"):
        with pytest.raises(DstackError, match="in_progress"):
            _require_in_progress(task(status=status))


def test_verify_head_message_rejects_multiple_or_legacy_owners(git_repo: Path) -> None:
    (git_repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            "feat(example): add change",
            "-m",
            "Task: ds-123\nBeads: ds-123",
        ],
        cwd=git_repo,
        check=True,
    )
    with pytest.raises(DstackError):
        _verify_head_message(git_repo, subject="feat(example): add change", task_id="ds-123")


def test_verify_head_message_rejects_legacy_owner_for_correction(git_repo: Path) -> None:
    (git_repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat(legacy): old contract", "-m", "Beads: ds-123"],
        cwd=git_repo,
        check=True,
    )

    with pytest.raises(DstackError):
        _verify_head_message(git_repo, subject="feat(example): add change", task_id="ds-123")


def test_autosquash_correction_targets_exact_commit_when_subjects_repeat(git_repo: Path) -> None:
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, text=True, capture_output=True
    ).stdout.strip()
    (git_repo / "other.txt").write_text("unrelated\n", encoding="utf-8")
    subprocess.run(["git", "add", "other.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat(old): duplicate subject", "-m", "Task: ds-other"],
        cwd=git_repo,
        check=True,
    )
    (git_repo / "change.txt").write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat(old): duplicate subject", "-m", "Task: ds-123"],
        cwd=git_repo,
        check=True,
    )
    target = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, text=True, capture_output=True
    ).stdout.strip()
    (git_repo / "change.txt").write_text("corrected\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=git_repo, check=True)
    message = build_commit_message(
        "feat(example): add change",
        "- Preserve the corrected behavior.",
        "ds-123",
    )

    _autosquash_correction(git_repo, target=target, base=base, message=message)

    observed = subprocess.run(
        ["git", "log", "--reverse", "--format=%B%x00", f"{base}..HEAD"],
        cwd=git_repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.split("\x00")
    assert observed[0].strip() == "feat(old): duplicate subject\n\nTask: ds-other"
    assert observed[1].strip() == message.strip()


@pytest.mark.parametrize("note", ["Add support for `Result<T, E>`", "Use foo()", "Keep [the API](api.md)"])
def test_task_commit_body_preserves_technical_syntax(note: str) -> None:
    issue = task()
    issue["notes"] = f"Implementation: {note}"
    assert task_commit_body(issue) == f"- {note}"
