from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SKILLS = {
    "dstack-beads-audit-feature",
    "dstack-beads-implement",
    "dstack-beads-plan-feature",
    "dstack-beads-review-plan",
}
REQUIRED_PROMPTS = {"audit-feature.md", "implement.md", "plan-feature.md", "review-plan.md"}
REQUIRED_PACKAGE_ASSETS = {
    "assets/APPEND_SYSTEM.md",
    "assets/formulas/dstack-feature.formula.toml",
    *(f"assets/prompts/{name}" for name in REQUIRED_PROMPTS),
    *(f"assets/skills/{name}/SKILL.md" for name in REQUIRED_SKILLS),
}


def test_package_configuration_covers_runtime_assets() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = tuple(payload["tool"]["setuptools"]["package-data"]["dstack"])
    uncovered = {
        asset
        for asset in REQUIRED_PACKAGE_ASSETS
        if not any(PurePosixPath(asset).match(pattern) for pattern in patterns)
    }
    assert uncovered == set()


def test_required_targeted_resources_exist() -> None:
    skills = {path.parent.name for path in (ROOT / "dstack/assets/skills").glob("*/SKILL.md")}
    prompts = {path.name for path in (ROOT / "dstack/assets/prompts").glob("*.md")}
    assert REQUIRED_SKILLS <= skills
    assert REQUIRED_PROMPTS <= prompts


def test_repository_formula_matches_packaged_formula() -> None:
    assert (ROOT / ".beads/formulas/dstack-feature.formula.toml").read_bytes() == (
        ROOT / "dstack/assets/formulas/dstack-feature.formula.toml"
    ).read_bytes()
