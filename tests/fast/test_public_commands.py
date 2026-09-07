from __future__ import annotations

import json
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


def test_docs_commit_and_final_audit_reject_stale_export(public_feature: FeatureRepository) -> None:
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
    public_feature.invoke("audit", "--bead", "root", "--include-plan", "--require-docs")
    public_feature.data["issues"]["plan"]["design"] += "\nAccepted clarification.\n"
    rejected = public_feature.invoke("docs", "commit", "--bead", "root", expected=2)
    assert "differs from the native plan" in rejected["error"]
    audited = public_feature.invoke("audit", "--bead", "root", "--require-docs", expected=4)
    assert audited["validation"]["feature_docs"]["status"] == "invalid"


def test_review_uses_native_dependency_policy_and_hydrates_task_intent(public_feature: FeatureRepository) -> None:
    issues = public_feature.data["issues"]
    issues["review"]["status"] = "in_progress"
    issues["approval"]["status"] = "open"
    issues["audit"]["status"] = "open"
    issues["task"].update(status="open", notes="")
    issues["task"]["dependencies"].append({"id": "external-project-task", "dependency_type": "conditional-blocks"})
    result = public_feature.invoke("check", "review", "--bead", "root")
    assert result["status"] == "ok" and result["tasks"] == ["task"]
