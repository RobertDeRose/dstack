from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BD_AVAILABLE = shutil.which("bd") is not None
requires_bd = pytest.mark.skipif(not BD_AVAILABLE, reason="real Beads binary is not available on PATH")


def run_command(
    command: list[str],
    *,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    effective_env = dict(os.environ)
    effective_env["PYTHONPATH"] = str(ROOT)
    effective_env["BD_JSON_ENVELOPE"] = "1"
    if env:
        effective_env.update(env)
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        timeout=180,
        env=effective_env,
    )
    if check and result.returncode:
        raise AssertionError(f"command failed ({' '.join(command)}):\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("schema_version") == 1 and "data" in payload:
        return payload["data"]
    return payload


def run_json(cwd: Path, *args: str) -> Any:
    result = run_command(["bd", *args, "--json"], cwd=cwd)
    return unwrap(json.loads(result.stdout))


def run_dstack(cwd: Path, *args: str, check: bool = True) -> Any:
    result = run_command([sys.executable, "-m", "dstack", *args, "--root", str(cwd)], cwd=cwd, check=check)
    if not check and result.returncode:
        return result
    return json.loads(result.stdout)


def run_dstack_root(cwd: Path, *args: str, check: bool = True) -> Any:
    result = run_command([sys.executable, "-m", "dstack", *args], cwd=cwd, check=check)
    if not check and result.returncode:
        return result
    return json.loads(result.stdout)


def _make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    hk = bin_dir / "hk"
    hk.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hk.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    repo = tmp_path / "project"
    repo.mkdir()
    run_command(["git", "init", "--initial-branch", "main", "-q"], cwd=repo)
    run_command(["git", "config", "user.name", "Acceptance Test"], cwd=repo)
    run_command(["git", "config", "user.email", "acceptance@example.com"], cwd=repo)
    (repo / "README.md").write_text("acceptance\n", encoding="utf-8")
    run_command(["git", "add", "README.md"], cwd=repo)
    run_command(["git", "commit", "-qm", "initial"], cwd=repo)
    return repo


@pytest.fixture
def uninitialized_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _make_repo(tmp_path, monkeypatch)


@pytest.fixture
def real_repo(uninitialized_repo: Path) -> Path:
    run_command(["bd", "init", "--quiet", "--non-interactive", "--skip-agents"], cwd=uninitialized_repo)
    return uninitialized_repo


def pour_feature(repo: Path, *, slug: str = "native-workflow") -> tuple[str, dict[str, dict[str, Any]]]:
    run_dstack(repo, "install", "formula")
    run_command(["git", "add", ".beads"], cwd=repo)
    if run_command(["git", "diff", "--cached", "--quiet"], cwd=repo, check=False).returncode:
        run_command(["git", "commit", "-qm", "chore: initialize Beads workflow"], cwd=repo)

    payload = run_json(
        repo,
        "mol",
        "pour",
        "dstack-feature",
        "--var",
        "title=Feature: Native workflow",
        "--var",
        "desc=Use Beads as the workflow authority",
        "--var",
        "feature_title=Native workflow",
        "--var",
        f"feature_slug={slug}",
        "--var",
        "base_branch=main",
    )
    root = str(payload["new_epic_id"])
    run_json(
        repo,
        "update",
        root,
        "--add-label",
        "workflow:feature",
        "--add-label",
        f"feature:{slug}",
        "--set-metadata",
        "dstack.base_branch=main",
    )
    children = run_json(repo, "list", "--parent", root, "--all", "--include-gates", "--limit", "0")
    labels = {
        "plan": "dstack:step:plan",
        "review": "dstack:step:review",
        "approval": "dstack:step:approval",
        "implementation": "dstack:step:implementation",
        "audit": "dstack:step:audit",
    }
    steps = {
        name: next(issue for issue in children if label in issue.get("labels", [])) for name, label in labels.items()
    }
    return root, steps
