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
        candidate = shutil.which(explicit)
        return candidate if candidate and os.access(candidate, os.X_OK) else None
    candidate = shutil.which("bd")
    if candidate and "pytest" not in candidate and os.access(candidate, os.X_OK):
        return candidate
    return None


def require_real_bd() -> str:
    candidate = real_bd()
    if candidate:
        return candidate
    if os.environ.get("DSTACK_REQUIRE_REAL_BD") == "1":
        raise RuntimeError(
            "DSTACK_REQUIRE_REAL_BD=1 but a usable real Beads binary was not found"
        )
    pytest.skip("real Beads binary is unavailable")


def controller_command(repo: Path, *args: str) -> list[str]:
    return ["python3", "-S", str(DSTACKCTL), "--root", str(repo), *args]


def controller_result(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        controller_command(repo, *args),
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "BD_JSON_ENVELOPE": "1"},
    )


def controller(repo: Path, *args: str):
    return run_json(controller_command(repo, *args), cwd=repo)


def prepare_real_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bd = require_real_bd()
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
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initialize dstack"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    repair = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "repair-legacy", "--root", str(repo)],
        cwd=repo,
    )
    assert repair["status"] == "ok"
    return repo


def test_required_real_mode_rejects_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSTACK_REAL_BD", "/definitely/missing/bd")
    monkeypatch.setenv("DSTACK_REQUIRE_REAL_BD", "1")
    with pytest.raises(RuntimeError, match="DSTACK_REQUIRE_REAL_BD"):
        require_real_bd()


def unwrap(payload):
    if isinstance(payload, dict) and payload.get("schema_version") == 1:
        return payload.get("data")
    return payload


def first_item(payload):
    return payload[0] if isinstance(payload, list) else payload


