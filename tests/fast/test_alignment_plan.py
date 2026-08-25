from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))

from dstack_alignment_plan import (  # noqa: E402
    SCHEMA,
    canonical_plan_bytes,
    canonicalize_plan,
    plan_digest,
    verify_correction_graph,
)
from dstacklib import DstackError  # noqa: E402


BASELINE = "a" * 40


def plan(**overrides):
    value = {
        "schema": SCHEMA,
        "baseline_commit": BASELINE,
        "scope": "repository",
        "findings": [{"title": "Finding", "evidence": "Evidence", "rationale": "Reason"}],
        "accepted_corrections": [
            {
                "title": "Correction",
                "description": "Description",
                "acceptance": "Acceptance",
                "priority": 1,
                "depends_on": [],
            }
        ],
        "rejected_corrections": [],
        "validation_expectations": ["Tests"],
        "documentation_impact": {
            "end_user_operator": ["CLI"],
            "developer_reviewer": [],
            "future_auditor": [],
        },
        "deferred_findings": [],
        "accepted_risks": [],
    }
    value.update(overrides)
    return value


def test_canonical_plan_normalizes_order_unicode_and_line_endings():
    left = plan(scope="e\u0301\r\n", validation_expectations=["B", "A"])
    right = plan(scope="é\n", validation_expectations=["A", "B"])
    assert canonical_plan_bytes(left) == canonical_plan_bytes(right)
    assert plan_digest(left) == plan_digest(right)


def test_canonical_plan_rejects_unknown_fields_and_bad_graph():
    with pytest.raises(DstackError, match="unknown"):
        canonicalize_plan(plan(extra=True))
    with pytest.raises(DstackError, match="priority"):
        canonicalize_plan(
            plan(
                accepted_corrections=[
                    {
                        "title": "Correction",
                        "description": "D",
                        "acceptance": "A",
                        "priority": True,
                        "depends_on": [],
                    }
                ]
            )
        )
    with pytest.raises(DstackError, match="unknown title"):
        canonicalize_plan(
            plan(
                accepted_corrections=[
                    {
                        "title": "Correction",
                        "description": "D",
                        "acceptance": "A",
                        "priority": 1,
                        "depends_on": ["Missing"],
                    }
                ]
            )
        )


class GraphClient:
    def __init__(self, correction):
        self.correction = correction

    def show(self, issue_id):
        if issue_id == "approval":
            return {"id": "approval", "status": "open"}
        raise AssertionError(issue_id)

    def children(self, parent_id):
        assert parent_id == "corrections"
        return [self.correction]


def graph_view():
    return {
        "steps": {"approval": {"id": "approval"}, "corrections": {"id": "corrections"}},
    }


def graph_plan(extra_relationships=None):
    item = {
        "id": "correction-id",
        "title": "Correction",
        "description": "Description",
        "acceptance_criteria": "Acceptance",
        "priority": 1,
        "parent": "corrections",
        "labels": ["dstack:work:correction"],
        "dependencies": [
            {"type": "parent-child", "depends_on_id": "corrections"},
            {"type": "blocks", "depends_on_id": "approval"},
        ],
    }
    if extra_relationships:
        item["dependencies"].extend(extra_relationships)
    return GraphClient(item), graph_view(), plan()


def test_correction_graph_rejects_additional_nonblocking_relationship():
    client, view, value = graph_plan([{"type": "relates-to", "depends_on_id": "context"}])
    with pytest.raises(DstackError, match="graph changed"):
        verify_correction_graph(client, view, value)


def test_correction_graph_accepts_exact_parent_and_blockers():
    client, view, value = graph_plan()
    verify_correction_graph(client, view, value)


def test_canonical_plan_rejects_cycles_and_non_full_baseline():
    corrections = [
        {"title": "A", "description": "D", "acceptance": "A", "priority": 1, "depends_on": ["B"]},
        {"title": "B", "description": "D", "acceptance": "A", "priority": 1, "depends_on": ["A"]},
    ]
    with pytest.raises(DstackError, match="cycle"):
        canonicalize_plan(plan(accepted_corrections=corrections))
    with pytest.raises(DstackError, match="full Git"):
        canonicalize_plan(plan(baseline_commit="abc"))
