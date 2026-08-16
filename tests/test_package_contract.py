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
        "start-feature",
        "review-feature-spec",
        "implement-feature",
        "close-feature",
        "project-alignment-review",
        "project-alignment-execute",
        "project-alignment-land",
    }
    assert commands == {path.stem for path in (ROOT / "prompts").glob("*.md")}
    assert commands <= {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}


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
    source = (ROOT / "skills" / "dstack-core" / "scripts" / "setup.py").read_text()
    for forbidden in (
        "bd ready",
        "--claim",
        "bd worktree",
        "bd gate resolve",
        "bd close",
        "bd create",
    ):
        assert forbidden not in source
