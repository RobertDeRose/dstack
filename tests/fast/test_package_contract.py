from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_package_declares_all_agent_assets() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = set(payload["tool"]["setuptools"]["package-data"]["dstack"])
    assert "assets/formulas/*.toml" in patterns
    assert "assets/prompts/*.md" in patterns
    assert "assets/skills/*/*.md" in patterns


def test_exact_targeted_resources_are_packaged() -> None:
    skills = {path.parent.name for path in (ROOT / "dstack/assets/skills").glob("*/SKILL.md")}
    prompts = {path.name for path in (ROOT / "dstack/assets/prompts").glob("*.md")}
    assert skills == {
        "dstack-beads-audit-feature",
        "dstack-beads-implement",
        "dstack-beads-plan-feature",
        "dstack-beads-review-plan",
    }
    assert prompts == {"audit-feature.md", "implement.md", "plan-feature.md", "review-plan.md"}


def test_repository_formula_matches_packaged_formula() -> None:
    assert (ROOT / ".beads/formulas/dstack-feature.formula.toml").read_bytes() == (
        ROOT / "dstack/assets/formulas/dstack-feature.formula.toml"
    ).read_bytes()
