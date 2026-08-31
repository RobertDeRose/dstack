from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from conftest import run_command, run_ctl, run_json

from dstack.docs import RECORD_SUBJECTS  # noqa: E402


def semantic_record(kind: str) -> str:
    lines = ["# Acceptance record", ""]
    for subject in RECORD_SUBJECTS[kind]:
        lines.extend([f"## {subject}", "", f"Acceptance evidence for {subject}.", ""])
    return "\n".join(lines)


def items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    return [payload] if isinstance(payload, dict) and payload.get("id") else []


def by_label(values: list[dict], label: str) -> dict:
    matches = [item for item in values if label in item.get("labels", [])]
    assert len(matches) == 1, (label, matches)
    return matches[0]


def dependency_ids(issue: dict, relation: str = "blocks") -> set[str]:
    return {
        str(record.get("depends_on_id") or record.get("id"))
        for record in issue.get("dependencies", [])
        if (record.get("type") or record.get("dependency_type") or "blocks") == relation
    }


def resolved_id(repo: Path, selector: str) -> str:
    return run_ctl(repo, "feature", "resolve", selector)["root"]["id"]


def test_no_change_alignment_landing_has_no_git_candidate(
    acceptance_repo: Path,
) -> None:
    alignment = run_ctl(
        acceptance_repo,
        "alignment",
        "initialize",
        "--title",
        "No-change alignment",
        "--slug",
        "no-change-alignment",
        "--target-branch",
        "main",
        "--scope",
        "repository",
    )
    root_id = alignment["root"]["id"]
    correction = run_ctl(
        acceptance_repo,
        "alignment",
        "add-correction",
        root_id,
        "--title",
        "Confirm alignment",
        "--description",
        "Confirm that the repository already satisfies the requirement.",
        "--acceptance",
        "The correction closes without repository changes.",
    )["correction"]
    review_file = acceptance_repo.parent / "no-change-alignment-review.md"
    review_file.write_text(
        "# Alignment review\n\n"
        "The repository already satisfies the reviewed requirement. The native correction graph records the "
        "single verification task and no repository change is expected.\n"
    )
    run_ctl(
        acceptance_repo,
        "alignment",
        "finish-plan",
        root_id,
        "--summary-file",
        str(review_file),
    )
    run_ctl(acceptance_repo, "alignment", "approve", root_id)
    run_ctl(acceptance_repo, "alignment", "claim-next", root_id)
    run_ctl(
        acceptance_repo,
        "alignment",
        "finish-task",
        root_id,
        "--task",
        correction["id"],
        "--no-repository-change",
        "--reason",
        "repository already aligned",
    )
    run_ctl(acceptance_repo, "alignment", "finish-workstream", root_id)
    run_ctl(acceptance_repo, "alignment", "claim-landing", root_id)
    summary = acceptance_repo.parent / "no-change-alignment-reconciliation.md"
    summary.write_text(semantic_record("alignment-reconciliation"))
    landed = run_ctl(
        acceptance_repo,
        "alignment",
        "finish-landing",
        root_id,
        "--summary-file",
        str(summary),
    )
    assert landed["landing"]["close_reason"] == "Alignment landing completed"

    inspected = run_ctl(acceptance_repo, "delivery", "inspect", root_id)
    assert inspected["candidate_revision"] is None
    assert inspected["candidate_head"]
    assert inspected["evidence"]["candidate_revision"] is None
    assert inspected["evidence"]["evidence_source"] is None
    assert inspected["evidence"]["derivation"] == "no repository change"


