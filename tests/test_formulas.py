from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from fake_bd import validate_formula_dependencies

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "formulas" / f"{name}.formula.toml").read_text())


def assert_no_epic_blocks_task(formula: dict) -> None:
    steps = {step["id"]: step for step in formula["steps"]}
    for dependent in steps.values():
        for blocker_id in (
            *dependent.get("needs", []),
            *dependent.get("depends_on", []),
        ):
            blocker = steps[blocker_id]
            assert not (
                blocker.get("type", "task") == "epic"
                and dependent.get("type", "task") != "epic"
            ), f"epic {blocker_id} cannot ordinarily block task {dependent['id']}"


def test_beads_rejects_epic_as_an_ordinary_task_blocker() -> None:
    broken = {
        "steps": [
            {"id": "workstream", "type": "epic"},
            {"id": "closeout", "type": "task", "needs": ["workstream"]},
        ]
    }

    with pytest.raises(
        RuntimeError,
        match="epics can only block other epics, not tasks",
    ):
        validate_formula_dependencies(broken)


def test_feature_formula_is_small_native_workflow() -> None:
    formula = load("dstack-feature")
    assert formula["type"] == "workflow"
    assert formula["phase"] == "liquid"
    assert formula["pour"] is True
    assert [step["id"] for step in formula["steps"]] == [
        "specification",
        "implementation",
        "closeout",
    ]
    implementation = formula["steps"][1]
    closeout = formula["steps"][2]
    assert implementation["type"] == "epic"
    assert implementation["gate"]["type"] == "human"
    assert implementation["needs"] == ["specification"]
    assert closeout["needs"] == ["specification"]
    assert closeout["waits_for"] == "children-of(implementation)"
    assert_no_epic_blocks_task(formula)


def test_alignment_formula_is_small_native_workflow() -> None:
    formula = load("dstack-project-alignment")
    assert formula["type"] == "workflow"
    assert formula["phase"] == "liquid"
    assert formula["pour"] is True
    assert [step["id"] for step in formula["steps"]] == [
        "analysis",
        "corrections",
        "landing",
    ]
    corrections = formula["steps"][1]
    landing = formula["steps"][2]
    assert corrections["type"] == "epic"
    assert corrections["gate"]["type"] == "human"
    assert corrections["needs"] == ["analysis"]
    assert landing["needs"] == ["analysis"]
    assert landing["waits_for"] == "children-of(corrections)"
    assert_no_epic_blocks_task(formula)


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
