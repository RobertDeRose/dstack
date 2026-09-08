from __future__ import annotations

from typing import Any

from dstack.git_ops import canonical_task_message
from dstack.task_validation import validate_implementation_task


def task_fixture() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    task = {
        "id": "task",
        "title": "Implement native recovery",
        "issue_type": "task",
        "status": "closed",
        "parent": "implementation",
        "labels": ["dstack:work:implementation"],
        "description": "Implement the reviewed recovery behavior.",
        "design": "Use only native Git and Beads state.",
        "acceptance_criteria": "Interrupted work resumes without a shadow journal.",
        "notes": "Implementation: Resume interrupted native work.",
        "dependencies": [
            {"id": "implementation", "dependency_type": "parent-child"},
            {"id": "approval", "dependency_type": "blocks"},
        ],
    }
    steps = {
        "implementation": {"id": "implementation", "issue_type": "epic"},
        "approval": {"id": "approval", "issue_type": "task"},
    }
    return task, steps


def record_for(task: dict[str, Any]) -> dict[str, Any]:
    message = canonical_task_message(task, "example").rstrip("\n")
    subject, body = message.split("\n\n", 1)
    return {
        "commit": "deadbeef",
        "subject": subject,
        "body": body,
        "paths": ["src/recovery.py"],
        "footer_ids": ("task",),
        "legacy_footer_ids": (),
    }


def test_shared_task_validation_accepts_one_canonical_commit() -> None:
    task, steps = task_fixture()
    result = validate_implementation_task(task, steps, "example", [record_for(task)])
    assert result["errors"] == []
    assert result["commits"] == [{"commit": "deadbeef", "subject": "feat(example): implement native recovery"}]


def test_no_repository_change_cannot_retain_canonical_commit() -> None:
    task, steps = task_fixture()
    record = record_for(task)
    task["notes"] = "No repository change: existing behavior already satisfies the accepted outcome"
    result = validate_implementation_task(task, steps, "example", [record])
    assert any("must own 0 canonical commit" in error for error in result["errors"])
