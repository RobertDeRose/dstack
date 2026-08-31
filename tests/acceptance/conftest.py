from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSTACK = "dstack"


def pytest_sessionstart(session: pytest.Session) -> None:
    if shutil.which("bd") is None:
        pytest.exit("real Beads is required: install bd on PATH", returncode=1)


def run_command(
    command: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    effective_timeout = timeout or float(os.environ.get("DSTACK_ACCEPTANCE_COMMAND_TIMEOUT", "120"))
    if not math.isfinite(effective_timeout) or effective_timeout <= 0:
        raise ValueError("acceptance command timeout must be positive and finite")
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr or ""
        raise AssertionError(
            f"command timed out after {effective_timeout:g}s ({' '.join(command)}) in {cwd}:\n"
            f"stdout={stdout}\nstderr={stderr}"
        ) from exc
    if check and result.returncode:
        raise AssertionError(f"command failed ({' '.join(command)}):\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and value.get("schema_version") == 1:
        return value.get("data")
    return value


def run_json(cwd: Path, *args: str) -> Any:
    result = run_command(["bd", *args, "--json"], cwd=cwd)
    try:
        return unwrap(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"bd returned non-JSON for {' '.join(args)}: {result.stdout}") from exc


def run_ctl(cwd: Path, *args: str, check: bool = True) -> Any:
    result = run_command([DSTACK, "ctl", "--root", str(cwd), *args], cwd=cwd, check=check)
    if not result.returncode:
        try:
            return unwrap(json.loads(result.stdout))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"controller returned non-JSON: {result.stdout}") from exc
    return result


@pytest.fixture
def real_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BD_JSON_ENVELOPE", "1")
    repo = tmp_path / "repo"
    repo.mkdir()
    run_command(["git", "init", "--initial-branch=main", "-q"], cwd=repo)
    run_command(["git", "config", "user.name", "Acceptance Test"], cwd=repo)
    run_command(["git", "config", "user.email", "acceptance@example.com"], cwd=repo)
    (repo / "README.md").write_text("acceptance\n")
    run_command(["git", "add", "README.md"], cwd=repo)
    run_command(["git", "commit", "-qm", "initial"], cwd=repo)
    from dstack.docs import create_foundation

    create_foundation(repo)
    run_command(["git", "add", "docs"], cwd=repo)
    run_command(["git", "commit", "-qm", "docs: add acceptance foundation"], cwd=repo)
    return repo


@pytest.fixture
def beads_repo(real_repo: Path) -> Path:
    run_command(
        ["bd", "init", "--quiet", "--stealth", "--skip-agents", "--skip-hooks", "--non-interactive"],
        cwd=real_repo,
    )
    formula_dir = real_repo / ".beads/formulas"
    formula_dir.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "dstack/assets/formulas").glob("*.formula.toml"):
        shutil.copyfile(source, formula_dir / source.name)
    return real_repo


@pytest.fixture
def acceptance_repo(real_repo: Path) -> Path:
    result = run_command([str(DSTACK), "ctl", "infra", "check"], cwd=real_repo)
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert Path(payload["root"]) == real_repo.resolve()
    assert payload["formula_versions"]["dstack-feature"] == 9
    assert payload["formula_versions"]["dstack-project-alignment"] == 8
    # Automatic infrastructure must not create a repository setup boundary.
    assert run_command(["git", "status", "--porcelain=v1"], cwd=real_repo).stdout == ""
    return real_repo
