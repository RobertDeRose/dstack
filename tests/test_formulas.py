from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from fake_bd import validate_formula_dependencies

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "formulas" / f"{name}.formula.toml").read_text())


def test_beads_rejects_cross_kind_blocking_edges() -> None:
    epic_blocks_task = {
        "steps": [
            {"id": "workstream", "type": "epic"},
            {"id": "closeout", "type": "task", "needs": ["workstream"]},
        ]
    }
    with pytest.raises(
        RuntimeError,
        match="tasks can only block other tasks, not epics",
    ):
        validate_formula_dependencies(epic_blocks_task)

    task_blocks_epic = {
        "steps": [
            {"id": "approval", "type": "task"},
            {"id": "workstream", "type": "epic", "needs": ["approval"]},
        ]
    }
    with pytest.raises(
        RuntimeError,
        match="epics can only block other epics, not tasks",
    ):
        validate_formula_dependencies(task_blocks_epic)


def test_beads_rejects_a_formula_gate_on_an_epic() -> None:
    broken = {
        "steps": [
            {
                "id": "workstream",
                "type": "epic",
                "gate": {"type": "human", "id": "approve-work"},
            }
        ]
    }

    with pytest.raises(
        RuntimeError,
        match="epics can only block other epics, not tasks",
    ):
        validate_formula_dependencies(broken)


def test_feature_formula_uses_gated_task_milestone_and_epic_workstream() -> None:
    formula = load("dstack-feature")
    assert formula["type"] == "workflow"
    assert formula["phase"] == "liquid"
    assert formula["pour"] is True
    assert [step["id"] for step in formula["steps"]] == [
        "specification",
        "approval",
        "implementation",
        "closeout",
    ]

    specification, approval, implementation, closeout = formula["steps"]
    assert specification["type"] == "task"
    assert approval["type"] == "task"
    assert approval["needs"] == ["specification"]
    assert approval["gate"]["type"] == "human"
    assert implementation["type"] == "epic"
    assert "gate" not in implementation
    assert "needs" not in implementation
    assert closeout["needs"] == ["approval"]
    assert closeout["waits_for"] == "children-of(implementation)"
    validate_formula_dependencies(formula)


def test_alignment_formula_uses_gated_task_milestone_and_epic_workstream() -> None:
    formula = load("dstack-project-alignment")
    assert formula["type"] == "workflow"
    assert formula["phase"] == "liquid"
    assert formula["pour"] is True
    assert [step["id"] for step in formula["steps"]] == [
        "analysis",
        "approval",
        "corrections",
        "landing",
    ]

    analysis, approval, corrections, landing = formula["steps"]
    assert analysis["type"] == "task"
    assert approval["type"] == "task"
    assert approval["needs"] == ["analysis"]
    assert approval["gate"]["type"] == "human"
    assert corrections["type"] == "epic"
    assert "gate" not in corrections
    assert "needs" not in corrections
    assert landing["needs"] == ["approval"]
    assert landing["waits_for"] == "children-of(corrections)"
    validate_formula_dependencies(formula)


def test_formulas_do_not_encode_review_ceremony() -> None:
    text = "\n".join(path.read_text().lower() for path in (ROOT / "formulas").glob("*.toml"))
    for forbidden in (
        "reviewer-a",
        "reviewer-b",
        "replacement_count",
        "review_pass",
        "coordinator",
        "interaction ledger",
    ):
        assert forbidden not in text


def test_stable_formula_children_do_not_template_labels_or_metadata() -> None:
    for name in ("dstack-feature", "dstack-project-alignment"):
        formula = load(name)
        for step in formula["steps"]:
            labels = step.get("labels", [])
            metadata = step.get("metadata", {})
            rendered = repr((labels, metadata))
            assert "{{" not in rendered
            assert metadata == {"dstack_step": metadata["dstack_step"]}
