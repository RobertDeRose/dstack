from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from conftest import DSTACKCTL, ctl, run_command, run_json


def initialize(repo: Path, title: str = "Leader Election Weighting"):
    return ctl(repo, "feature", "initialize", title, "--base-branch", "dev")


def test_initialize_resolves_by_title_slug_and_id_and_is_idempotent(installed_repo: Path) -> None:
    created = initialize(installed_repo)
    root_id = created["root"]["id"]
    assert created["created"] is True
    assert ctl(installed_repo, "feature", "resolve", root_id)["root"]["id"] == root_id
    assert ctl(installed_repo, "feature", "resolve", "leader-election-weighting")["root"]["id"] == root_id
    assert ctl(installed_repo, "feature", "resolve", "Leader Election Weighting")["root"]["id"] == root_id
    reused = initialize(installed_repo)
    assert reused["created"] is False
    assert reused["root"]["id"] == root_id


def test_human_gate_resolution_does_not_require_gate_list_parent(
    installed_repo: Path,
) -> None:
    created = initialize(installed_repo)
    gates = run_json(
        ["bd", "gate", "list", "--all", "--limit", "0", "--json"],
        cwd=installed_repo,
    )
    assert len(gates) == 1
    assert "parent" not in gates[0]

    inspected = ctl(installed_repo, "feature", "inspect", created["root"]["id"])
    assert inspected["human_gate"]["id"] == created["human_gate"]["id"]


def test_spec_approval_uses_design_digest_without_requiring_a_commit(installed_repo: Path) -> None:
    created = initialize(installed_repo)
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("# Design\n\nAccepted architecture.\n")
    ctl(installed_repo, "feature", "claim-spec", created["root"]["id"])
    approved = ctl(installed_repo, "feature", "approve-spec", created["root"]["id"])
    expected = hashlib.sha256(design.read_bytes()).hexdigest()
    assert approved["approved_design_sha256"] == expected
    assert approved["design_approved"] is True
    assert approved["steps"]["specification"]["status"] == "closed"
    assert approved["steps"]["approval"]["status"] == "closed"
    assert approved["human_gate"]["status"] == "closed"
    assert subprocess.check_output(["git", "rev-list", "--count", "dev..HEAD"], cwd=worktree, text=True).strip() == "0"


