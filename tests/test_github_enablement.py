"""Focused contract tests for GitHub Pages enablement."""

from __future__ import annotations

import json
import os
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
state = json.loads(state_path.read_text()) if state_path.exists() else {"gets": 0, "created": False}
with Path(os.environ["GH_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\n")

def finish(code=0, stdout="", stderr=""):
    state_path.write_text(json.dumps(state))
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    raise SystemExit(code)

if args[:2] == ["auth", "status"]:
    finish(1, stderr="not authenticated\n") if scenario == "auth" else finish()
if args[:2] == ["repo", "view"]:
    finish(1, stderr="no repository\n") if scenario == "repo" else finish(stdout="owner/project\n")
if args[0] == "variable":
    finish(1, stderr="variable denied\n") if scenario == "variable" else finish()
if args[0] == "api":
    method = args[args.index("--method") + 1] if "--method" in args else "GET"
    if method == "POST":
        if scenario == "create-fail":
            finish(1, stderr="create denied\n")
        state["created"] = True
        finish(stdout='{"html_url":"https://owner.github.io/project/"}\n')
    if method == "PUT":
        finish(1, stderr="update denied\n") if scenario == "update" else finish()
    state["gets"] += 1
    if scenario == "get" and state["gets"] == 1:
        finish(1, stderr="expected HTTP 404 but returned (HTTP 500)\n")
    if scenario in {"create", "create-fail"} and not state["created"]:
        finish(1, stderr="gh: Not Found (HTTP 404)\n")
    if scenario == "final" and state["gets"] > 1:
        finish(1, stderr="url unavailable\n")
    finish(stdout="https://owner.github.io/project/\n")
finish(2, stderr="unexpected arguments\n")
"""


def helper(repository_root: Path) -> Path:
    return repository_root / "skills/setup-project/template/scripts/enable-docs-deployment.py"


def fake_environment(tmp_path: Path, scenario: str) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "gh"
    executable.write_text(FAKE_GH, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "gh.log"
    return (
        os.environ
        | {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GH_SCENARIO": scenario,
            "GH_STATE": str(tmp_path / "state.json"),
            "GH_LOG": str(log),
        },
        log,
    )


def logged_commands(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    ("scenario", "message", "variable_attempted"),
    [
        ("auth", "authentication check failed", False),
        ("repo", "repository resolution failed", False),
        ("get", "Pages query failed", False),
        ("create-fail", "Pages creation failed", False),
        ("update", "Pages update failed", False),
        ("variable", "deployment variable update failed", True),
        ("final", "Pages URL query failed", True),
    ],
)
def test_enablement_reports_failures_without_false_success(
    repository_root: Path,
    tmp_path: Path,
    scenario: str,
    message: str,
    variable_attempted: bool,
) -> None:
    environment, log = fake_environment(tmp_path, scenario)
    result = run_command([sys.executable, str(helper(repository_root))], cwd=tmp_path, env=environment, expected=1)

    assert message in result.stderr
    assert "Manual recovery:" in result.stderr
    assert "gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow" in result.stderr
    assert "gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO" in result.stderr
    assert "deployment enabled:" not in result.stdout
    commands = logged_commands(log)
    assert any(command[:2] == ["variable", "set"] for command in commands) is variable_attempted


def test_enablement_requires_external_gh(repository_root: Path, tmp_path: Path) -> None:
    result = run_command(
        [sys.executable, str(helper(repository_root))],
        cwd=tmp_path,
        env=os.environ | {"PATH": str(tmp_path)},
        expected=1,
    )

    assert "GitHub CLI (gh) is not installed" in result.stderr
    assert "Install GitHub CLI: https://cli.github.com/" in result.stderr
    assert "Manual recovery:" in result.stderr
    assert "gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow" in result.stderr
    assert "gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO" in result.stderr
    assert "deployment enabled:" not in result.stdout


def test_enablement_creates_then_updates_pages_with_variable_last(repository_root: Path, tmp_path: Path) -> None:
    environment, log = fake_environment(tmp_path, "create")

    first = run_command([sys.executable, str(helper(repository_root))], cwd=tmp_path, env=environment)
    second = run_command([sys.executable, str(helper(repository_root))], cwd=tmp_path, env=environment)

    assert first.stdout == "GitHub Pages deployment enabled: https://owner.github.io/project/\n"
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
    assert mise["tasks"]["docs:deployment:enable"]["run"] == "python3 scripts/enable-docs-deployment.py"
    assert (project / "scripts/enable-docs-deployment.py").stat().st_mode & stat.S_IXUSR
    assert "GitHub Pages deployment" in (project / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    assert "## Recovery" in (project / "docs/src/operations/github-pages.md").read_text(encoding="utf-8")
