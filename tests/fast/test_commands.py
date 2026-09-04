from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dstack import commands as subject
from dstack.core import CommandResult


class WorktreeClient:
    def __init__(self, root: Path):
        self.root = root
        self.items: list[dict[str, Any]] = []

    def worktrees(self) -> list[dict[str, Any]]:
        return list(self.items)


def test_worktree_ensure_delegates_creation_and_inventory_to_beads(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = WorktreeClient(git_repo)
    original_run = subject.run
    observed: list[list[str]] = []

    def fake_run(command: list[str] | tuple[str, ...], **kwargs: Any) -> CommandResult:
        values = list(command)
        observed.append(values)
        if values[:3] == ["bd", "worktree", "create"]:
            path = Path(values[3])
            branch = values[5]
            result = original_run(["git", "worktree", "add", str(path), branch], cwd=git_repo)
            client.items = [{"path": str(path), "branch": branch}]
            return result
        if values[:3] == ["bd", "worktree", "remove"]:
            result = original_run(["git", "worktree", "remove", "--force", values[3]], cwd=git_repo, check=False)
            client.items = []
            return result
        return original_run(values, **kwargs)

    monkeypatch.setattr(subject, "run", fake_run)
    worktree, created_branch, created_worktree = subject.ensure_branch_worktree(
        client,  # type: ignore[arg-type]
        "feat/native-control-plane",
        "main",
    )
    try:
        assert created_branch is True
        assert created_worktree is True
        assert worktree.name.endswith(".feat-native-control-plane")
        assert ["bd", "worktree", "create", str(worktree), "--branch", "feat/native-control-plane"] in observed

        again = subject.ensure_branch_worktree(client, "feat/native-control-plane", "main")  # type: ignore[arg-type]
        assert again == (worktree, False, False)
    finally:
        original_run(["git", "worktree", "remove", "--force", str(worktree)], cwd=git_repo, check=False)


class GraphClient:
    def __init__(self, issues: dict[str, dict[str, Any]]):
        self.issues = issues

    def show(self, issue_id: str) -> dict[str, Any]:
        return self.issues[issue_id]

    def show_optional(self, issue_id: str) -> dict[str, Any] | None:
        return self.issues.get(issue_id)


def graph_fixture() -> tuple[GraphClient, dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    root = {
        "id": "root",
        "issue_type": "molecule",
        "labels": ["workflow:feature", "feature:example"],
        "metadata": {"dstack.base_branch": "main"},
    }
    steps = {
        "plan": {
            "id": "plan",
            "title": "Plan example",
            "description": "Original request",
            "issue_type": "task",
            "labels": ["dstack:step:plan"],
            "design": """### Goals
Deliver the workflow.

### User-facing behavior
Expose explicit lifecycle commands.

### Implemented design
Use native Beads state.

### Compatibility and constraints
Keep the native final-step identity.

### Validation
Exercise the real graph.

### Non-goals
No shadow controller.
""",
            "acceptance_criteria": "The native graph controls readiness.",
            "status": "closed",
        },
        "review": {"id": "review", "issue_type": "task", "status": "in_progress"},
        "approval": {"id": "approval", "issue_type": "task", "status": "open"},
        "implementation": {"id": "implementation", "issue_type": "epic"},
        "audit": {"id": "audit", "issue_type": "task", "status": "open"},
    }
    task = {
        "id": "task",
        "title": "Implement native workflow",
        "issue_type": "task",
        "parent": "implementation",
        "labels": ["dstack:work:implementation", "dstack:commit:feat"],
        "description": "Implement the reviewed behavior.",
        "acceptance_criteria": "The public workflow uses native readiness.",
        "dependencies": [
            {"id": "implementation", "dependency_type": "parent-child"},
            {"id": "approval", "dependency_type": "blocks"},
        ],
    }
    issues = {
        "root": root,
        **steps,
        "implementation": steps["implementation"],
        "approval": {**steps["approval"], "parent": "root"},
        "audit": {
            "id": "audit",
            "issue_type": "task",
            "parent": "root",
            "dependencies": [
                {"id": "approval", "dependency_type": "blocks"},
                {"id": "implementation", "dependency_type": "waits-for"},
            ],
        },
        "task": task,
    }
    return GraphClient(issues), root, steps, task


def test_graph_check_accepts_one_native_fan_in_and_atomic_approval_dependency() -> None:
    client, root, steps, task = graph_fixture()
    assert subject.graph_errors_for_task(client, task, root, steps, [task]) == []  # type: ignore[arg-type]


def test_graph_check_rejects_inherited_structural_label_and_redundant_audit_blocker() -> None:
    client, root, steps, task = graph_fixture()
    assert subject.implementation_task_graph_errors(task, steps) == []

    task["labels"].append("dstack:step:implementation")
    assert subject.graph_errors_for_task(client, task, root, steps, [task])  # type: ignore[arg-type]

    task["labels"].remove("dstack:step:implementation")
    client.issues["audit"]["dependencies"].append({"id": "task", "dependency_type": "blocks"})
    assert subject.graph_errors_for_task(client, task, root, steps, [task])  # type: ignore[arg-type]


def test_graph_check_rejects_nonstandard_readiness_edges() -> None:
    client, root, steps, task = graph_fixture()
    task["dependencies"].append({"id": "other", "dependency_type": "conditional-blocks"})
    client.issues["other"] = {"id": "other", "issue_type": "task", "parent": "implementation"}

    assert subject.graph_errors_for_task(client, task, root, steps, [task])  # type: ignore[arg-type]


def test_preapproval_review_accepts_complete_blocked_graph() -> None:
    client, root, steps, task = graph_fixture()

    assert (
        subject.review_graph_errors(  # type: ignore[arg-type]
            client,
            root,
            steps,
            [task],
            ready_task_ids=[],
            cycles=[],
        )
        == []
    )


def test_preapproval_review_rejects_missing_work_false_readiness_and_cycles() -> None:
    client, root, steps, task = graph_fixture()

    errors = subject.review_graph_errors(  # type: ignore[arg-type]
        client,
        root,
        steps,
        [],
        ready_task_ids=["task"],
        cycles=[{"cycle": ["task", "approval"]}],
    )

    assert "review must create at least one implementation task" in errors
    assert "implementation tasks are ready before approval: task" in errors
    assert "native Beads dependency graph contains a cycle" in errors
