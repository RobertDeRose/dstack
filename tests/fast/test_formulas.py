from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "formulas" / f"{name}.formula.toml").read_text())


def test_feature_formula_is_minimal_and_uses_native_fan_in() -> None:
    formula = load("dstack-feature")
    assert formula["version"] == 8
    assert set(formula["vars"]) == {"feature_title", "feature_slug", "design_path"}
    assert [step["id"] for step in formula["steps"]] == [
        "specification",
        "approval",
        "implementation",
        "closeout",
    ]
    steps = {step["id"]: step for step in formula["steps"]}
    assert steps["approval"]["gate"]["type"] == "human"
    assert steps["implementation"]["type"] == "epic"
    assert steps["closeout"]["waits_for"] == "children-of(implementation)"
    assert sum(step["id"] == "closeout" for step in formula["steps"]) == 1
    assert "single final reconciliation" in formula["description"]
    assert all("metadata" not in step for step in formula["steps"])
    assert all("{{" not in repr(step.get("labels", [])) for step in formula["steps"])


def test_alignment_formula_is_minimal_and_uses_native_fan_in() -> None:
    formula = load("dstack-project-alignment")
    assert formula["version"] == 8
    assert set(formula["vars"]) == {"audit_title", "audit_slug", "scope"}
    steps = {step["id"]: step for step in formula["steps"]}
    assert set(steps) == {"analysis", "approval", "corrections", "landing"}
    assert steps["approval"]["gate"]["type"] == "human"
    assert steps["corrections"]["type"] == "epic"
    assert steps["landing"]["waits_for"] == "children-of(corrections)"
    assert sum(step["id"] == "landing" for step in formula["steps"]) == 1
    assert "single final reconciliation" in formula["description"]
    assert all("metadata" not in step for step in formula["steps"])
