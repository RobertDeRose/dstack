from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = PACKAGE_ROOT / "skills" / "dstack-beads-core" / "scripts" / "setup.py"
FAKE_BD = PACKAGE_ROOT / "tests" / "fake_bd.py"


@pytest.fixture
def target_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=dev"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    (repo / "README.md").write_text("# target\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "bd"
    wrapper.write_text(f"#!/bin/sh\nexec python3 -S {FAKE_BD!s} \"$@\"\n")
    wrapper.chmod(0o755)

    state = tmp_path / "beads-state.json"
    state.write_text(json.dumps({"next_id": 1, "issues": {}, "protos": {}, "relations": [], "comments": {}}))
    monkeypatch.setenv("DSTACK_FAKE_BD_STATE", str(state))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return repo


def run_json(command: Iterable[str], *, cwd: Path, check: bool = True) -> Any:
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
            f"command failed ({' '.join(command)}):\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    if completed.returncode != 0:
        return completed
    return json.loads(completed.stdout)


@pytest.fixture
def installed_repo(target_repo: Path) -> Path:
    run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"],
        cwd=target_repo,
    )
    return target_repo
