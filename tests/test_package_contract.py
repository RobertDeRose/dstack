from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_package_version_and_resources() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    assert package["name"] == "dstack"
    assert package["version"] == "0.4.3"
    assert package["pi"]["skills"] == ["./skills"]
    assert package["pi"]["prompts"] == ["./prompts"]


def test_all_skill_and_prompt_frontmatter_parses() -> None:
    for path in [*ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("prompts/*.md")]:
        text = path.read_text()
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert isinstance(yaml.safe_load(frontmatter), dict)


def test_core_principles_and_architecture_are_first_class_docs() -> None:
    principles = (ROOT / "docs/core-principles.md").read_text()
    architecture = (ROOT / "docs/architecture.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    for phrase in (
        "KISS and YAGNI",
        "Never store Git commit hashes in Beads",
        "Documentation is not workflow state",
    ):
        assert phrase in principles
    assert "stateless dstackctl" in architecture
    assert "docs/core-principles.md" in agents
    assert "post-merge bookkeeping commit" in agents


def test_skills_are_short_and_decision_oriented() -> None:
    for path in ROOT.glob("skills/*/SKILL.md"):
        lines = path.read_text().splitlines()
        assert len(lines) <= 100, f"{path} is {len(lines)} lines"
        assert "Read the `dstack-beads-core` skill and every core reference" not in path.read_text()


def test_no_git_sha_mapping_or_shadow_state_contract() -> None:
    text = "\n".join(path.read_text() for path in ROOT.glob("skills/**/*.md"))
    assert "external_ref=git" not in text
    assert "reviewer replacement" not in text.casefold()
    assert "dstack:delivery-ready" not in text
    assert "tasks.md" not in text or "Do not create `tasks.md`" in text
    assert not (ROOT / "skills/dstack-beads-core/scripts/git_evidence.py").exists()


def test_uv_run_has_default_development_dependencies() -> None:
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = set(project["dependency-groups"]["dev"])
    assert any(item.startswith("pytest") for item in dependencies)
    assert any(item.startswith("PyYAML") for item in dependencies)
