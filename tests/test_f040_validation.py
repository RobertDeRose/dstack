"""Focused contract tests for F040 generated GitHub validation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from copier import run_copy

from tests.support import run_command


DATA = {
    "project_name": "Validation Example",
    "project_slug": "validation-example",
    "project_purpose": "Validate the generated project.",
    "project_users": "Project contributors.",
    "project_scope": "Repository validation.",
    "project_boundaries": "Deployment remains separate.",
    "project_kind": "library",
    "language_profiles": ["other"],
    "repository_default_branch": "main",
    "include_readme": True,
}


@pytest.mark.integration
@pytest.mark.parametrize("entrypoint", ["repository", "bundled"])
def test_generated_validation_reuses_locked_local_check(
    tagged_template_source: Path,
    tmp_path: Path,
    entrypoint: str,
) -> None:
    source = tagged_template_source if entrypoint == "repository" else tagged_template_source / "skills/setup-project"
    project = tmp_path / entrypoint
    run_copy(str(source), project, data=DATA, defaults=True, quiet=True, unsafe=False)

    workflow = project / ".github/workflows/validate.yml"
    text = workflow.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)

    assert set(parsed[True]) == {"push", "pull_request"}
    assert parsed["permissions"] == {}
    job = parsed["jobs"]["validate"]
    assert job["permissions"] == {"contents": "read"}
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 20
    steps = job["steps"]
    assert steps[0]["uses"] == "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
    assert steps[0]["with"]["persist-credentials"] is False
    assert steps[1]["uses"] == "jdx/mise-action@5228313ee0372e111a38da051671ca30fc5a96db"
    assert steps[1]["with"]["install"] is False
    assert [step.get("run") for step in steps if "run" in step] == ["mise install --locked", "mise run check"]
    assert all(step.get("env") == {"MISE_GLOBAL_CONFIG_FILE": "/dev/null"} for step in steps if "run" in step)
    assert "mise lock" not in text
    assert len(re.findall(r"uses: [^@]+@[0-9a-f]{40}", text)) == 2
    assert "GitHub validation" in (project / "docs/src/development/tooling.md").read_text(encoding="utf-8")

    run_command(["actionlint", str(workflow)], cwd=project)
    run_command(["zizmor", "--no-progress", str(workflow)], cwd=project)
