from __future__ import annotations

import json

import pytest
from typing import TYPE_CHECKING

from dstack.core import run

if TYPE_CHECKING:
    from conftest import FeatureRepository


def test_commit_retry_reword_and_task_check_use_only_selected_evidence(public_feature: FeatureRepository) -> None:
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Add support for `Result<T, E>`.")
    for index in range(110):
        public_feature.data["issues"][f"sibling-{index}"] = {**task, "id": f"sibling-{index}", "status": "closed"}
    (public_feature.worktree / "implementation.txt").write_text("accepted outcome\n", encoding="utf-8")
    run(["git", "add", "implementation.txt"], cwd=public_feature.worktree)
    created = public_feature.invoke("commit", "--bead", "task")
    retry = public_feature.invoke("commit", "--bead", "task")
    assert retry["mode"] == "unchanged" and retry["commit"] == created["commit"]
    task["title"] = "fix: Preserve the accepted outcome"
    reworded = public_feature.invoke("commit", "--bead", "task")
    assert reworded["mode"] == "corrected"
    assert reworded["subject"] == "fix(example): preserve the accepted outcome"
    message = run(["git", "log", "-1", "--format=%B"], cwd=public_feature.worktree).stdout
    assert "`Result<T, E>`." in message
    public_feature.calls.write_text("", encoding="utf-8")
    checked = public_feature.invoke("check", "task", "--bead", "task")
    assert checked["status"] == "ok"
    calls = [json.loads(line) for line in public_feature.calls.read_text().splitlines()]
    assert not any("implementation" in call and "--parent" in call for call in calls)
    assert not any(any(arg.startswith("sibling-") for arg in call) for call in calls)


def test_docs_commit_and_final_feature_check_reject_stale_export(public_feature: FeatureRepository) -> None:
    rejected = public_feature.invoke("docs", "export-design", "--bead", "root", primary=True, expected=2)
    assert "registered feature worktree" in rejected["error"]
    assert not (public_feature.repo / "docs").exists()
    public_feature.invoke("docs", "export-design", "--bead", "root", "--scaffold")
    directory = public_feature.worktree / "docs/src/features/example"
    (directory / "index.md").write_text(
        "# Example\n\n## Overview\n\nProvide the reviewed native workflow.\n\n"
        "## User Impact\n\nUsers can resume interrupted work safely.\n\n"
        "## Implemented Design\n\n{{#include design.md}}\n",
        encoding="utf-8",
    )
    (directory / "design.md").write_text("", encoding="utf-8")
    run(["git", "add", "docs"], cwd=public_feature.worktree)
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    assert "empty" in rejected["error"]
    public_feature.invoke("docs", "export-design", "--bead", "root")
    run(["git", "add", "docs"], cwd=public_feature.worktree)
    public_feature.invoke("docs", "commit", "--bead", "root")
    public_feature.invoke("check", "feature", "--bead", "root", "--include-plan", "--require-docs")
    public_feature.data["issues"]["plan"]["design"] += "\nAccepted clarification.\n"
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    assert "differs from the native plan" in rejected["error"]
    audited = public_feature.invoke("check", "feature", "--bead", "root", "--require-docs", expected=4)
    assert audited["validation"]["feature_docs"]["status"] == "invalid"



def test_plan_check_accepts_any_issue_in_the_feature(public_feature: FeatureRepository) -> None:
    root = public_feature.invoke("check", "plan", "--bead", "root")
    descendant = public_feature.invoke("check", "plan", "--bead", "task")
    assert root["status"] == descendant["status"] == "ok"
    assert root["bead"] == descendant["bead"] == "plan"

def test_review_uses_native_dependency_policy_and_hydrates_task_intent(public_feature: FeatureRepository) -> None:
    issues = public_feature.data["issues"]
    issues["review"]["status"] = "in_progress"
    issues["approval"]["status"] = "open"
    issues["audit"]["status"] = "open"
    issues["task"].update(status="open", notes="")
    issues["task"]["dependencies"].append({"id": "external-project-task", "dependency_type": "conditional-blocks"})
    result = public_feature.invoke("check", "review", "--bead", "root")
    assert result["status"] == "ok" and result["tasks"] == ["task"]


