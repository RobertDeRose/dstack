"""Focused contract tests for GitHub Pages enablement."""

from __future__ import annotations

import json
import stat
import sys
import tomllib
from pathlib import Path

import pytest
from copier import run_copy

from tests.support import run_command


DATA = {
    "project_name": "Enablement Example",
    "project_slug": "enablement-example",
    "project_purpose": "Enable documentation deployment.",
    "project_users": "Repository administrators.",
    "project_scope": "GitHub Pages administration.",
    "project_boundaries": "Application deployment remains separate.",
    "project_kind": "documentation",
    "language_profiles": ["other"],
    "repository_default_branch": "main",
    "include_readme": True,
}
UNIVERSAL_TOOLS = {
    "hk",
    "cocogitto",
    "harper-cli",
    "npm:@contextlint/cli",
    "node",
    "mdbook",
    "uv",
    "rumdl",
    "typos",
    "npm:markdown-table-formatter",
}
TASKS = {"check", "fix", "docs:check", "docs:build", "docs:deployment:enable", "docs:serve"}
FAKE_GH = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
scenario = os.environ["GH_SCENARIO"]
state_path = Path(os.environ["GH_STATE"])
state = json.loads(state_path.read_text()) if state_path.exists() else {
    "created": scenario == "update",
    "gets": 0,
}
with Path(os.environ["GH_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\n")

def finish(code=0, stdout="", stderr=""):
    state_path.write_text(json.dumps(state))
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    raise SystemExit(code)

if args[:2] == ["repo", "view"]:
    finish(1, stderr="no repository\n") if scenario == "repo" else finish(stdout="owner/project\n")
if args[0] == "variable":
    finish(1, stderr="variable denied\n") if scenario == "variable" else finish()
if args[0] == "api":
    method = args[args.index("--method") + 1] if "--method" in args else "GET"
    if method == "POST":
        if scenario == "create" or state["created"]:
            finish(1, stderr="create denied (HTTP 403)\n")
        state["created"] = True
        finish()
    if method == "PUT":
        finish(1, stderr="update denied\n") if scenario == "update" else finish()
    state["gets"] += 1
    if scenario == "query" and state["gets"] == 1:
        finish(1, stderr="query unavailable (HTTP 500)\n")
    if not state["created"]:
        finish(1, stderr="gh: Not Found (HTTP 404)\n")
    finish(1, stderr="url unavailable\n") if scenario == "final" and state["gets"] > 1 else finish(
        stdout="https://owner.github.io/project/\n"
    )
finish(2, stderr="unexpected arguments\n")
"""


def enablement_task(repository_root: Path) -> str:
    mise = tomllib.loads((repository_root / "mise.toml").read_text(encoding="utf-8"))
    return mise["tasks"]["docs:deployment:enable"]["run"]


def fake_environment(tmp_path: Path, scenario: str) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "gh"
    executable.write_text(FAKE_GH.replace("#!/usr/bin/env python3", f"#!{sys.executable}"), encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "gh.log"
    return (
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "GH_SCENARIO": scenario,
            "GH_STATE": str(tmp_path / "state.json"),
            "GH_LOG": str(log),
        },
        log,
    )


def logged_commands(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    ("scenario", "message", "methods", "variable_attempted"),
    [
        ("repo", "no repository", [], False),
        ("query", "query unavailable", [], False),
        ("create", "create denied", ["POST"], False),
        ("update", "update denied", ["PUT"], False),
        ("variable", "variable denied", ["POST"], True),
        ("final", "url unavailable", ["POST"], True),
    ],
)
def test_enablement_stops_on_failed_gh_command(
    repository_root: Path,
    tmp_path: Path,
    scenario: str,
    message: str,
    methods: list[str],
    variable_attempted: bool,
) -> None:
    environment, log = fake_environment(tmp_path, scenario)
    result = run_command(
        ["/bin/bash", "-c", enablement_task(repository_root)],
        cwd=tmp_path,
        env=environment,
        expected=1,
    )

    assert message in result.stderr
    commands = logged_commands(log)
    assert [command[command.index("--method") + 1] for command in commands if "--method" in command] == methods
    assert any(command[:2] == ["variable", "set"] for command in commands) is variable_attempted


def test_enablement_creates_then_updates_pages_with_variable_last(repository_root: Path, tmp_path: Path) -> None:
    environment, log = fake_environment(tmp_path, "success")
    command = ["/bin/bash", "-c", enablement_task(repository_root)]

    first = run_command(command, cwd=tmp_path, env=environment)
    second = run_command(command, cwd=tmp_path, env=environment)

    assert first.stdout == "https://owner.github.io/project/\n"
    assert second.stdout == first.stdout
    mutations = [
        command for command in logged_commands(log) if "--method" in command or command[:2] == ["variable", "set"]
    ]
    assert mutations == [
        ["api", "--method", "POST", "repos/owner/project/pages", "-f", "build_type=workflow"],
        ["variable", "set", "DOCS_DEPLOYMENT_ENABLED", "--body", "true", "--repo", "owner/project"],
        ["api", "--method", "PUT", "repos/owner/project/pages", "-f", "build_type=workflow"],
        ["variable", "set", "DOCS_DEPLOYMENT_ENABLED", "--body", "true", "--repo", "owner/project"],
    ]


@pytest.mark.integration
@pytest.mark.parametrize("entrypoint", ["repository", "bundled"])
def test_generated_enablement_keeps_ten_tools_and_adds_sixth_task(
    tagged_template_source: Path,
    tmp_path: Path,
    entrypoint: str,
) -> None:
    source = tagged_template_source if entrypoint == "repository" else tagged_template_source / "skills/setup-project"
    project = tmp_path / entrypoint
    run_copy(str(source), project, data=DATA, defaults=True, quiet=True, unsafe=False)

    mise = tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))
    assert set(mise["tools"]) == UNIVERSAL_TOOLS
    assert set(mise["tasks"]) == TASKS
    task = mise["tasks"]["docs:deployment:enable"]["run"]
    assert "repository=$(gh repo view" in task
    assert "gh variable set DOCS_DEPLOYMENT_ENABLED" in task
    assert not (project / "scripts/enable-docs-deployment.py").exists()
    assert "GitHub Pages deployment" in (project / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    assert "## Recovery" in (project / "docs/src/operations/github-pages.md").read_text(encoding="utf-8")
