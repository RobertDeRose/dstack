from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import run_command, run_json


def items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    return [payload] if isinstance(payload, dict) and payload.get("id") else []


def by_label(values, label: str) -> dict:
    matches = [item for item in values if label in item.get("labels", [])]
    assert len(matches) == 1, (label, matches)
    return matches[0]


def test_bd_contract_covers_native_primitives(beads_repo: Path) -> None:
    acceptance_repo = beads_repo
    feature = run_json(acceptance_repo, "formula", "show", "dstack-feature")
    alignment = run_json(acceptance_repo, "formula", "show", "dstack-project-alignment")
    assert {step["id"] for step in feature["steps"]} == {
        "specification",
        "approval",
        "implementation",
        "closeout",
    }
    assert {step["id"] for step in alignment["steps"]} == {
        "analysis",
        "approval",
        "corrections",
        "landing",
    }
    assert {step["id"]: step["type"] for step in feature["steps"]} == {
        "specification": "task",
        "approval": "task",
        "implementation": "epic",
        "closeout": "task",
    }
    assert {step["id"]: step["type"] for step in alignment["steps"]} == {
        "analysis": "task",
        "approval": "task",
        "corrections": "epic",
        "landing": "task",
    }
    assert next(step for step in feature["steps"] if step["id"] == "approval")["gate"]["type"] == "human"

    poured_feature = run_json(
        acceptance_repo,
        "mol",
        "pour",
        "dstack-feature",
        "--var",
        "feature_title=Contract Feature",
        "--var",
        "feature_slug=contract-feature",
        "--var",
        "design_path=docs/src/features/contract-feature/design.md",
    )
    poured_alignment = run_json(
        acceptance_repo,
        "mol",
        "pour",
        "dstack-project-alignment",
        "--var",
        "audit_title=Contract Alignment",
        "--var",
        "audit_slug=contract-alignment",
        "--var",
        "scope=contract",
    )
    feature_root = str(poured_feature.get("root_id") or poured_feature["new_epic_id"])
    alignment_root = str(poured_alignment.get("root_id") or poured_alignment["new_epic_id"])
    feature_children = items(run_json(acceptance_repo, "list", "--all", "--parent", feature_root, "--limit", "0"))
    alignment_children = items(run_json(acceptance_repo, "list", "--all", "--parent", alignment_root, "--limit", "0"))
    implementation = by_label(feature_children, "dstack:step:implementation")
    approval = by_label(feature_children, "dstack:step:implementation-approval")
    closeout_step = next(step for step in feature["steps"] if step["id"] == "closeout")
    assert closeout_step["waits_for"] == "children-of(implementation)"
    assert by_label(alignment_children, "dstack:step:alignment-corrections")["issue_type"] == "epic"

    gates = items(run_json(acceptance_repo, "gate", "list", "--all", "--limit", "0"))
    approval_full = items(run_json(acceptance_repo, "show", approval["id"]))[0]
    gate_ids = {
        str(record.get("depends_on_id") or record.get("id")) for record in approval_full.get("dependencies", [])
    }
    gate = next(item for item in gates if str(item["id"]) in gate_ids)
    assert gate.get("await_type") == "human"

    task = items(run_json(
        acceptance_repo, "create", "contract task", "--type", "task",
        "--parent", implementation["id"], "--deps", approval["id"],
        "--acceptance", "contract behavior",
    ))[0]
    native_child = items(run_json(
        acceptance_repo, "create", "native fan-in child", "--type", "task",
        "--parent", implementation["id"], "--deps", approval["id"],
        "--acceptance", "native child completes",
    ))[0]
    assert items(run_json(
        acceptance_repo, "ready", "--parent", implementation["id"],
        "--exclude-type", "epic,molecule,gate", "--limit", "0",
    )) == []
    run_command(["bd", "close", by_label(feature_children, "dstack:step:specification")["id"], "--reason", "specified"], cwd=acceptance_repo)
    run_command(["bd", "gate", "resolve", gate["id"], "--reason", "approved"], cwd=acceptance_repo)
    run_command(["bd", "close", approval["id"], "--reason", "approved"], cwd=acceptance_repo)
    ready = items(
        run_json(
            acceptance_repo,
            "ready",
            "--parent",
            implementation["id"],
            "--exclude-type",
            "epic,molecule,gate",
            "--limit",
            "0",
        )
    )
    assert {item["id"] for item in ready} == {task["id"], native_child["id"]}
    claimed = items(run_json(acceptance_repo, "update", task["id"], "--claim"))[0]
    assert claimed["status"] in {"in_progress", "claimed"}

    owned = items(
        run_json(
            acceptance_repo,
            "create",
            "owned task",
            "--type",
            "task",
            "--parent",
            implementation["id"],
            "--deps",
            approval["id"],
            "--acceptance",
            "ownership remains atomic",
        )
    )[0]
    run_json(acceptance_repo, "update", owned["id"], "--claim", "--actor", "owner-a")
    conflict = run_command(
        ["bd", "update", owned["id"], "--claim", "--actor", "owner-b", "--json"],
        cwd=acceptance_repo,
        check=False,
    )
    assert conflict.returncode != 0

    run_command(
        ["bd", "close", task["id"], "--reason", "complete"],
        cwd=acceptance_repo,
    )
    run_command(
        ["bd", "close", owned["id"], "--reason", "complete", "--actor", "owner-a"],
        cwd=acceptance_repo,
    )
    run_command(
        ["bd", "close", native_child["id"], "--reason", "complete"],
        cwd=acceptance_repo,
    )
    claimed_closeout = items(run_json(
        acceptance_repo, "ready", "--parent", feature_root,
        "--label", "dstack:step:closeout", "--claim", "--json",
    ))
    assert by_label(claimed_closeout, "dstack:step:closeout")["status"] in {
        "in_progress",
        "claimed",
    }
    closeout = items(run_json(acceptance_repo, "show", claimed_closeout[0]["id"]))[0]
    assert closeout["status"] in {"in_progress", "claimed"}
    run_command(
        ["bd", "close", implementation["id"], "--reason", "children complete"],
        cwd=acceptance_repo,
    )

    corrections = by_label(alignment_children, "dstack:step:alignment-corrections")
    alignment_approval = by_label(alignment_children, "dstack:step:alignment-approval")
    alignment_analysis = by_label(alignment_children, "dstack:step:alignment-analysis")
    alignment_gate_ids = {
        str(record.get("depends_on_id") or record.get("id"))
        for record in items(run_json(acceptance_repo, "show", alignment_approval["id"]))[0].get("dependencies", [])
    }
    alignment_gate = next(item for item in gates if str(item["id"]) in alignment_gate_ids)
    correction = items(
        run_json(
            acceptance_repo,
            "create",
            "native correction",
            "--type",
            "task",
            "--parent",
            corrections["id"],
            "--deps",
            alignment_approval["id"],
            "--acceptance",
            "correction completes",
        )
    )[0]
    run_command(
        ["bd", "close", alignment_analysis["id"], "--reason", "analyzed"],
        cwd=acceptance_repo,
    )
    run_command(
        ["bd", "gate", "resolve", alignment_gate["id"], "--reason", "approved"],
        cwd=acceptance_repo,
    )
    run_command(
        ["bd", "close", alignment_approval["id"], "--reason", "approved"],
        cwd=acceptance_repo,
    )
    assert (
        items(
            run_json(
                acceptance_repo,
                "ready",
                "--parent",
                alignment_root,
                "--label",
                "dstack:step:alignment-landing",
                "--claim",
                "--json",
            )
        )
        == []
    )
    run_command(
        ["bd", "close", correction["id"], "--reason", "complete"],
        cwd=acceptance_repo,
    )
    claimed_landing = items(
        run_json(
            acceptance_repo,
            "ready",
            "--parent",
            alignment_root,
            "--label",
            "dstack:step:alignment-landing",
            "--claim",
            "--json",
        )
    )
    assert by_label(claimed_landing, "dstack:step:alignment-landing")["status"] in {
        "in_progress",
        "claimed",
    }

    old = items(run_json(acceptance_repo, "create", "old item", "--type", "task"))[0]
    new = items(run_json(acceptance_repo, "create", "replacement item", "--type", "task"))[0]
    run_command(["bd", "supersede", old["id"], "--with", new["id"]], cwd=acceptance_repo)
    superseded = items(run_json(acceptance_repo, "show", old["id"]))[0]
    assert superseded["status"] == "closed"
    assert any(
        str(record.get("depends_on_id") or record.get("id")) == new["id"]
        for record in superseded.get("dependencies", [])
    )

    branch = "contract-worktree"
    subprocess.run(["git", "branch", branch], cwd=acceptance_repo, check=True, capture_output=True)
    worktree = acceptance_repo.parent / "contract-worktree"
    run_command(["bd", "worktree", "create", str(worktree), "--branch", branch], cwd=acceptance_repo)
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=acceptance_repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert f"branch refs/heads/{branch}" in listing
