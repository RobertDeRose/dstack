from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dstack import git_ops as subject
from dstack.core import DstackError
from dstack.git_state import commit_records
from dstack.policy import build_commit_message, canonical_docs_message, reject_beads_paths, task_commit_body
from dstack.git_ops import (
    _autosquash_correction,
    _commit,
    _require_in_progress,
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

    malformed = task()
    malformed["notes"] = "Implementation:"
    with pytest.raises(DstackError, match="note"):
        task_commit_body(malformed)


def test_task_commit_body_preserves_literal_ownership_terms_in_technical_prose() -> None:
    issue = task()
    issue["notes"] = "Implementation: Parse the Task: trailer without scanning the entire commit."
    assert task_commit_body(issue) == "- Parse the Task: trailer without scanning the entire commit."


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


def test_commit_rejects_beads_state_and_unstaged_changes(git_repo: Path) -> None:
    with pytest.raises(DstackError):
        reject_beads_paths(["src/app.py", ".beads/config.yaml"])

    (git_repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    (git_repo / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=git_repo, check=True)
    with pytest.raises(DstackError, match="unstaged or untracked"):
        _commit(git_repo, build_commit_message("feat(example): change", "", "ds-123"))


def test_native_in_progress_status_is_required() -> None:
    _require_in_progress(task())
    for status in ("open", "blocked", "closed"):
        with pytest.raises(DstackError, match="in_progress"):
            _require_in_progress(task(status=status))


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

    _autosquash_correction(git_repo, target=target, message=message)

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


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root).decode().strip()


def commit_file(root: Path, name: str, content: str, subject_line: str) -> str:
    (root / name).write_text(content, encoding="utf-8")
    git(root, "add", "--", name)
    git(root, "commit", "-qm", subject_line)
    return git(root, "rev-parse", "HEAD")


def test_correction_does_not_autosquash_another_tasks_pending_fixup(git_repo: Path) -> None:
    base = git(git_repo, "rev-parse", "HEAD")
    target = commit_file(git_repo, "a", "first\n", "feat: A")
    commit_file(git_repo, "b", "first\n", "feat: B")
    commit_file(git_repo, "b", "second\n", "fixup! feat: B")
    commit_file(git_repo, "c", "third\n", "feat: C")
    (git_repo / "a").write_text("corrected\n", encoding="utf-8")
    git(git_repo, "add", "a")
    message = build_commit_message("fix(example): correct A", "- Keep technical syntax `Result<T, E>`.", "a")

    _autosquash_correction(git_repo, target=target, message=message)

    assert git(git_repo, "log", "--reverse", "--format=%s", f"{base}..HEAD").splitlines() == [
        "fix(example): correct A",
        "feat: B",
        "fixup! feat: B",
        "feat: C",
    ]
    assert (git_repo / "a").read_text() == "corrected\n"
    assert (git_repo / "b").read_text() == "second\n"
    assert (git_repo / "c").read_text() == "third\n"


def test_canonical_retry_is_a_noop_and_notes_only_correction_rewords(git_repo: Path) -> None:
    base = git(git_repo, "rev-parse", "HEAD")
    (git_repo / "a").write_text("first\n", encoding="utf-8")
    git(git_repo, "add", "a")
    message = build_commit_message("feat(example): add A", "- Add A.", "a")
    target = _commit(git_repo, message)
    descendant = commit_file(git_repo, "b", "second\n", "feat: B")

    assert subject._correct_or_reuse(git_repo, target, message) == "unchanged"
    assert git(git_repo, "rev-parse", "HEAD") == descendant
    updated = build_commit_message("fix(example): add A", "- Preserve A().", "a")
    assert subject._correct_or_reuse(git_repo, target, updated) == "corrected"
    assert git(git_repo, "log", "--format=%s", f"{base}..HEAD").splitlines() == ["feat: B", "fix(example): add A"]
    assert git(git_repo, "show", "HEAD~1:a") == "first"
    assert git(git_repo, "show", "HEAD:b") == "second"


def test_correction_refuses_published_evidence_without_mutating(git_repo: Path) -> None:
    target = commit_file(git_repo, "a", "first", "feat: A")
    git(git_repo, "update-ref", "refs/remotes/origin/feat/example", target)
    (git_repo / "a").write_text("correction")
    git(git_repo, "add", "a")
    with pytest.raises(DstackError, match="remote-tracking"):
        _autosquash_correction(git_repo, target=target, message="corrected")
    assert git(git_repo, "rev-parse", "HEAD") == target
    assert git(git_repo, "diff", "--cached", "--name-only") == "a"


def test_commit_refuses_an_existing_native_operation(git_repo: Path) -> None:
    (git_repo / ".git/rebase-merge").mkdir()
    with pytest.raises(DstackError, match="existing native Git operation"):
        subject._correct_or_reuse(git_repo, "HEAD", "anything")


@pytest.mark.parametrize("name", ["tab\tfile", "line\nfile", 'quoted"file', "cr\rfile", "\nleading", "record\x1efile"])
def test_beads_path_guard_handles_literal_git_paths(git_repo: Path, name: str) -> None:
    (git_repo / ".beads").mkdir()
    (git_repo / ".beads" / name).write_text("runtime")
    git(git_repo, "add", ".beads")
    assert subject.staged_paths(git_repo) == [f".beads/{name}"]
    with pytest.raises(DstackError, match="Beads configuration or runtime state"):
        _commit(git_repo, "feat: wrong\n\nTask: a\n")


def test_stopped_correction_keeps_native_rebase_state_and_abort_preserves_fixup(git_repo: Path) -> None:
    from dstack.core import run

    path = git_repo / "overlap.txt"
    path.write_text("first\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=git_repo)
    target = _commit(git_repo, build_commit_message("feat(example): first", "- Add first outcome.", "task-a"))
    path.write_text("second\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=git_repo)
    _commit(git_repo, build_commit_message("feat(example): second", "- Add second outcome.", "task-b"))
    path.write_text("corrected\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=git_repo)
    with pytest.raises(DstackError, match="native rebase"):
        _autosquash_correction(
            git_repo,
            target=target,
            message=build_commit_message("feat(example): corrected", "- Correct first outcome.", "task-a"),
        )
    assert run(["git", "status", "--porcelain"], cwd=git_repo).stdout
    with pytest.raises(DstackError, match="existing native Git operation"):
        _commit(git_repo, build_commit_message("feat(example): forbidden", "", "other"))
    run(["git", "rebase", "--abort"], cwd=git_repo)
    assert path.read_text(encoding="utf-8") == "corrected\n"
    assert run(["git", "log", "-1", "--format=%s"], cwd=git_repo).stdout.startswith("amend! ")
    messages = run(["git", "log", "--format=%B"], cwd=git_repo).stdout
    assert "Task: task-b" in messages
