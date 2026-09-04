from __future__ import annotations

import pytest

from dstack.core import DstackError
from dstack.policy import PLAN_SECTIONS, commit_subject, validate_plan_issue, validate_task_issue


PLAN_CONTENT = {
    "Goals": "Ship deterministic planning.",
    "User-facing behavior": "The planning skill asks focused product questions.",
    "Implemented design": "Beads stores the request, design, acceptance criteria, and comments.",
    "Compatibility and constraints": "Existing repositories remain native Beads projects.",
    "Validation": "Public checks exercise the completed workflow graph.",
    "Non-goals": "No custom scheduler or lifecycle database.",
}


def plan_design(*, level: int = 3, omit: str | None = None) -> str:
    marker = "#" * level
    return "\n\n".join(f"{marker} {section}\n{content}" for section, content in PLAN_CONTENT.items() if section != omit)


def valid_plan(**kwargs: object) -> dict[str, object]:
    return {
        "id": "ds-plan",
        "title": "Plan deterministic workflow",
        "description": "Original user request: make workflow state native.",
        "issue_type": "task",
        "labels": ["dstack:step:plan"],
        "design": plan_design(**kwargs),
        "acceptance_criteria": "The native graph exposes each reviewed step in dependency order.",
    }


def valid_task() -> dict[str, object]:
    return {
        "id": "ds-task",
        "title": "Preserve inbound arrival timestamps",
        "issue_type": "task",
        "labels": ["dstack:work:implementation"],
        "description": (
            "- Implement arrival ordering through the public queue interface.\n"
            "- Cover timestamp retention through observable tests."
        ),
        "acceptance_criteria": "Queued messages retain the timestamp captured at ingress.",
    }


def legacy_commit_task() -> dict[str, object]:
    task = valid_task()
    task["labels"] = [
        "dstack:work:implementation",
        "dstack:commit:fix",
        "dstack:scope:coordinator",
    ]
    return task


def test_complete_publishable_plan_is_valid() -> None:
    result = validate_plan_issue(valid_plan())
    assert result["status"] == "ok"
    assert result["errors"] == []
    assert result["required_sections"] == list(PLAN_SECTIONS)


def test_plan_requires_level_three_publishable_sections() -> None:
    wrong_level = validate_plan_issue(valid_plan(level=2))
    missing = validate_plan_issue(valid_plan(omit="Validation"))

    assert wrong_level["status"] == "invalid"
    assert any("level-three" in error for error in wrong_level["errors"])
    assert "missing plan section: Validation" in missing["errors"]


def test_plan_rejects_sections_outside_the_publishable_set() -> None:
    issue = valid_plan()
    issue["design"] = f"{issue['design']}\n\n### Repository evidence\nInternal planning notes."

    result = validate_plan_issue(issue)

    assert result["status"] == "invalid"
    assert "plan headings must be exactly the publishable section set" in result["errors"]


def test_plan_rejects_missing_request_acceptance_and_placeholders() -> None:
    issue = valid_plan()
    issue["description"] = ""
    issue["acceptance_criteria"] = "TODO"
    result = validate_plan_issue(issue)

    assert result["status"] == "invalid"
    assert "native Beads description is empty" in result["errors"]
    assert "acceptance criteria contain a placeholder or unchecked item" in result["errors"]


def test_task_requires_only_native_shape_and_observable_acceptance() -> None:
    assert validate_task_issue(valid_task()) == {
        "status": "ok",
        "bead": "ds-task",
        "errors": [],
    }


def test_task_accepts_prose_planned_description_without_commit_labels() -> None:
    issue = valid_task()
    issue["description"] = "Implement arrival ordering through the public queue interface."
    issue["labels"] = ["dstack:work:implementation"]

    assert validate_task_issue(issue) == {
        "status": "ok",
        "bead": "ds-task",
        "errors": [],
    }


def test_task_rejects_malformed_execution_notes() -> None:
    issue = valid_task()
    issue["notes"] = "Implementation:"

    result = validate_task_issue(issue)

    assert result["status"] == "invalid"
    assert any("implementation note" in error for error in result["errors"])


def test_task_rejects_non_action_implementation_notes() -> None:
    issue = valid_task()
    issue["notes"] = "Implementation: The output is compact."

    result = validate_task_issue(issue)

    assert result["status"] == "invalid"
    assert "implementation note must start with a clear action verb" in result["errors"]


def test_task_rejects_conflicting_change_modes() -> None:
    issue = valid_task()
    issue["notes"] = "No repository change: The outcome is documentation-only.\nImplementation: Add a fixture."

    result = validate_task_issue(issue)

    assert result["status"] == "invalid"
    assert "implementation notes cannot be combined with a No repository change reason" in result["errors"]


def test_task_tolerates_legacy_bootstrap_metadata_without_requiring_it() -> None:
    issue = legacy_commit_task()
    issue["description"] = "Legacy prose summary."
    assert validate_task_issue(issue)["status"] == "ok"


def test_task_requires_a_native_task_issue_type() -> None:
    issue = valid_task()
    issue["issue_type"] = "decision"

    result = validate_task_issue(issue)

    assert result["status"] == "invalid"
    assert "implementation Bead must be a task issue" in result["errors"]


def test_commit_subject_is_fixed_by_feature_slug_and_task_title() -> None:
    assert commit_subject(valid_task(), "native-workflow") == (
        "feat(native-workflow): preserve inbound arrival timestamps"
    )

    issue = valid_task()
    issue["title"] = "fix(coordinator): preserve inbound arrival timestamps"
    with pytest.raises(DstackError):
        commit_subject(issue, "native-workflow")
