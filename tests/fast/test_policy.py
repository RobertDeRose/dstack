from __future__ import annotations

from collections.abc import Iterable

import pytest

from dstack.core import DstackError
from dstack.policy import PLAN_SECTIONS, commit_subject, validate_plan_issue, validate_task_issue


PLAN_CONTENT = {
    "Goal": "Ship deterministic planning.",
    "Current behavior": "The agent guesses.",
    "Proposed behavior": "The agent asks material questions.",
    "Repository evidence": "`dstack/policy.py` validates the plan.",
    "Questions and answers": "Question: Should ambiguity block closure?\nAnswer: Yes.",
    "Decisions and rationale": "Use native Beads fields to avoid a second plan store.",
    "Compatibility and migration": "Existing molecules remain historical.",
    "Documentation impact": """### End users
Update planning usage.

### Developers
Document the formula and validators.

### Future agents
Record the authority invariant.""",
    "Non-goals": "No autonomous product-policy decisions.",
}

DOCUMENTATION_LINES = (
    "- End-user: not affected - No observable interface or operational behavior changes.",
    "- Developer: required - Document queue timestamp ownership in architecture guidance.",
    "- Future-agent: required - Record the ordering invariant and rationale for later planning.",
)


def plan_design(
    *,
    questions: str | None = None,
    order: Iterable[str] = PLAN_SECTIONS,
    content_overrides: dict[str, str] | None = None,
) -> str:
    content = dict(PLAN_CONTENT)
    if questions is not None:
        content["Questions and answers"] = questions
    if content_overrides:
        content.update(content_overrides)
    return "\n\n".join(f"## {section}\n{content[section]}" for section in order) + "\n"


def valid_plan(**kwargs: object) -> dict[str, object]:
    return {
        "id": "ds-plan",
        "issue_type": "task",
        "labels": ["dstack:step:plan"],
        "design": plan_design(**kwargs),
        "acceptance_criteria": "The plan validator accepts this complete structure.",
    }


def valid_task(*, documentation_lines: Iterable[str] = DOCUMENTATION_LINES) -> dict[str, object]:
    matrix = "\n".join(documentation_lines)
    return {
        "id": "ds-task",
        "title": "Preserve inbound arrival timestamps",
        "issue_type": "task",
        "labels": [
            "dstack:work:implementation",
            "dstack:commit:fix",
            "dstack:scope:coordinator",
        ],
        "description": f"""Implement arrival ordering.

## Documentation impact

{matrix}
""",
        "acceptance_criteria": "Queued messages retain the timestamp captured at ingress.",
    }


def test_complete_plan_is_valid() -> None:
    result = validate_plan_issue(valid_plan())
    assert result["status"] == "ok"
    assert result["errors"] == []


def test_plan_validation_ignores_prose_wording_wrapping_and_section_order() -> None:
    reordered = tuple(reversed(PLAN_SECTIONS))
    issue = valid_plan(
        order=reordered,
        content_overrides={
            "Goal": "Ship deterministic planning while preserving\nrepository authority and compact agent context.",
            "Current behavior": "Planning behavior is inconsistent across agents.",
            "Proposed behavior": "Validate the observable Beads record instead of copied skill wording.",
        },
    )
    assert validate_plan_issue(issue)["status"] == "ok"


def test_plan_rejects_unresolved_questions_and_placeholders() -> None:
    issue = valid_plan(questions="Status: unresolved\nTODO decide who owns authority.")
    result = validate_plan_issue(issue)
    assert result["status"] == "invalid"
    assert len(result["errors"]) >= 2


def test_task_requires_all_documentation_audiences() -> None:
    issue = valid_task(documentation_lines=DOCUMENTATION_LINES[:-1])
    result = validate_task_issue(issue)
    assert result["status"] == "invalid"
    assert set(result["documentation_impact"]) == {"End-user", "Developer"}


def test_documentation_impact_rejects_weak_reason() -> None:
    lines = (
        "- End-user: not affected - None.",
        DOCUMENTATION_LINES[1],
        DOCUMENTATION_LINES[2],
    )
    result = validate_task_issue(valid_task(documentation_lines=lines))
    assert result["status"] == "invalid"
    assert result["documentation_impact"]["End-user"] == {
        "status": "not affected",
        "reason": "None.",
    }


def test_commit_subject_is_derived_from_task_policy() -> None:
    assert commit_subject(valid_task()) == "fix(coordinator): preserve inbound arrival timestamps"


def test_commit_subject_rejects_embedded_conventional_prefix() -> None:
    issue = valid_task()
    issue["title"] = "fix(coordinator): preserve inbound arrival timestamps"
    with pytest.raises(DstackError):
        commit_subject(issue)


def test_plan_requires_question_ledger_or_evidence_based_none_declaration() -> None:
    assert validate_plan_issue(valid_plan(questions="Repository investigation was complete."))["status"] == "invalid"
    assert (
        validate_plan_issue(
            valid_plan(
                questions=(
                    "No material questions: Existing tests and accepted decisions resolve the requested behavior."
                )
            )
        )["status"]
        == "ok"
    )


def test_plan_rejects_unpaired_or_unresolved_answer() -> None:
    assert validate_plan_issue(valid_plan(questions="Question: Should ambiguity block closure?"))["status"] == "invalid"
    assert (
        validate_plan_issue(valid_plan(questions="Question: Should ambiguity block closure?\nAnswer: Unknown"))[
            "status"
        ]
        == "invalid"
    )
