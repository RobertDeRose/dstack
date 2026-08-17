from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import ctl, run_json


def test_alignment_three_tiers_use_native_tasks_and_current_evidence(installed_repo: Path) -> None:
    audit = ctl(
        installed_repo,
        "alignment",
        "initialize",
        "--title",
        "Repository Alignment",
        "--target-branch",
        "dev",
    )
    root_id = audit["root"]["id"]
    correction = ctl(
        installed_repo,
        "alignment",
        "add-correction",
        root_id,
        "--title",
        "Correct behavior",
        "--acceptance",
        "validated",
    )["correction"]
    ctl(installed_repo, "alignment", "finish-plan", root_id)
    ctl(installed_repo, "alignment", "approve", root_id)
    assert ctl(installed_repo, "alignment", "claim-next", root_id)["correction"]["id"] == correction["id"]
    worktree = Path(audit["worktree"])
    (worktree / "alignment.txt").write_text("fixed\n")
    subprocess.run(["git", "add", "alignment.txt"], cwd=worktree, check=True)
    ctl(worktree, "git", "commit", "--bead", correction["id"], "--subject", "fix: align repository")
    ctl(installed_repo, "alignment", "finish-task", root_id, "--task", correction["id"])
    ctl(installed_repo, "alignment", "finish-workstream", root_id)
    ctl(installed_repo, "alignment", "claim-landing", root_id)
    landed = ctl(installed_repo, "alignment", "finish-landing", root_id)
    assert landed["steps"]["landing"]["status"] == "closed"
    assert "baseline_commit" not in landed["root"].get("metadata", {})


def create_legacy(repo: Path):
    root = run_json(
        ["bd", "create", "Legacy Feature", "--type", "epic", "--labels", "workflow:feature", "--json"],
        cwd=repo,
    )[0]
    run_json(
        ["bd", "update", root["id"], "--add-label", "feature:legacy-feature", "--set-metadata", "base_branch=dev", "--set-metadata", "design_path=docs/src/features/legacy-feature/design.md", "--json"],
        cwd=repo,
    )
    implementation = run_json(
        ["bd", "create", "Implement: Legacy Feature", "--type", "task", "--parent", root["id"], "--json"],
        cwd=repo,
    )[0]
    real = run_json(
        ["bd", "create", "legacy T001 — real outcome", "--type", "task", "--parent", implementation["id"], "--labels", "phase:implementation", "--acceptance", "works", "--json"],
        cwd=repo,
    )[0]
    review = run_json(
        ["bd", "create", "Review architecture: Legacy Feature", "--type", "task", "--parent", root["id"], "--labels", "review:architecture", "--json"],
        cwd=repo,
    )[0]
    closeout = run_json(
        ["bd", "create", "Validate: Legacy Feature", "--type", "task", "--parent", root["id"], "--json"],
        cwd=repo,
    )[0]
    return root, implementation, real, review, closeout


def test_narrow_legacy_adoption_copies_only_selected_real_work(installed_repo: Path) -> None:
    root, implementation, real, review, closeout = create_legacy(installed_repo)
    inspection = ctl(installed_repo, "adopt", "inspect", root["id"])
    assert real["id"] in {item["id"] for item in inspection["classified"]["implementation"]}
    adopted = ctl(
        installed_repo,
        "adopt",
        "apply",
        root["id"],
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
    assert adopted["steps"]["specification"]["status"] == "open"
    assert adopted["human_gate"]["status"] == "open"
    assert len(adopted["work_items"]) == 1
    legacy_view = ctl(installed_repo, "feature", "inspect", root["id"])
    assert legacy_view["root"]["status"] == "closed"
    assert legacy_view["current"] is False
    rerun = ctl(installed_repo, "adopt", "apply", root["id"])
    assert rerun["already_adopted"] is True


def test_alignment_initialize_is_idempotent_and_delivery_resolves_slug(
    installed_repo: Path,
) -> None:
    first = ctl(
        installed_repo,
        "alignment",
        "initialize",
        "--title",
        "Current Architecture",
        "--target-branch",
        "dev",
    )
    second = ctl(
        installed_repo,
        "alignment",
        "initialize",
        "--title",
        "Current Architecture",
        "--target-branch",
        "dev",
    )
    assert second["created"] is False
    assert second["root"]["id"] == first["root"]["id"]

    root_id = first["root"]["id"]
    correction = ctl(
        installed_repo,
        "alignment",
        "add-correction",
        root_id,
        "--title",
        "Align one thing",
        "--acceptance",
        "done",
    )["correction"]
    ctl(installed_repo, "alignment", "finish-plan", root_id)
    ctl(installed_repo, "alignment", "approve", root_id)
    ctl(installed_repo, "alignment", "claim-next", root_id)
    worktree = Path(first["worktree"])
    (worktree / "aligned.txt").write_text("done\n")
    subprocess.run(["git", "add", "aligned.txt"], cwd=worktree, check=True)
    ctl(worktree, "git", "commit", "--bead", correction["id"], "--subject", "fix: align")
    ctl(installed_repo, "alignment", "finish-task", root_id, "--task", correction["id"])
    ctl(installed_repo, "alignment", "finish-workstream", root_id)
    ctl(installed_repo, "alignment", "claim-landing", root_id)
    ctl(installed_repo, "alignment", "finish-landing", root_id)

    delivered = ctl(installed_repo, "delivery", "inspect", "current-architecture")
    assert delivered["kind"] == "alignment"
    assert delivered["root"]["id"] == root_id


def test_adoption_resume_accepts_real_beads_supersedes_direction(
    installed_repo: Path,
    monkeypatch,
) -> None:
    import json
    import os

    root, implementation, real, review, closeout = create_legacy(installed_repo)
    adopted = ctl(
        installed_repo,
        "adopt",
        "apply",
        root["id"],
        "--remaining",
        real["id"],
        "--spec-ceremony",
        review["id"],
        "--implementation-coordinator",
        implementation["id"],
        "--closeout-ceremony",
        closeout["id"],
    )
    state_path = Path(os.environ["DSTACK_FAKE_BD_STATE"])
    state = json.loads(state_path.read_text())
    old = state["issues"][root["id"]]
    old["relations"] = [
        {"to": adopted["root"]["id"], "type": "supersedes"}
    ]
    state_path.write_text(json.dumps(state))

    rerun = ctl(installed_repo, "adopt", "apply", root["id"])
    assert rerun["already_adopted"] is True
    assert rerun["root"]["id"] == adopted["root"]["id"]