def run_json(command: list[str], *, cwd: Path):
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "BD_JSON_ENVELOPE": "1"},
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({' '.join(command)}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    try:
        return unwrap(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"command returned non-JSON ({' '.join(command)}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        ) from exc


def initialize_real_feature(repo: Path, title: str) -> tuple[dict, Path]:
    created = controller(repo, "feature", "initialize", title, "--base-branch", "main")
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(f"# {title}\n")
    controller(repo, "feature", "claim-spec", created["root"]["id"])
    controller(repo, "feature", "approve-spec", created["root"]["id"])
    return created, worktree


def close_real_feature(repo: Path, root_id: str) -> None:
    controller(repo, "feature", "finish-workstream", root_id)
    controller(repo, "feature", "claim-closeout", root_id)
    controller(repo, "feature", "finish-closeout", root_id)


def test_real_beads_design_drift_ownership_and_no_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = prepare_real_repo(tmp_path, monkeypatch)
    created, worktree = initialize_real_feature(repo, "Real Failure Boundaries")
    root_id = created["root"]["id"]
    design = worktree / created["design_path"]
    task = controller(
        repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "No source change",
        "--acceptance",
        "The native no-change reason is audited.",
    )["task"]

    design.write_text("# changed after approval\n")
    drift = controller_result(repo, "feature", "claim-next", root_id, "--task", task["id"])
    assert drift.returncode != 0
    assert "differs from the approved specification" in drift.stderr
    current = run_json(["bd", "show", task["id"], "--json"], cwd=repo)
    assert current[0]["status"] == "open"

    design.write_text(f"# Real Failure Boundaries\n")
    controller(repo, "feature", "claim-next", root_id, "--task", task["id"])
    controller(
        repo,
        "feature",
        "finish-task",
        root_id,
        "--task",
        task["id"],
        "--no-repository-change",
        "--reason",
        "No source change was required.",
    )

    competing = controller(
        repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Competing owner",
        "--acceptance",
        "Another owner cannot finish this task.",
    )["task"]
    run_json(
        ["bd", "update", competing["id"], "--claim", "--actor", "other-owner", "--json"],
        cwd=repo,
    )
    claim = controller_result(repo, "feature", "claim-next", root_id, "--task", competing["id"])
    assert claim.returncode != 0
    finish = controller_result(
        repo,
        "feature",
        "finish-task",
        root_id,
        "--task",
        competing["id"],
        "--no-repository-change",
        "--reason",
        "Not allowed for another owner.",
    )
    assert finish.returncode != 0

    close_real_feature(repo, root_id)
    audit = controller(repo, "evidence", "audit-feature", root_id)
    assert audit["status"] == "ok"
    assert task["id"] in audit["no_repository_change"]


def test_real_beads_alignment_lifecycle_and_rewrite_safe_footer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = prepare_real_repo(tmp_path, monkeypatch)
    alignment = controller(
        repo,
        "alignment",
        "initialize",
        "--title",
        "Real Alignment",
        "--target-branch",
        "main",
    )
    root_id = alignment["root"]["id"]
    correction = controller(
        repo,
        "alignment",
        "add-correction",
        root_id,
        "--title",
        "Real correction",
        "--acceptance",
        "The correction is delivered through native fan-in.",
    )["correction"]
    controller(repo, "alignment", "finish-plan", root_id)
    controller(repo, "alignment", "approve", root_id)
    assert controller(repo, "alignment", "claim-next", root_id)["correction"]["id"] == correction["id"]
    worktree = Path(alignment["worktree"])
    (worktree / "real-alignment.txt").write_text("fixed\n")
    subprocess.run(["git", "add", "real-alignment.txt"], cwd=worktree, check=True)
    controller(
        worktree,
        "git",
        "commit",
        "--bead",
        correction["id"],
        "--subject",
        "fix: real alignment",
    )
    controller(repo, "alignment", "finish-task", root_id, "--task", correction["id"])
    controller(repo, "alignment", "finish-workstream", root_id)
    controller(repo, "alignment", "claim-landing", root_id)
    landed = controller(repo, "alignment", "finish-landing", root_id)
    assert landed["steps"]["landing"]["status"] == "closed"

    created, worktree = initialize_real_feature(repo, "Real Rewrite Boundary")
    feature_root = created["root"]["id"]
    task = controller(
        repo,
        "feature",
        "add-task",
        feature_root,
        "--title",
        "Rewrite footer",
        "--acceptance",
        "A rewritten footer remains reachable evidence.",
    )["task"]
    controller(repo, "feature", "claim-next", feature_root)
    (worktree / "rewritten.txt").write_text("rewritten\n")
    subprocess.run(["git", "add", "rewritten.txt"], cwd=worktree, check=True)
    controller(
        worktree,
        "git",
        "commit",
        "--bead",
        task["id"],
        "--subject",
        "feat: original footer",
    )
    subprocess.run(
        ["git", "commit", "--amend", "-m", f"feat: rewritten footer\n\nBeads: {task['id']}"],
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    controller(repo, "feature", "finish-task", feature_root, "--task", task["id"])
    close_real_feature(repo, feature_root)
    audit = controller(repo, "evidence", "audit-feature", feature_root)
    assert audit["status"] == "ok"
    assert audit["mapping"][task["id"]][0]["subject"] == "feat: rewritten footer"


def add_real_remote(repo: Path) -> Path:
    bare = repo.parent / "origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo, check=True, capture_output=True)
    return bare


def advance_remote_main(repo: Path, bare: Path, name: str) -> None:
    clone = repo.parent / name
    subprocess.run(["git", "clone", str(bare), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Remote"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.email", "remote@example.com"], cwd=clone, check=True)
    (clone / "remote.txt").write_text("remote advance\n")
    subprocess.run(["git", "add", "remote.txt"], cwd=clone, check=True)
    subprocess.run(["git", "commit", "-m", "remote: advance target"], cwd=clone, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=clone, check=True, capture_output=True)


def complete_real_feature(repo: Path, title: str) -> tuple[dict, Path, dict]:
    created, worktree = initialize_real_feature(repo, title)
    root_id = created["root"]["id"]
    task = controller(
        repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Deliver real feature",
        "--acceptance",
        "The candidate has reachable real-Beads evidence.",
    )["task"]
    controller(repo, "feature", "claim-next", root_id)
    (worktree / "real-delivery.txt").write_text("delivered\n")
    subprocess.run(["git", "add", "real-delivery.txt"], cwd=worktree, check=True)
    controller(
        worktree,
        "git",
        "commit",
        "--bead",
        task["id"],
        "--subject",
        "feat: real delivery",
    )
    controller(repo, "feature", "finish-task", root_id, "--task", task["id"])
    close_real_feature(repo, root_id)
    return created, worktree, task


def test_real_beads_stale_target_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = prepare_real_repo(tmp_path, monkeypatch)
    bare = add_real_remote(repo)
    created, _, _ = complete_real_feature(repo, "Real Stale Target")
    advance_remote_main(repo, bare, "remote-stale")
    failed = controller_result(repo, "delivery", "pr-preflight", created["root"]["id"])
    assert failed.returncode != 0
    assert "target" in failed.stderr.casefold()


def test_real_beads_pr_gate_finalization_preserves_local_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = prepare_real_repo(tmp_path, monkeypatch)
    bare = add_real_remote(repo)
    created, worktree, _ = complete_real_feature(repo, "Real PR Gate")
    branch = created["branch"]
    subprocess.run(["git", "push", "origin", branch], cwd=worktree, check=True, capture_output=True)
    controller(repo, "delivery", "pr-preflight", created["root"]["id"])
    registered = controller(
        repo,
        "delivery",
        "register-pr",
        created["root"]["id"],
        "--pr-number",
        "42",
    )
    gate = registered["gate"]
    waiting = controller_result(repo, "delivery", "finalize-pr", created["root"]["id"])
    assert waiting.returncode == 2
    assert "waiting" in waiting.stdout
    subprocess.run(
        ["bd", "gate", "resolve", gate["id"], "--reason", "Merged in isolated remote"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={**os.environ, "BD_JSON_ENVELOPE": "1"},
    )
    subprocess.run(["git", "push", "origin", f"{branch}:main"], cwd=repo, check=True, capture_output=True)
    before = subprocess.check_output(["git", "rev-parse", "main"], cwd=repo, text=True).strip()
    finalized = controller(repo, "delivery", "finalize-pr", created["root"]["id"])
    after = subprocess.check_output(["git", "rev-parse", "main"], cwd=repo, text=True).strip()
    assert finalized["status"] == "ok"
    assert before == after
    assert finalized["root"]["status"] == "closed"


def test_real_beads_legacy_adoption_uses_native_supersedes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = prepare_real_repo(tmp_path, monkeypatch)
    legacy = first_item(run_json(
        ["bd", "create", "Legacy Real Feature", "--type", "epic", "--labels", "workflow:feature", "--json"],
        cwd=repo,
    ))
    run_json(
        [
            "bd",
            "update",
            legacy["id"],
            "--add-label",
            "feature:legacy-real",
            "--set-metadata",
            "dstack.base_branch=main",
            "--set-metadata",
            "dstack.design_path=docs/src/features/legacy-real/design.md",
            "--json",
        ],
        cwd=repo,
    )
    implementation = first_item(run_json(
        ["bd", "create", "Implement: Legacy Real Feature", "--type", "task", "--parent", legacy["id"], "--json"],
        cwd=repo,
    ))
    real = first_item(run_json(
        [
            "bd",
            "create",
            "legacy real outcome",
            "--type",
            "task",
            "--parent",
            implementation["id"],
            "--labels",
            "phase:implementation",
            "--acceptance",
            "works",
            "--json",
        ],
        cwd=repo,
    ))
    review = first_item(run_json(
        ["bd", "create", "Review Legacy Real", "--type", "task", "--parent", legacy["id"], "--labels", "review:architecture", "--json"],
        cwd=repo,
    ))
    closeout = first_item(run_json(
        ["bd", "create", "Validate: Legacy Real", "--type", "task", "--parent", legacy["id"], "--json"],
        cwd=repo,
    ))
    adopted = controller(
        repo,
        "adopt",
        "apply",
        legacy["id"],
        "--remaining",
        real["id"],
        "--spec-ceremony",
        review["id"],
        "--implementation-coordinator",
        implementation["id"],
        "--closeout-ceremony",
        closeout["id"],
    )
    assert adopted["root"]["status"] == "open"
    assert len(adopted["work_items"]) == 1
    old = first_item(run_json(["bd", "show", legacy["id"], "--json"], cwd=repo))
    assert old["status"] == "closed"


def test_real_beads_feature_gate_claim_fan_in_and_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the supported real Beads boundary in JSON-envelope mode."""

    bd = require_real_bd()
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
    assert subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".beads/interactions.jsonl"],
        cwd=repo,
        check=False,
        capture_output=True,
    ).returncode != 0
    assert "interactions.jsonl" in (repo / ".beads/.gitignore").read_text()

    # Repository setup is a separate Git boundary. Feature delivery begins only
    # after the Beads/dStack configuration baseline is committed.
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initialize dstack"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

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