@pytest.mark.parametrize("abbreviated_commands", [False, True])
def test_partial_id_correction_keeps_one_canonical_owner(
    public_feature: FeatureRepository,
    abbreviated_commands: bool,
) -> None:
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Deliver the accepted outcome.")
    public_feature.data["aliases"] = {"ta": "task"}
    run(["git", "config", "rebase.abbreviateCommands", str(abbreviated_commands).lower()], cwd=public_feature.worktree)
    path = public_feature.worktree / "outcome.txt"
    path.write_text("initial\n", encoding="utf-8")
    run(["git", "add", "outcome.txt"], cwd=public_feature.worktree)
    original = public_feature.invoke("commit", "--bead", "ta")
    assert original["bead"] == "task"
    assert public_feature.invoke("commit", "--bead", "ta")["mode"] == "unchanged"

    path.write_text("corrected\n", encoding="utf-8")
    run(["git", "add", "outcome.txt"], cwd=public_feature.worktree)
    task["notes"] = "Implementation: Preserve the corrected outcome."
    corrected = public_feature.invoke("commit", "--bead", "ta")
    assert corrected["mode"] == "corrected" and corrected["bead"] == "task"
    assert corrected["commit"] != original["commit"]
    messages = run(["git", "log", "main..HEAD", "--format=%B"], cwd=public_feature.worktree).stdout
    assert messages.count("Task: task") == 1 and "amend!" not in messages
    checked = public_feature.invoke("check", "task", "--bead", "ta")
    assert checked["bead"] == "task" and len(checked["evidence"]["commits"]) == 1
    assert (
        run(["git", "config", "--get", "rebase.abbreviateCommands"], cwd=public_feature.worktree).stdout.strip()
        == str(abbreviated_commands).lower()
    )


@pytest.mark.parametrize("reported_branch", ["feat/example", ""])
def test_worktree_entry_resumes_a_conflicted_correction(
    public_feature: FeatureRepository,
    reported_branch: str,
) -> None:
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Add the first outcome.")
    path = public_feature.worktree / "overlap.txt"
    path.write_text("first\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=public_feature.worktree)
    public_feature.invoke("commit", "--bead", "task")
    public_feature.commit(
        "feat(example): later behavior\n\nTask: later\n", path="overlap.txt", content="first\nlater\n"
    )
    path.write_text("corrected\nlater\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=public_feature.worktree)
    task["notes"] = "Implementation: Correct the first outcome."
    stopped = public_feature.invoke("commit", "--bead", "task", expected=2)
    assert "correction stopped" in stopped["error"]
    assert run(["git", "symbolic-ref", "--quiet", "HEAD"], cwd=public_feature.worktree, check=False).returncode
    public_feature.data["worktrees"][0]["branch"] = reported_branch
    located = public_feature.invoke("worktree", "--bead", "root", primary=True)
    assert located["worktree"] == str(public_feature.worktree)
    assert located["status"] == "recovery_required" and located["git_operation"] == "rebase-merge"
    assert not located["created_branch"] and not located["created_worktree"]
    blocked = public_feature.invoke("commit", "--bead", "task", expected=2)
    assert "finish or abort" in blocked["error"]
    # Resolve the selected correction, then preserve the later task during replay.
    path.write_text("corrected\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=public_feature.worktree)
    continued = run(
        ["git", "rebase", "--continue"], cwd=public_feature.worktree, check=False, env={"GIT_EDITOR": "true"}
    )
    assert continued.returncode != 0
    path.write_text("corrected\nlater\n", encoding="utf-8")
    run(["git", "add", "overlap.txt"], cwd=public_feature.worktree)
    run(["git", "rebase", "--continue"], cwd=public_feature.worktree, env={"GIT_EDITOR": "true"})
    public_feature.data["worktrees"][0]["branch"] = "feat/example"
    assert public_feature.invoke("worktree", "--bead", "root", primary=True)["status"] == "ok"
    checked = public_feature.invoke("check", "task", "--bead", "task")
    assert len(checked["evidence"]["commits"]) == 1
    assert path.read_text(encoding="utf-8") == "corrected\nlater\n"
    assert public_feature.invoke("commit", "--bead", "task")["mode"] == "unchanged"


def test_worktree_entry_does_not_adopt_an_arbitrary_detached_checkout(public_feature: FeatureRepository) -> None:
    run(["git", "switch", "--detach"], cwd=public_feature.worktree)
    public_feature.data["worktrees"][0]["branch"] = ""
    rejected = public_feature.invoke("worktree", "--bead", "root", primary=True, expected=2)
    assert "path exists" in rejected["error"]
    assert public_feature.worktree.is_dir()


def test_commit_rejects_mechanically_invalid_task_before_mutating_history(public_feature: FeatureRepository) -> None:
    task = public_feature.data["issues"]["task"]
    task.update(status="in_progress", notes="Implementation: Implement the accepted outcome.", design="")
    target = public_feature.worktree / "invalid-task.txt"
    target.write_text("change\n", encoding="utf-8")
    run(["git", "add", "invalid-task.txt"], cwd=public_feature.worktree)
    before = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip()
    rejected = public_feature.invoke("commit", "--bead", "task", expected=2)
    assert "implementation Bead design is empty" in rejected["error"]
    assert run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip() == before
