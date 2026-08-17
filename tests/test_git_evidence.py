from __future__ import annotations

import json
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills" / "dstack-beads-core" / "scripts" / "git_evidence.py"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return proc.stdout.strip()


def run_evidence(repo: Path, *args: str) -> tuple[int, dict[str, object]]:
    proc = subprocess.run(
        ["python3", str(SCRIPT), "--root", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    stream = proc.stdout if proc.stdout.strip() else proc.stderr
    return proc.returncode, json.loads(stream)


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    return repo


def test_evidence_survives_commit_rewrite(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    design = repo / "design.md"
    design.write_text("accepted\n")
    git(repo, "add", "design.md")
    git(repo, "commit", "-m", "docs: accept design", "-m", "Beads: bead-123")
    original = git(repo, "rev-parse", "HEAD")

    code, payload = run_evidence(repo, "--bead", "bead-123", "--path", "design.md")
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["commit"] == original

    git(repo, "commit", "--amend", "-m", "docs: accept design cleanly", "-m", "Beads: bead-123")
    rewritten = git(repo, "rev-parse", "HEAD")
    assert rewritten != original

    code, payload = run_evidence(repo, "--bead", "bead-123", "--path", "design.md")
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["commit"] == rewritten


def test_evidence_detects_design_drift(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    design = repo / "design.md"
    design.write_text("accepted\n")
    git(repo, "add", "design.md")
    git(repo, "commit", "-m", "docs: accept design", "-m", "Beads: bead-123")

    design.write_text("changed later\n")
    git(repo, "add", "design.md")
    git(repo, "commit", "-m", "docs: drift design")

    code, payload = run_evidence(repo, "--bead", "bead-123", "--path", "design.md")
    assert code == 3
    assert payload["status"] == "drifted"
    assert payload["path_unchanged_since_evidence"] is False


def test_missing_evidence_is_explicit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "docs: initial")

    code, payload = run_evidence(repo, "--bead", "missing")
    assert code == 2
    assert payload["status"] == "missing"
