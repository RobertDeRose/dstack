from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import DSTACK, ROOT, run_command, run_ctl, run_json

from dstack.commands import claim_ready_work, reopen_authorization_boundary
from dstack.delivery import (
    cancel_pr_gate,
    pr_gate_state,
    register_pr_gate,
    replace_pr_gates,
)
from dstack.core import BeadsClient, DstackError, root_metadata_value


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


def test_unsupported_ambient_beads_is_rejected_without_initializing(real_repo: Path, tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_bd = fake_bin / "bd"
    fake_bd.write_text("#!/bin/sh\necho 'bd version 1.2.2 (homebrew)'\n")
    fake_bd.chmod(0o755)
    ambient_mise = tmp_path / "ambient-mise"
    ambient_mise.mkdir()
    (ambient_mise / "config.toml").write_text('[tools]\npython = "3.13"\n')
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["MISE_CONFIG_DIR"] = str(ambient_mise)

    result = subprocess.run(
        [str(DSTACK), "ctl", "infra", "check"],
        cwd=real_repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "requires Beads 1.2.2 exactly" in result.stderr
    assert not (real_repo / ".beads").exists()


def test_native_claims_are_scoped_and_atomic_under_concurrency(beads_repo: Path) -> None:
    parent = items(
        run_json(
            beads_repo,
            "create",
            "Concurrent implementation",
            "--type",
            "task",
            "--labels",
            "dstack:work:implementation",
        )
    )[0]
    children = [
        items(
            run_json(
                beads_repo,
                "create",
                f"Concurrent child {suffix}",
                "--type",
                "task",
                "--parent",
                parent["id"],
                "--labels",
                "dstack:work:implementation",
            )
        )[0]
        for suffix in ("a", "b")
    ]
    script = """
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from dstack.commands import claim_ready_work
from dstack.core import BeadsClient
claimed = claim_ready_work(
    BeadsClient(Path.cwd()),
    parent_id=sys.argv[2],
    label="dstack:work:implementation",
)
print(json.dumps(claimed))
"""
    workers = [
        subprocess.Popen(
            [
                "python3",
                "-S",
                "-c",
                script,
                str(ROOT),
                parent["id"],
            ],
            cwd=beads_repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in children
    ]
    results = [worker.communicate(timeout=60) for worker in workers]
    assert all(worker.returncode == 0 for worker in workers), results
    claimed_ids = {json.loads(stdout)["id"] for stdout, _ in results}
    assert claimed_ids == {child["id"] for child in children}


def test_external_dependent_stays_blocked_through_add_before_remove(
    beads_repo: Path,
) -> None:
    old = items(run_json(beads_repo, "create", "legacy blocker", "--type", "task"))[0]
    replacement = items(run_json(beads_repo, "create", "replacement blocker", "--type", "task"))[0]
    dependent = items(run_json(beads_repo, "create", "external dependent", "--type", "task"))[0]
    run_command(
        ["bd", "dep", "add", dependent["id"], old["id"], "--type", "blocks"],
        cwd=beads_repo,
    )
    ready = items(run_json(beads_repo, "ready", "--limit", "0"))
    assert dependent["id"] not in {item["id"] for item in ready}

    run_command(
        [
            "bd",
            "dep",
            "add",
            dependent["id"],
            replacement["id"],
            "--type",
            "blocks",
        ],
        cwd=beads_repo,
    )
    ready = items(run_json(beads_repo, "ready", "--limit", "0"))
    assert dependent["id"] not in {item["id"] for item in ready}

    run_command(
        ["bd", "dep", "remove", dependent["id"], old["id"]],
        cwd=beads_repo,
    )
    ready = items(run_json(beads_repo, "ready", "--limit", "0"))
    assert dependent["id"] not in {item["id"] for item in ready}

    run_command(
        ["bd", "close", replacement["id"], "--reason", "replacement delivered"],
        cwd=beads_repo,
    )
    ready = items(run_json(beads_repo, "ready", "--limit", "0"))
    assert dependent["id"] in {item["id"] for item in ready}


def test_real_adoption_keeps_incoming_dependent_blocked(beads_repo: Path) -> None:
    legacy = items(
        run_json(
            beads_repo,
            "create",
            "Legacy feature",
            "--type",
            "epic",
            "--labels",
            "workflow:feature,feature:legacy-feature",
        )
    )[0]
    child = items(
        run_json(
            beads_repo,
            "create",
            "Remaining work",
            "--type",
            "task",
            "--parent",
            legacy["id"],
        )
    )[0]
    dependent = items(run_json(beads_repo, "create", "External dependent", "--type", "task"))[0]
    run_command(
        ["bd", "dep", "add", dependent["id"], child["id"], "--type", "blocks"],
        cwd=beads_repo,
    )
    classification = {
        "schema": "dstack.adoption-classification/v1",
        "legacy_root_id": legacy["id"],
        "entries": [
            {
                "legacy_id": child["id"],
                "classification": "remaining-implementation",
                "reason": "product work remains",
                "replacement": {
                    "title": "Remaining work",
                    "description": "Continue the remaining work.",
                    "acceptance": "The work is complete.",
                    "priority": 2,
                },
            }
        ],
    }
    classification_file = beads_repo / "classification.json"
    classification_file.write_text(json.dumps(classification))
    result = run_ctl(
        beads_repo,
        "adopt",
        "apply",
        legacy["id"],
        "--title",
        "Adopted feature",
        "--slug",
        "adopted-feature",
        "--classification-file",
        str(classification_file),
    )
    replacement_id = result["mapping"][child["id"]]
    dependent_after = items(run_json(beads_repo, "show", dependent["id"]))[0]
    dependency_ids = {
        str(record.get("depends_on_id") or record.get("id")) for record in dependent_after.get("dependencies", [])
    }
    assert replacement_id in dependency_ids
    assert child["id"] not in dependency_ids
    ready = items(run_json(beads_repo, "ready", "--limit", "0"))
    assert dependent["id"] not in {item["id"] for item in ready}

    run_command(
        [
            "bd",
            "close",
            replacement_id,
            "--force",
            "--reason",
            "replacement delivered",
        ],
        cwd=beads_repo,
    )
    ready = items(run_json(beads_repo, "ready", "--limit", "0"))
    assert dependent["id"] in {item["id"] for item in ready}


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

    specification = by_label(feature_children, "dstack:step:specification")
    specification_blocker = items(
        run_json(
            acceptance_repo,
            "create",
            "specification blocker",
            "--type",
            "task",
        )
    )[0]
    run_command(
        ["bd", "dep", "add", specification["id"], specification_blocker["id"]],
        cwd=acceptance_repo,
    )
    assert (
        items(
            run_json(
                acceptance_repo,
                "ready",
                "--parent",
                feature_root,
                "--label",
                "dstack:step:specification",
                "--claim",
                "--limit",
                "1",
            )
        )
        == []
    )
    assert "assignee" not in items(run_json(acceptance_repo, "show", specification["id"]))[0]
    run_command(
        ["bd", "close", specification_blocker["id"], "--reason", "unblocked"],
        cwd=acceptance_repo,
    )
    claimed_specification = items(
        run_json(
            acceptance_repo,
            "ready",
            "--parent",
            feature_root,
            "--label",
            "dstack:step:specification",
            "--claim",
            "--limit",
            "1",
        )
    )[0]
    assert claimed_specification["id"] == specification["id"]
    run_json(
        acceptance_repo,
        "update",
        specification["id"],
        "--status",
        "open",
        "--assignee",
        "",
    )
    released_specification = items(run_json(acceptance_repo, "show", specification["id"]))[0]
    assert released_specification["status"] == "open"
    assert not released_specification.get("assignee")

    unlike_epic = items(run_json(acceptance_repo, "create", "Unlike epic", "--type", "epic"))[0]
    unlike_task = items(run_json(acceptance_repo, "create", "Unlike task", "--type", "task"))[0]
    unlike_dependency = run_command(
        ["bd", "dep", "add", unlike_task["id"], unlike_epic["id"]],
        cwd=acceptance_repo,
        check=False,
    )
    assert unlike_dependency.returncode != 0

    task = items(
        run_json(
            acceptance_repo,
            "create",
            "contract task",
            "--type",
            "task",
            "--parent",
            implementation["id"],
            "--deps",
            approval["id"],
            "--acceptance",
            "contract behavior",
        )
    )[0]
    native_child = items(
        run_json(
            acceptance_repo,
            "create",
            "native fan-in child",
            "--type",
            "task",
            "--parent",
            implementation["id"],
            "--deps",
            approval["id"],
            "--acceptance",
            "native child completes",
        )
    )[0]
    assert (
        items(
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
        == []
    )
    run_command(
        [
            "bd",
            "close",
            by_label(feature_children, "dstack:step:specification")["id"],
            "--reason",
            "specified",
        ],
        cwd=acceptance_repo,
    )
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
    native_fan_in_gap = items(
        run_json(
            acceptance_repo,
            "ready",
            "--parent",
            feature_root,
            "--label",
            "dstack:step:closeout",
            "--claim",
            "--json",
        )
    )
    claimed_gap = by_label(native_fan_in_gap, "dstack:step:closeout")
    assert claimed_gap["status"] in {"in_progress", "claimed"}
    run_json(
        acceptance_repo,
        "update",
        claimed_gap["id"],
        "--status",
        "open",
    )
    run_command(
        ["bd", "close", native_child["id"], "--reason", "complete"],
        cwd=acceptance_repo,
    )
    claimed_closeout = items(run_json(acceptance_repo, "update", claimed_gap["id"], "--claim"))
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

    client = BeadsClient(acceptance_repo)
    registered = register_pr_gate(client, feature_root, "41")
    assert register_pr_gate(client, feature_root, "41")["id"] == registered["id"]
    with pytest.raises(DstackError, match="conflicting PR gate"):
        register_pr_gate(client, feature_root, "42")

    duplicate = client.create_gate(
        gate_type="gh:pr",
        blocks=feature_root,
        await_id="41",
        reason="acceptance duplicate",
    )
    client.resolve_gate(duplicate["id"], "acceptance closed duplicate")
    with pytest.raises(DstackError, match="ambiguous PR gates"):
        register_pr_gate(client, feature_root, "41")

    replacement, replaced = replace_pr_gates(
        client,
        feature_root,
        "42",
        "acceptance repair",
    )
    assert set(replaced) == {registered["id"], duplicate["id"]}
    assert replace_pr_gates(
        client,
        feature_root,
        "42",
        "acceptance retry",
    ) == (replacement, [])
    active = pr_gate_state(client, feature_root)["active"]
    assert [gate["id"] for gate in active] == [replacement["id"]]
    cancelled = cancel_pr_gate(client, feature_root, "use direct delivery")
    assert cancelled["id"] == replacement["id"]
    gate_state = pr_gate_state(client, feature_root)
    assert gate_state["active"] == []
    assert [gate["id"] for gate in gate_state["all"] if gate["id"] == replacement["id"]]
    root_after_cancellation = client.show(feature_root)
    assert any(
        str(record.get("depends_on_id") or record.get("id")) == replacement["id"]
        and str(record.get("type") or record.get("dependency_type")) == "relates-to"
        for record in root_after_cancellation.get("dependencies", [])
    )

    client.update(
        feature_root,
        "--set-metadata",
        "dstack.approved_design_sha256=accepted",
    )
    client.update(claimed_closeout[0]["id"], "--status", "open", "--assignee", "")
    reopen_authorization_boundary(
        client,
        root_id=feature_root,
        planning_id=by_label(feature_children, "dstack:step:specification")["id"],
        approval_id=approval["id"],
        gate_id=gate["id"],
        workstream_id=implementation["id"],
        terminal_id=claimed_closeout[0]["id"],
        reason="contract scope revision",
        digest_key="dstack.approved_design_sha256",
    )
    assert root_metadata_value(client.show(feature_root), "dstack.approved_design_sha256") is None
    assert all(
        client.show(issue_id)["status"] == "open"
        for issue_id in (
            by_label(feature_children, "dstack:step:specification")["id"],
            approval["id"],
            gate["id"],
            implementation["id"],
        )
    )
    revision = client.create(
        "authorized revision",
        parent=implementation["id"],
        labels=["dstack:work:implementation"],
        dependencies=[approval["id"]],
        acceptance="revision remains blocked before renewed approval",
    )
    assert revision["id"] not in {
        item["id"] for item in client.ready_children(implementation["id"], label="dstack:work:implementation")
    }
    with pytest.raises(DstackError, match="not currently ready"):
        claim_ready_work(
            client,
            parent_id=implementation["id"],
            label="dstack:work:implementation",
            requested_id=revision["id"],
        )
    assert client.show(revision["id"])["status"] == "open"
    wrong_label = client.create(
        "wrong label",
        parent=implementation["id"],
        acceptance="validation refuses this task",
    )
    with pytest.raises(DstackError, match="lacks required label"):
        claim_ready_work(
            client,
            parent_id=implementation["id"],
            label="dstack:work:implementation",
            requested_id=wrong_label["id"],
        )
    wrong_parent = client.create(
        "wrong parent",
        parent=feature_root,
        labels=["dstack:work:implementation"],
        acceptance="validation refuses this task",
    )
    with pytest.raises(DstackError, match="not a direct child"):
        claim_ready_work(
            client,
            parent_id=implementation["id"],
            label="dstack:work:implementation",
            requested_id=wrong_parent["id"],
        )
    client.close(
        by_label(feature_children, "dstack:step:specification")["id"],
        "renewed specification",
    )
    client.resolve_gate(gate["id"], "renewed approval")
    client.close(approval["id"], "renewed approval")
    client.resolve_gate(replacement["id"], "acceptance claim verification")
    claimed_revision = claim_ready_work(
        client,
        parent_id=implementation["id"],
        label="dstack:work:implementation",
        requested_id=revision["id"],
    )
    assert claimed_revision and claimed_revision["id"] == revision["id"]

    client.update(claimed_landing[0]["id"], "--status", "open", "--assignee", "")
    reopen_authorization_boundary(
        client,
        root_id=alignment_root,
        planning_id=alignment_analysis["id"],
        approval_id=alignment_approval["id"],
        gate_id=alignment_gate["id"],
        workstream_id=corrections["id"],
        terminal_id=claimed_landing[0]["id"],
        reason="contract alignment revision",
    )
    assert all(
        client.show(issue_id)["status"] == "open"
        for issue_id in (
            alignment_analysis["id"],
            alignment_approval["id"],
            alignment_gate["id"],
            corrections["id"],
        )
    )
