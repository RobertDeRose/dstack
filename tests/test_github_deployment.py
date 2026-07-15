"""Focused contract tests for generated Pages deployment."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from copier import run_copy

from tests.support import run_command


DATA = {
    "project_name": "Pages Example",
    "project_slug": "pages-example",
    "project_purpose": "Publish project documentation.",
    "project_users": "Project contributors.",
    "project_scope": "Documentation deployment.",
    "project_boundaries": "Application deployment remains separate.",
    "project_kind": "documentation",
    "language_profiles": ["other"],
    "repository_default_branch": 'release/"stable"',
    "include_readme": True,
}
GATE = "vars.DOCS_DEPLOYMENT_ENABLED == 'true'"


@pytest.mark.integration
@pytest.mark.parametrize("entrypoint", ["repository", "bundled"])
def test_generated_pages_deployment_is_branch_restricted_and_gated(
    tagged_template_source: Path,
    tmp_path: Path,
    entrypoint: str,
) -> None:
    source = tagged_template_source if entrypoint == "repository" else tagged_template_source / "skills/setup-project"
    project = tmp_path / entrypoint
    run_copy(str(source), project, data=DATA, defaults=True, quiet=True, unsafe=False)

    workflow = project / ".github/workflows/docs.yml"
    text = workflow.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)

    assert parsed[True] == {"push": {"branches": ['release/"stable"']}, "workflow_dispatch": None}
    assert "pull_request" not in text
    assert "paths" not in parsed[True]["push"]
    assert parsed["permissions"] == {}
    assert parsed["concurrency"] == {"group": "pages", "cancel-in-progress": False}

    build = parsed["jobs"]["build"]
    deploy = parsed["jobs"]["deploy"]
    assert build["if"] == GATE
    assert deploy["if"] == GATE
    assert build["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert deploy["needs"] == "build"
    assert deploy["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }

    steps = build["steps"]
    assert [step.get("uses") for step in steps if "uses" in step] == [
        "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10",
        "jdx/mise-action@5228313ee0372e111a38da051671ca30fc5a96db",
        "actions/configure-pages@983d7736d9b0ae728b81ab479565c72886d7745b",
        "actions/upload-pages-artifact@7b1f4a764d45c48632c6b24a0339c27f5614fb0b",
    ]
    assert steps[0]["with"]["persist-credentials"] is False
    assert steps[1]["with"] == {"install": False, "cache": False}
    assert [step.get("run") for step in steps if "run" in step] == ["mise install --locked", "mise run docs:build"]
    assert all(
        step.get("env") == {"MISE_IGNORED_CONFIG_PATHS": "/home/runner/.config/mise/config.toml"}
        for step in steps
        if "run" in step
    )
    assert steps[-1]["with"]["path"] == "docs/book"
    assert deploy["steps"] == [
        {
            "name": "Deploy Pages",
            "id": "deployment",
            "uses": "actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
        }
    ]
    assert len(re.findall(r"uses: [^@]+@[0-9a-f]{40}", text)) == 5

    run_command(["actionlint", str(workflow)], cwd=project)
    run_command(["zizmor", "--no-progress", str(workflow)], cwd=project)
