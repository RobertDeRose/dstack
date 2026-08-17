from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = PACKAGE_ROOT / "skills/dstack-beads-core/scripts/setup.py"
DSTACKCTL = PACKAGE_ROOT / "skills/dstack-beads-core/scripts/dstackctl.py"
FAKE_BD = PACKAGE_ROOT / "tests/fake_bd.py"


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("schema_version") == 1 and "data" in payload:
        return payload["data"]
    return payload


@pytest.fixture
def target_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=dev"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    (repo / "README.md").write_text("# target\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "bd"
    wrapper.write_text(f'#!/bin/sh\nexec python3 -S "{FAKE_BD}" "$@"\n')
    wrapper.chmod(0o755)

    state = tmp_path / "beads-state.json"
    state.write_text(json.dumps({"next_id": 1, "issues": {}, "comments": {}, "relations": []}))
    monkeypatch.setenv("DSTACK_FAKE_BD_STATE", str(state))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return repo


def run_command(
    command: Iterable[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed ({' '.join(command)}):\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return completed


def run_json(command: Iterable[str], *, cwd: Path, check: bool = True) -> Any:
    completed = run_command(command, cwd=cwd, check=check)
    if completed.returncode != 0:
        return completed
    return unwrap(json.loads(completed.stdout))


def ctl(repo: Path, *args: str, check: bool = True) -> Any:
    return run_json(
        ["python3", "-S", str(DSTACKCTL), "--root", str(repo), *args],
        cwd=repo,
        check=check,
    )


@pytest.fixture
def installed_repo(target_repo: Path) -> Path:
    run_json(
        [
            "python3",
            "-S",
            str(SETUP_SCRIPT),
            "install",
            "--root",
            str(target_repo),
            "--init",
        ],
        cwd=target_repo,
    )
    return target_repo