def test_feature_smoke_runs_shipped_lifecycle(acceptance_repo: Path) -> None:
    before = run_command(["git", "status", "--porcelain=v1", "--branch"], cwd=acceptance_repo).stdout
    blocker_a = items(run_json(acceptance_repo, "create", "External blocker A", "--type", "epic"))[0]
    blocker_b = items(run_json(acceptance_repo, "create", "External blocker B", "--type", "epic"))[0]
    unrelated = items(run_json(acceptance_repo, "create", "Related planning context", "--type", "epic"))[0]
    body_file = acceptance_repo.parent / "planned-feature.md"
    initial_body = """# Goal

Ship detailed smoke behavior without losing multiline intent.

# Requirements

- Preserve native Beads fields.
- Keep the accepted four-stage workflow.

# Dependencies

External blocker A must ship first.
"""
    initial_acceptance = "Multiline planned intent survives materialization."
    body_file.write_text(initial_body)
    planned_result = run_ctl(
        acceptance_repo,
        "feature",
        "plan",
        "--title",
        "Acceptance smoke",
        "--slug",
        "acceptance-smoke",
        "--body-file",
        str(body_file),
        "--acceptance",
        initial_acceptance,
        "--priority",
        "1",
        "--depends-on",
        blocker_a["id"],
    )
    assert planned_result["created"] is True
    planned = planned_result["planned_feature"]
    run_command(
        [
            "bd",
            "dep",
            "add",
            planned["id"],
            unrelated["id"],
            "--type",
            "tracks",
        ],
        cwd=acceptance_repo,
    )
    planned = items(run_json(acceptance_repo, "show", planned["id"]))[0]
    assert planned["description"] == initial_body
    assert planned["acceptance_criteria"] == initial_acceptance
    assert planned["priority"] == 1
    assert dependency_ids(planned) == {blocker_a["id"]}
    assert dependency_ids(planned, "tracks") == {unrelated["id"]}
    for selector in (planned["id"], "acceptance-smoke", "Acceptance smoke"):
        assert resolved_id(acceptance_repo, selector) == planned["id"]

    revised_body = """# Goal

Ship revised smoke behavior while retaining every durable planning decision.

# Requirements

- Preserve revised multiline native Beads intent.
- Keep the accepted four-stage workflow.

# Dependencies

External blocker B replaces blocker A.
"""
    revised_acceptance = "Revised intent, priority, and blocker survive materialization."
    revised_title = "Acceptance smoke revised"
    body_file.write_text(revised_body)
    replanned = run_ctl(
        acceptance_repo,
        "feature",
        "plan",
        planned["id"],
        "--title",
        revised_title,
        "--body-file",
        str(body_file),
        "--acceptance",
        revised_acceptance,
        "--priority",
        "3",
        "--depends-on",
        blocker_b["id"],
    )
    assert replanned["created"] is False
    assert replanned["planned_feature"]["id"] == planned["id"]
    body_file.unlink()

    planned = items(run_json(acceptance_repo, "show", planned["id"]))[0]
    assert planned["title"] == revised_title
    assert planned["description"] == revised_body
    assert planned["acceptance_criteria"] == revised_acceptance
    assert planned["priority"] == 3
    assert dependency_ids(planned) == {blocker_b["id"]}
    assert dependency_ids(planned, "tracks") == {unrelated["id"]}
    for selector in (planned["id"], "acceptance-smoke", revised_title):
        assert resolved_id(acceptance_repo, selector) == planned["id"]
    assert (
        len(
            [
                issue
                for issue in items(run_json(acceptance_repo, "list", "--all"))
                if "dstack:feature-idea" in issue.get("labels", [])
            ]
        )
        == 1
    )
    assert run_command(["git", "status", "--porcelain=v1", "--branch"], cwd=acceptance_repo).stdout == before

    created = run_ctl(acceptance_repo, "feature", "initialize", planned["id"], "--base-branch", "main")
    assert created["planned_source"] == planned["id"]
    assert created["root"]["description"] == revised_body
    assert created["root"]["acceptance_criteria"] == revised_acceptance
    assert created["root"]["priority"] == 3
    assert created["preserved_blockers"] == [blocker_b["id"]]
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    run_ctl(acceptance_repo, "feature", "claim-spec", root_id)
    scaffolded = run_ctl(acceptance_repo, "feature", "scaffold-design", root_id)
    assert scaffolded["created"] is True
    design = worktree / created["design_path"]
    accepted_design = semantic_record("feature-design")
    design.write_text(accepted_design)

    worktrees = run_command(["git", "worktree", "list", "--porcelain"], cwd=acceptance_repo).stdout
    for selector in (planned["id"], "acceptance-smoke", revised_title):
        repeated = run_ctl(acceptance_repo, "feature", "initialize", selector, "--base-branch", "main")
        assert repeated["created"] is False
        assert repeated["root"]["id"] == root_id
        assert Path(repeated["worktree"]) == worktree
    assert run_command(["git", "worktree", "list", "--porcelain"], cwd=acceptance_repo).stdout == worktrees
    assert run_ctl(acceptance_repo, "feature", "scaffold-design", root_id)["created"] is False
    assert design.read_text() == accepted_design
    current_roots = [
        issue
        for issue in items(run_json(acceptance_repo, "list", "--all"))
        if "workflow:feature" in issue.get("labels", [])
    ]
    assert [issue["id"] for issue in current_roots] == [root_id]
    current_graph = [
        items(run_json(acceptance_repo, "show", root_id))[0],
        *items(
            run_json(
                acceptance_repo,
                "list",
                "--all",
                "--parent",
                root_id,
                "--limit",
                "0",
            )
        ),
    ]
    assert any(blocker_b["id"] in dependency_ids(issue) for issue in current_graph)
    assert all(blocker_a["id"] not in dependency_ids(issue) for issue in current_graph)
    source = items(run_json(acceptance_repo, "show", planned["id"]))[0]
    assert source["status"] == "closed"
    assert root_id in dependency_ids(source, "supersedes")
    materialized = items(run_json(acceptance_repo, "show", root_id))[0]
    assert materialized["description"] == revised_body
    assert materialized["acceptance_criteria"] == revised_acceptance
    assert materialized["priority"] == 3
    implementation = by_label(current_graph, "dstack:step:implementation")
    approval = by_label(current_graph, "dstack:step:implementation-approval")
    native_child = items(
        run_json(
            acceptance_repo,
            "create",
            "Native fan-in child",
            "--type",
            "task",
            "--parent",
            implementation["id"],
            "--deps",
            approval["id"],
            "--acceptance",
            "Terminal claim waits for every direct child.",
        )
    )[0]
    task = run_ctl(
        acceptance_repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Ship smoke behavior",
        "--acceptance",
        "The smoke behavior is delivered with Git evidence.",
    )["task"]

    subprocess.run(["git", "add", "docs"], cwd=worktree, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            f"docs: accept smoke design\n\nBeads: {created['steps']['specification']['id']}",
        ],
        cwd=worktree,
        check=True,
    )
    accepted_design = design.read_text()
    design.write_text(accepted_design + "uncommitted\n")
    refused_approval = run_ctl(
        acceptance_repo,
        "feature",
        "approve-spec",
        root_id,
        check=False,
    )
    assert refused_approval.returncode != 0
    subprocess.run(["git", "checkout", "--", created["design_path"]], cwd=worktree, check=True)
    approved = run_ctl(acceptance_repo, "feature", "approve-spec", root_id)
    head_design = subprocess.run(
        ["git", "show", f"HEAD:{created['design_path']}"],
        cwd=worktree,
        check=True,
        capture_output=True,
    ).stdout
    assert approved["approved_design_sha256"] == hashlib.sha256(head_design).hexdigest()
    approved_root = items(run_json(acceptance_repo, "show", root_id))[0]
    assert "dstack.pending_design_sha256" not in approved_root.get("metadata", {})
    assert int(approved_root["metadata"]["dstack.created_formula_version"]) == 9
    assert int(approved_root["metadata"]["dstack.formula_version"]) == 9

    # Formula contract drift is an internal semantic audit boundary, not a migration.
    run_json(
        acceptance_repo,
        "update",
        root_id,
        "--set-metadata",
        "dstack.formula_version=8",
    )
    stale = run_ctl(acceptance_repo, "feature", "claim-next", root_id, check=False)
    assert stale.returncode == 3
    stale_payload = json.loads(stale.stderr)
    assert stale_payload["status"] == "audit_required"
    assert stale_payload["from_version"] == 8
    assert stale_payload["to_version"] == 9
    assert stale_payload["skill"] == "dstack-beads-review-feature-spec"
    run_ctl(acceptance_repo, "feature", "audit-complete", root_id)
    audited_root = items(run_json(acceptance_repo, "show", root_id))[0]
    assert int(audited_root["metadata"]["dstack.formula_version"]) == 9
    audited_task = items(run_json(acceptance_repo, "show", task["id"]))[0]
    assert int(audited_task["metadata"]["dstack.formula_version"]) == 9
    late_refused = run_ctl(
        acceptance_repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Late unauthorized scope",
        "--acceptance",
        "This child must not be created after approval.",
        check=False,
    )
    assert late_refused.returncode != 0
    run_command(
        ["bd", "close", blocker_b["id"], "--reason", "external dependency delivered"],
        cwd=acceptance_repo,
    )
    change = worktree / "smoke.py"
    change.write_text("SMOKE = True\n")
    subprocess.run(
        ["git", "add", "smoke.py"],
        cwd=worktree,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", f"feat: ship smoke behavior\n\nBeads: {task['id']}"],
        cwd=worktree,
        check=True,
    )
    run_ctl(acceptance_repo, "feature", "finish-task", root_id, "--task", task["id"])
    refused = run_ctl(
        acceptance_repo,
        "feature",
        "claim-closeout",
        root_id,
        check=False,
    )
    assert refused.returncode != 0
    assert native_child["id"] in refused.stderr
    assert items(run_json(acceptance_repo, "show", created["steps"]["closeout"]["id"]))[0]["status"] == "open"
    run_command(
        [
            "bd",
            "close",
            native_child["id"],
            "--reason",
            "no-repository-change: fan-in acceptance only",
        ],
        cwd=acceptance_repo,
    )
    run_ctl(acceptance_repo, "feature", "finish-workstream", root_id)
    claimed_closeout = run_ctl(acceptance_repo, "feature", "claim-closeout", root_id)
    reconciliation = run_ctl(acceptance_repo, "feature", "scaffold-reconciliation", root_id)
    reconciliation_text = semantic_record("feature-reconciliation").replace(
        "Acceptance evidence for Delivered outcome.",
        "The smoke behavior is delivered. [Architecture](../../architecture/index.md)",
    )
    (worktree / reconciliation["reconciliation_path"]).write_text(reconciliation_text)
    subprocess.run(["git", "add", "docs"], cwd=worktree, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            f"docs: reconcile smoke feature\n\nBeads: {claimed_closeout['closeout']['id']}",
        ],
        cwd=worktree,
        check=True,
    )
    run_ctl(acceptance_repo, "feature", "finish-closeout", root_id)
    fixup = worktree / "smoke-fixup.py"
    fixup.write_text("SMOKE_FIXUP = True\n")
    subprocess.run(["git", "add", "smoke-fixup.py"], cwd=worktree, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            f"fixup: refine smoke behavior\n\nBeads: {claimed_closeout['closeout']['id']}",
        ],
        cwd=worktree,
        check=True,
    )
    ready_root = run_json(acceptance_repo, "show", root_id)
    assert ready_root[0]["status"] == "open"

    delivered = run_ctl(acceptance_repo, "delivery", "merge", root_id)
    assert delivered["root"] == root_id
    assert delivered["previous_target_head"] != delivered["delivered_head"]
    closed = run_json(acceptance_repo, "show", root_id)
    assert closed[0]["status"] == "closed"
    subprocess.run(
        ["git", "worktree", "remove", str(worktree)],
        cwd=acceptance_repo,
        check=True,
    )
    subprocess.run(
        ["git", "branch", "-d", created["branch"]],
        cwd=acceptance_repo,
        check=True,
    )
    delivered_audit = run_ctl(
        acceptance_repo,
        "audit",
        "feature",
        root_id,
        "--format",
        "json",
        "--verbose",
    )
    assert delivered_audit["git_evidence"]["status"] == "ok"
    assert delivered_audit["git_evidence"]["source"] == "delivered-target"
    assert delivered_audit["git_evidence"]["feature_branch_present"] is False
    assert task["id"] in delivered_audit["git_evidence"]["mapping"]
    assert claimed_closeout["closeout"]["id"] in delivered_audit["git_evidence"]["mapping"]

    alignment = run_ctl(
        acceptance_repo,
        "alignment",
        "initialize",
        "--title",
        "Acceptance alignment",
        "--slug",
        "acceptance-alignment",
        "--target-branch",
        "main",
        "--scope",
        "repository",
    )
    alignment_root = alignment["root"]["id"]
    alignment_worktree = Path(alignment["worktree"])
    correction = run_ctl(
        acceptance_repo,
        "alignment",
        "add-correction",
        alignment_root,
        "--title",
        "Add aligned behavior",
        "--description",
        "Implement aligned behavior in the acceptance repository.",
        "--acceptance",
        "The correction is committed and delivered with native readiness.",
    )["correction"]
    alignment_graph = run_ctl(acceptance_repo, "alignment", "inspect", alignment_root, "--verbose")
    native_correction = items(
        run_json(
            acceptance_repo,
            "create",
            "Native alignment child",
            "--type",
            "task",
            "--parent",
            alignment_graph["steps"]["corrections"]["id"],
            "--deps",
            f"{alignment_graph['steps']['approval']['id']},{correction['id']}",
            "--labels",
            "dstack:work:correction",
            "--no-inherit-labels",
            "--description",
            "Preserve fan-in acceptance behavior.",
            "--acceptance",
            "Landing waits for every direct child.",
        )
    )[0]
    alignment_review = acceptance_repo.parent / "alignment-review.md"
    alignment_review.write_text(
        "# Alignment review\n\n"
        "The correction graph contains the accepted repository change and a native fan-in verification task. "
        "Current Git and Beads state will be revalidated at execution and delivery.\n"
    )
    run_ctl(
        acceptance_repo,
        "alignment",
        "finish-plan",
        alignment_root,
        "--summary-file",
        str(alignment_review),
    )
    run_command(
        ["bd", "dep", "add", native_correction["id"], unrelated["id"], "--type", "related"],
        cwd=acceptance_repo,
    )
    drifted = run_ctl(
        acceptance_repo,
        "alignment",
        "approve",
        alignment_root,
        check=False,
    )
    assert drifted.returncode != 0
    assert "review identity" in drifted.stderr
    run_command(
        ["bd", "dep", "remove", native_correction["id"], unrelated["id"]],
        cwd=acceptance_repo,
    )
    run_ctl(acceptance_repo, "alignment", "approve", alignment_root)
    late_correction_refused = run_ctl(
        acceptance_repo,
        "alignment",
        "add-correction",
        alignment_root,
        "--title",
        "Late unauthorized correction",
        "--acceptance",
        "This correction must not be created after approval.",
        check=False,
    )
    assert late_correction_refused.returncode != 0
    claimed_correction = run_ctl(acceptance_repo, "alignment", "claim-next", alignment_root)["correction"]
    assert claimed_correction["id"] == correction["id"]

    (alignment_worktree / "aligned.py").write_text("ALIGNED = True\n")
    subprocess.run(["git", "add", "aligned.py"], cwd=alignment_worktree, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            f"fix: align acceptance repository\n\nBeads: {correction['id']}",
        ],
        cwd=alignment_worktree,
        check=True,
    )
    finished_correction = run_ctl(
        acceptance_repo,
        "alignment",
        "finish-task",
        alignment_root,
        "--task",
        correction["id"],
    )
    assert finished_correction["workstream"]["workstream"]["status"] == "open"
    refused_landing = run_ctl(
        acceptance_repo,
        "alignment",
        "claim-landing",
        alignment_root,
        check=False,
    )
    assert refused_landing.returncode != 0
    assert native_correction["id"] in refused_landing.stderr
    run_command(
        [
            "bd",
            "close",
            native_correction["id"],
            "--reason",
            "no-repository-change: fan-in acceptance only",
        ],
        cwd=acceptance_repo,
    )
    run_ctl(acceptance_repo, "alignment", "finish-workstream", alignment_root)
    run_ctl(acceptance_repo, "alignment", "claim-landing", alignment_root)
    alignment_reconciliation = acceptance_repo.parent / "alignment-reconciliation.md"
    alignment_reconciliation.write_text(semantic_record("alignment-reconciliation"))
    landed = run_ctl(
        acceptance_repo,
        "alignment",
        "finish-landing",
        alignment_root,
        "--reason",
        "Acceptance alignment reconciled",
        "--summary-file",
        str(alignment_reconciliation),
    )
    assert landed["landing"]["status"] == "closed"
    assert landed["evidence"]["status"] == "ok"
    assert landed["documentation"]["status"] == "ok"
    alignment_fixup = alignment_worktree / "alignment-fixup.py"
    alignment_fixup.write_text("ALIGNMENT_FIXUP = True\n")
    subprocess.run(["git", "add", "alignment-fixup.py"], cwd=alignment_worktree, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            f"fixup: refine alignment behavior\n\nBeads: {landed['landing']['id']}",
        ],
        cwd=alignment_worktree,
        check=True,
    )
    alignment_fixup_candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=alignment_worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ready_alignment = items(run_json(acceptance_repo, "show", alignment_root))[0]
    assert ready_alignment["status"] == "open"

    delivered_alignment = run_ctl(acceptance_repo, "delivery", "merge", alignment_root)
    assert delivered_alignment["root"] == alignment_root
    alignment_closed = items(run_json(acceptance_repo, "show", alignment_root))[0]
    assert alignment_closed["status"] == "closed"
    subprocess.run(
        ["git", "worktree", "remove", str(alignment_worktree)],
        cwd=acceptance_repo,
        check=True,
    )
    subprocess.run(
        ["git", "branch", "-d", "audit/acceptance-alignment"],
        cwd=acceptance_repo,
        check=True,
    )
    (acceptance_repo / "after-alignment.txt").write_text("target advanced\n")
    subprocess.run(["git", "add", "after-alignment.txt"], cwd=acceptance_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "chore: advance after alignment"],
        cwd=acceptance_repo,
        check=True,
    )
    delivered_alignment_inspection = run_ctl(acceptance_repo, "delivery", "inspect", alignment_root)
    assert delivered_alignment_inspection["delivery_state"] == "delivered"
    assert delivered_alignment_inspection["candidate_worktree"] is None
    assert delivered_alignment_inspection["evidence"]["source"] == "delivered-target"
    assert delivered_alignment_inspection["evidence"]["candidate_branch_present"] is False
    assert delivered_alignment_inspection["evidence"]["candidate_revision"] == alignment_fixup_candidate
    assert delivered_alignment_inspection["evidence"]["derivation"] == ("latest reachable landing Beads footer")
