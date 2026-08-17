from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import DSTACKCTL, SETUP_SCRIPT


def real_bd() -> str | None:
    explicit = os.environ.get("DSTACK_REAL_BD")
    if explicit:
        return explicit
    candidate = shutil.which("bd")
    if candidate and "pytest" not in candidate:
        return candidate
    return None


def unwrap(payload):
    if isinstance(payload, dict) and payload.get("schema_version") == 1:
        return payload.get("data")
    return payload


def run_json(command: list[str], *, cwd: Path):
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "BD_JSON_ENVELOPE": "1"},
    )
    return unwrap(json.loads(result.stdout))


@pytest.mark.skipif(real_bd() is None, reason="real Beads binary is unavailable")
def test_real_beads_feature_gate_claim_fan_in_and_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the supported real Beads boundary in JSON-envelope mode."""

    bd = real_bd()
    assert bd
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bd").symlink_to(bd)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("BD_JSON_ENVELOPE", "1")

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
    )
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            "python3",
            "-S",
            str(SETUP_SCRIPT),
            "install",
            "--root",
            str(repo),
            "--init",
        ],
        cwd=repo,
        check=True,
        env={**os.environ, "BD_JSON_ENVELOPE": "1"},
    )

    inventory = run_json(
        [
            "bd",
            "list",
            "--all",
            "--include-templates",
            "--include-gates",
            "--limit",
            "0",
            "--json",
        ],
        cwd=repo,
    )
    assert inventory == []

    created = run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "initialize",
            "Real Boundary",
            "--base-branch",
            "main",
        ],
        cwd=repo,
    )
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("# Real boundary\n")
    subprocess.run(["git", "add", str(design.relative_to(worktree))], cwd=worktree, check=True)
    run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(worktree),
            "git",
            "commit",
            "--bead",
            created["steps"]["specification"]["id"],
            "--subject",
            "docs: define real boundary",
        ],
        cwd=worktree,
    )
    run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "claim-spec",
            root_id,
        ],
        cwd=repo,
    )
    approved = run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "approve-spec",
            root_id,
        ],
        cwd=repo,
    )
    assert approved["steps"]["approval"]["status"] == "closed"
    assert approved["human_gate"]["status"] == "closed"

    task = run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "add-task",
            root_id,
            "--title",
            "Implement real boundary",
            "--acceptance",
            "done",
        ],
        cwd=repo,
    )["task"]
    claimed = run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "claim-next",
            root_id,
        ],
        cwd=repo,
    )
    assert claimed["task"]["id"] == task["id"]

    (worktree / "real.txt").write_text("done\n")
    subprocess.run(["git", "add", "real.txt"], cwd=worktree, check=True)
    run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(worktree),
            "git",
            "commit",
            "--bead",
            task["id"],
            "--subject",
            "feat: implement real boundary",
        ],
        cwd=worktree,
    )
    run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "finish-task",
            root_id,
            "--task",
            task["id"],
        ],
        cwd=repo,
    )
    run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "finish-workstream",
            root_id,
        ],
        cwd=repo,
    )
    run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "claim-closeout",
            root_id,
        ],
        cwd=repo,
    )
    closed = run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "feature",
            "finish-closeout",
            root_id,
        ],
        cwd=repo,
    )
    assert closed["steps"]["closeout"]["status"] == "closed"

    delivered = run_json(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(repo),
            "delivery",
            "merge",
            root_id,
        ],
        cwd=repo,
    )
    assert delivered["status"] == "ok"
    root = run_json(["bd", "show", root_id, "--json"], cwd=repo)
    if isinstance(root, list):
        root = root[0]
    assert root["status"] == "closed"
