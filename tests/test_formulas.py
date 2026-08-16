from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "formulas" / f"{name}.formula.toml").read_text())


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
    assert closeout["needs"] == ["implementation"]
    assert closeout["waits_for"] == "children-of(implementation)"


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
    assert landing["needs"] == ["corrections"]
    assert landing["waits_for"] == "children-of(corrections)"


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
