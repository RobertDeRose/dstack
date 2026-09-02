from __future__ import annotations

from copy import deepcopy

import pytest

from dstack.core import DstackError
from dstack.policy import commit_subject, documentation_impact, validate_plan_issue, validate_task_issue


def valid_plan() -> dict[str, object]:
    return {
        "id": "ds-plan",
        "issue_type": "task",
        "labels": ["dstack:step:plan"],
        "design": """## Goal
Ship deterministic planning.

## Current behavior
The agent guesses.

## Proposed behavior
The agent asks material questions.

## Repository evidence
`dstack/policy.py` validates the plan.

## Questions and answers
Question: Should ambiguity block closure?\nAnswer: Yes.

## Decisions and rationale
Use native Beads fields to avoid a second plan store.

## Compatibility and migration
Existing molecules remain historical.

## Documentation impact

### End users
Update planning usage.

### Developers
Document the formula and validators.

### Future agents
Record the authority invariant.

## Non-goals
No autonomous product-policy decisions.
""",
        "acceptance_criteria": "The plan validator accepts this complete structure.",
    }


def valid_task() -> dict[str, object]:
    return {
        "id": "ds-task",
        "title": "Preserve inbound arrival timestamps",
        "issue_type": "task",
        "labels": [
            "dstack:work:implementation",
            "dstack:commit:fix",
            "dstack:scope:coordinator",
        ],
        "description": """Implement arrival ordering.

## Documentation impact

- End-user: not affected - No observable interface or operational behavior changes.
- Developer: required - Document queue timestamp ownership in architecture guidance.
- Future-agent: required - Record the ordering invariant and rationale for later planning.
""",
        "acceptance_criteria": "Queued messages retain the timestamp captured at ingress.",
    }


def test_complete_plan_is_valid() -> None:
    result = validate_plan_issue(valid_plan())
    assert result["status"] == "ok"
    assert result["errors"] == []


def test_plan_rejects_unresolved_questions_and_placeholders() -> None:
    issue = deepcopy(valid_plan())
    issue["design"] = str(issue["design"]).replace(
        "Question: Should ambiguity block closure?\nAnswer: Yes.",
        "Status: unresolved\nTODO decide who owns authority.",
    )
    result = validate_plan_issue(issue)
    assert result["status"] == "invalid"
    assert any("unresolved" in error for error in result["errors"])
    assert any("placeholder" in error for error in result["errors"])


def test_task_requires_all_documentation_audiences() -> None:
    issue = valid_task()
    issue["description"] = str(issue["description"]).replace(
        "- Future-agent: required - Record the ordering invariant and rationale for later planning.\n",
        "",
    )
    result = validate_task_issue(issue)
    assert result["status"] == "invalid"
    assert "missing documentation-impact classification for Future-agent" in result["errors"]


def test_documentation_impact_rejects_weak_reason() -> None:
    issue = valid_task()
    issue["description"] = str(issue["description"]).replace(
        "No observable interface or operational behavior changes.",
        "None.",
    )
    _, errors = documentation_impact(issue)
    assert "documentation-impact reason for End-user is too weak" in errors


def test_commit_subject_is_derived_from_task_policy() -> None:
    assert commit_subject(valid_task()) == "fix(coordinator): preserve inbound arrival timestamps"


def test_commit_subject_rejects_embedded_conventional_prefix() -> None:
    issue = valid_task()
    issue["title"] = "fix(coordinator): preserve inbound arrival timestamps"
    with pytest.raises(DstackError, match="must not include"):
        commit_subject(issue)


def test_plan_requires_question_ledger_or_evidence_based_none_declaration() -> None:
    issue = deepcopy(valid_plan())
    issue["design"] = str(issue["design"]).replace(
        "Question: Should ambiguity block closure?\nAnswer: Yes.",
        "Repository investigation was complete.",
    )
    result = validate_plan_issue(issue)
    assert result["status"] == "invalid"
    assert any("paired `Question:`/`Answer:`" in error for error in result["errors"])

    issue["design"] = str(issue["design"]).replace(
        "Repository investigation was complete.",
        "No material questions: Existing tests and accepted decisions resolve the requested behavior.",
    )
    assert validate_plan_issue(issue)["status"] == "ok"


def test_plan_rejects_unpaired_or_unresolved_answer() -> None:
    issue = deepcopy(valid_plan())
    issue["design"] = str(issue["design"]).replace("\nAnswer: Yes.", "")
    result = validate_plan_issue(issue)
    assert any("Question without a following Answer" in error for error in result["errors"])

    issue = deepcopy(valid_plan())
    issue["design"] = str(issue["design"]).replace("Answer: Yes.", "Answer: Unknown")
    result = validate_plan_issue(issue)
    assert any("unresolved answer" in error for error in result["errors"])
