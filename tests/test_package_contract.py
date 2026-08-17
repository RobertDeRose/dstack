from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_package_registers_direct_prompt_commands_and_skills() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    assert package["name"] == "dstack"
    assert package["pi"] == {"skills": ["./skills"], "prompts": ["./prompts"]}
    commands = {
        "setup-project",
        "plan-features",
        "adopt-feature",
        "start-feature",
        "review-feature-spec",
        "implement-feature",
        "close-feature",
        "project-alignment-review",
        "project-alignment-execute",
        "project-alignment-land",
    }
    assert commands == {path.stem for path in (ROOT / "prompts").glob("*.md")}
    expected_skills = {f"dstack-beads-{command}" for command in commands}
    expected_skills.add("dstack-beads-core")
    assert expected_skills == {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}


def test_no_name_typo_or_old_workflow_files() -> None:
    typo = "ds" + "tck"
    tracked = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and path.suffix not in {".pyc"}
    ]
    for path in tracked:
        assert typo not in path.name.casefold()
        assert typo not in path.read_text(errors="ignore").casefold()
    for filename in (
        "tasks.md",
        "PIPELINE_STATE.md",
        "IMPLEMENTATION_PLAN.md",
        "REVIEW-STATE.md",
    ):
        assert not any(path.name == filename for path in ROOT.rglob("*"))


def test_setup_helper_does_not_execute_workflows() -> None:
    source = (ROOT / "skills" / "dstack-beads-core" / "scripts" / "setup.py").read_text()
    for forbidden in (
        "bd ready",
        "--claim",
        "bd worktree",
        "bd gate resolve",
        "bd close",
        "bd create",
    ):
        assert forbidden not in source


def _parse_frontmatter(path: Path) -> dict[str, object]:
    import yaml

    text = path.read_text()
    assert text.startswith("---\n")
    _, frontmatter, _ = text.split("---", 2)
    parsed = yaml.safe_load(frontmatter)
    assert isinstance(parsed, dict)
    return parsed


def test_all_skill_and_prompt_frontmatter_is_valid_yaml() -> None:
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        metadata = _parse_frontmatter(path)
        assert metadata["name"] == path.parent.name
        assert isinstance(metadata["description"], str)
        assert metadata["description"].strip()

    for path in sorted((ROOT / "prompts").glob("*.md")):
        metadata = _parse_frontmatter(path)
        assert isinstance(metadata["description"], str)
        assert metadata["description"].strip()


def test_prompt_aliases_target_namespaced_package_skills() -> None:
    for path in sorted((ROOT / "prompts").glob("*.md")):
        expected = f"dstack-beads-{path.stem}"
        assert f"Load and follow the `{expected}` skill." in path.read_text()


def test_setup_preflights_isolated_formula_pour_before_target_copy() -> None:
    source = (ROOT / "skills" / "dstack-beads-core" / "scripts" / "setup.py").read_text()
    assert "def validate_formula_bundle" in source
    assert "def pour_formula_preflight" in source
    install_body = source[source.index("def install("):source.index("def doctor(")]
    assert install_body.index("validate_formula_bundle(source_dir)") < install_body.index("copy_formula(")
    assert "restore_formula_files(snapshots)" in source
    assert '"--persist"' not in source
