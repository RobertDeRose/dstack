from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "skills/dstack-beads-core/scripts/setup.py"
CTL = ROOT / "skills/dstack-beads-core/scripts/dstackctl.py"


def pytest_sessionstart(session: pytest.Session) -> None:
    if shutil.which("bd") is None:
        pytest.exit("real Beads is required: install bd on PATH", returncode=1)


def run_command(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, check=False, text=True, capture_output=True)
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
    result = run_command(["python3", "-S", str(CTL), "--root", str(cwd), *args], cwd=cwd, check=check)
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
    return repo


@pytest.fixture
def beads_repo(real_repo: Path) -> Path:
    run_command(
        ["bd", "init", "--quiet", "--skip-agents", "--skip-hooks", "--non-interactive"],
        cwd=real_repo,
    )
    formula_dir = real_repo / ".beads/formulas"
    formula_dir.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "formulas").glob("*.formula.toml"):
        shutil.copyfile(source, formula_dir / source.name)
    return real_repo


@pytest.fixture
def acceptance_repo(real_repo: Path) -> Path:
    run_command(
        ["python3", "-S", str(SETUP), "install", "--root", str(real_repo), "--init"],
        cwd=real_repo,
    )
    run_command(["git", "add", "-A"], cwd=real_repo)
    run_command(["git", "commit", "-qm", "chore: initialize dstack"], cwd=real_repo)
    return real_repo