def test_design_drift_blocks_implementation_until_reapproved(installed_repo: Path) -> None:
    created = initialize(installed_repo)
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("v1\n")
    ctl(installed_repo, "feature", "claim-spec", created["root"]["id"])
    ctl(installed_repo, "feature", "approve-spec", created["root"]["id"])
    task = ctl(
        installed_repo,
        "feature",
        "add-task",
        created["root"]["id"],
        "--title",
        "Implement outcome",
        "--acceptance",
        "Works",
    )["task"]
    design.write_text("v2\n")
    failed = run_command(
        ["python3", "-S", str(DSTACKCTL), "--root", str(installed_repo), "feature", "claim-next", created["root"]["id"]],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "differs from the approved specification" in failed.stderr
    design.write_text("v1\n")
    claimed = ctl(installed_repo, "feature", "claim-next", created["root"]["id"])
    assert claimed["task"]["id"] == task["id"]


def test_task_commit_footer_closeout_and_rewrite_safe_audit(installed_repo: Path) -> None:
    created = initialize(installed_repo)
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("approved\n")
    ctl(installed_repo, "feature", "claim-spec", root_id)
    ctl(installed_repo, "feature", "approve-spec", root_id)
    task = ctl(installed_repo, "feature", "add-task", root_id, "--title", "Implement", "--acceptance", "done")["task"]
    ctl(installed_repo, "feature", "claim-next", root_id)
    (worktree / "feature.txt").write_text("done\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=worktree, check=True)
    ctl(worktree, "git", "commit", "--bead", task["id"], "--subject", "feat: implement outcome")
    first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
    ctl(installed_repo, "feature", "finish-task", root_id, "--task", task["id"])
    audit = ctl(installed_repo, "evidence", "audit-feature", root_id)
    assert audit["status"] == "ok"
    assert audit["mapping"][task["id"]][0]["commit"] == first
    subprocess.run(["git", "commit", "--amend", "-m", f"feat: rewritten\n\nBeads: {task['id']}"], cwd=worktree, check=True, capture_output=True)
    rewritten = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
    assert rewritten != first
    assert ctl(installed_repo, "evidence", "audit-feature", root_id)["status"] == "ok"
    ctl(installed_repo, "feature", "finish-workstream", root_id)
    assert ctl(installed_repo, "feature", "claim-closeout", root_id)["closeout"]["status"] == "in_progress"
    closed = ctl(installed_repo, "feature", "finish-closeout", root_id)
    assert closed["steps"]["closeout"]["status"] == "closed"
    assert closed["root"]["status"] == "open"


def test_starting_a_planned_legacy_epic_pours_current_workflow(installed_repo: Path) -> None:
    from conftest import run_json

    planned = run_json(
        [
            "bd",
            "create",
            "Zenoh DDS Forward Discovery",
            "--type",
            "epic",
            "--labels",
            "workflow:feature",
            "--json",
        ],
        cwd=installed_repo,
    )[0]
    run_json(
        [
            "bd",
            "update",
            planned["id"],
            "--add-label",
            "feature:zenoh-dds-forward-discovery",
            "--set-metadata",
            "migration_classification=planned",
            "--set-metadata",
            "base_branch=dev",
            "--set-metadata",
            "design_path=docs/src/features/zenoh-dds-forward-discovery/design.md",
            "--json",
        ],
        cwd=installed_repo,
    )
    started = ctl(installed_repo, "feature", "initialize", planned["id"], "--base-branch", "dev")
    assert started["created"] is True
    assert started["planned_source"] == planned["id"]
    assert started["slug"] == "zenoh-dds-forward-discovery"
    assert ctl(installed_repo, "feature", "inspect", planned["id"])["root"]["status"] == "closed"


def test_existing_molecule_survives_formula_upgrade_but_new_pour_requires_setup(
    installed_repo: Path,
) -> None:
    created = initialize(installed_repo)
    formula = installed_repo / ".beads/formulas/dstack-feature.formula.toml"
    formula.write_text(formula.read_text() + "\n# newer package not installed\n")

    inspected = ctl(installed_repo, "feature", "inspect", created["root"]["id"])
    assert inspected["root"]["id"] == created["root"]["id"]

    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "feature",
            "initialize",
            "Another Feature",
            "--base-branch",
            "dev",
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "/setup-project --force" in failed.stderr


def test_initialize_rolls_back_pour_and_branch_when_worktree_creation_fails(
    installed_repo: Path,
) -> None:
    blocked_path = installed_repo.parent / f"{installed_repo.name}.feat-rollback-feature"
    blocked_path.mkdir()
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "feature",
            "initialize",
            "Rollback Feature",
            "--base-branch",
            "dev",
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "exists but is not registered" in failed.stderr
    assert subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/feat/rollback-feature"],
        cwd=installed_repo,
    ).returncode != 0
    assert "Rollback Feature" not in subprocess.check_output(
        ["bd", "list", "--all", "--limit", "0"],
        cwd=installed_repo,
        text=True,
    )


def test_explicit_task_cannot_bypass_native_ready_dependencies(installed_repo: Path) -> None:
    created = initialize(installed_repo)
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("approved\n")
    ctl(installed_repo, "feature", "claim-spec", root_id)
    ctl(installed_repo, "feature", "approve-spec", root_id)
    first = ctl(
        installed_repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "First",
        "--acceptance",
        "done",
    )["task"]
    second = ctl(
        installed_repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Second",
        "--acceptance",
        "done",
        "--depends-on",
        first["id"],
    )["task"]
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "feature",
            "claim-next",
            root_id,
            "--task",
            second["id"],
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "not currently ready" in failed.stderr
