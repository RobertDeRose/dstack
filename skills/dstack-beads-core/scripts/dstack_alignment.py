#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from dstacklib import (
    BeadsClient,
    DstackError,
    alignment_context,
    alignment_view,
    ancestry,
    branch_exists,
    conventional_worktree,
    ensure_clean_worktree,
    human_gate_for_step,
    read_text_file,
    run,
    slugify,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)

from dstack_commands import (
    ALIGNMENT_RECONCILIATION_SCAFFOLD,
    claim_ready_step,
    claim_ready_step_with_fan_in,
    claim_ready_work,
    close_issue_if_needed,
    resolve_gate_if_needed,
    client_for,
    completion_reason,
    emit,
    ensure_branch_worktree,
    evidence_for_bead,
    keep_root_open_for_delivery,
    open_workstream_children,
    reject_documentation_work,
    require_installed_formula,
    require_no_documentation_changes,
    reopen_authorization_boundary,
    required_task_text,
    task_text,
)
from dstack_docs import validate_docs, validate_record
from dstack_alignment_plan import (
    canonical_description,
    parse_plan_file,
    require_alignment_authorized,
    require_current_plan,
    root_plan_metadata,
    verify_correction_graph,
)


def cmd_alignment_scaffold_record(args: argparse.Namespace) -> int:
    if args.kind != "reconciliation":
        raise DstackError("alignment plan authoring uses canonical JSON --plan-file")
    scaffold = ALIGNMENT_RECONCILIATION_SCAFFOLD
    try:
        with args.path.open("x", encoding="utf-8") as handle:
            handle.write(scaffold)
    except FileExistsError as exc:
        raise DstackError(f"alignment record already exists: {args.path}") from exc
    emit({"status": "ok", "kind": args.kind, "path": str(args.path)})
    return 0


def cmd_alignment_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_view(client, args.selector)
    try:
        require_alignment_authorized(client, view)
    except DstackError as exc:
        view["authorized"] = False
        view["authorization_error"] = str(exc)
    else:
        view["authorized"] = True
    emit({"status": "ok", **view})
    return 0


def cmd_alignment_initialize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    slug = args.slug or slugify(args.title)
    branch = f"audit/{slug}"
    validate_git_branch(client.root, branch, name="alignment branch")
    validate_git_branch(client.root, args.target_branch, name="target branch")
    validate_git_revision(client.root, args.target_branch, name="target branch")
    try:
        existing = alignment_context(client, slug)
    except DstackError as exc:
        if "resolved to 0 roots" not in str(exc):
            raise
    else:
        if existing["root"].get("status") != "closed":
            target_branch = str(existing.get("target_branch") or args.target_branch)
            _, worktree, _, _ = ensure_branch_worktree(client, branch, target_branch)
            emit({"status": "ok", "created": False, "worktree": str(worktree), **existing})
            return 0
        raise DstackError(f"project alignment is already closed: {existing['root']['id']}")

    require_installed_formula(client.root, "dstack-project-alignment")
    pour = client.pour(
        "dstack-project-alignment",
        {
            "audit_title": args.title,
            "audit_slug": slug,
            "scope": args.scope,
        },
    )
    root_id = str(pour.get("root_id") or pour.get("new_epic_id") or "")
    if not root_id:
        raise DstackError("bd mol pour returned no alignment root")
    created_branch = False
    created_worktree = False
    try:
        client.update(
            root_id,
            "--title",
            f"Project alignment: {args.title}",
            "--add-label",
            "workflow:project-alignment",
            "--add-label",
            f"audit:{slug}",
            "--set-metadata",
            f"dstack.target_branch={args.target_branch}",
            "--set-metadata",
            f"dstack.scope={args.scope}",
        )
        _, worktree, created_branch, created_worktree = ensure_branch_worktree(client, branch, args.target_branch)
    except Exception:
        if created_worktree:
            run(
                [
                    "bd",
                    "worktree",
                    "remove",
                    str(conventional_worktree(client.root, branch)),
                    "--force",
                ],
                cwd=client.root,
                check=False,
            )
        if created_branch and branch_exists(client.root, branch):
            run(
                ["git", "branch", "-D", "--", branch],
                cwd=client.root,
                check=False,
            )
        run(
            ["bd", "delete", root_id, "--cascade", "--force"],
            cwd=client.root,
            check=False,
        )
        raise
    emit({"status": "ok", "worktree": str(worktree), **alignment_context(client, root_id)})
    return 0


def cmd_alignment_add_correction(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    acceptance = required_task_text(args.acceptance_file, args.acceptance)
    reject_documentation_work(args.title, stage="alignment correction")
    approval = client.show(str(view["steps"]["approval"]["id"]))
    corrections = client.show(str(view["steps"]["corrections"]["id"]))
    if approval.get("status") == "closed" or corrections.get("status") == "closed":
        raise DstackError("approved or closed alignment scope requires explicit reauthorization")
    item = client.create(
        args.title,
        parent=str(corrections["id"]),
        labels=["dstack:work:correction"],
        dependencies=[str(approval["id"]), *args.depends_on],
        description=task_text(args.description_file, args.description),
        acceptance=acceptance,
        priority=args.priority,
    )
    emit({"status": "ok", "correction": item})
    return 0


def _reauthorization_diagnostics(
    client: BeadsClient,
    view: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    raw = analysis.get("description")
    if not isinstance(raw, str) or not raw.strip():
        plan_state = {"status": "absent"}
    else:
        try:
            _, _, digest = canonical_description(analysis)
        except DstackError as exc:
            plan_state = {"status": "invalid", "reason": str(exc)}
        else:
            plan_state = {"status": "valid", "digest": digest}
    pending, approved = root_plan_metadata(client, str(view["root"]["id"]))
    return {
        "plan": plan_state,
        "pending_digest": pending,
        "approved_digest": approved,
    }


def _reset_alignment_plan_after_reauthorization(
    client: BeadsClient,
    view: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> None:
    raw = analysis.get("description")
    if not isinstance(raw, str) or not raw.strip() or raw.lstrip().startswith("Analyze "):
        return
    scope = str(view.get("scope") or "project alignment")
    placeholder = f"Analyze {scope}"
    client.update(str(analysis["id"]), "--description", placeholder)
    observed = client.show(str(analysis["id"]))
    if observed.get("description") != placeholder:
        raise DstackError("alignment plan reset did not converge")


def cmd_alignment_reauthorize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    root_id = str(view["root"]["id"])
    steps = view["steps"]
    analysis = client.show(str(steps["analysis"]["id"]))
    diagnostics = _reauthorization_diagnostics(client, view, analysis)
    approval = client.show(str(steps["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    if not isinstance(gate, dict):
        raise DstackError("alignment approval task lacks one blocking human gate")
    reopen_authorization_boundary(
        client,
        root_id=root_id,
        planning_id=str(steps["analysis"]["id"]),
        approval_id=str(approval["id"]),
        gate_id=str(gate["id"]),
        workstream_id=str(steps["corrections"]["id"]),
        terminal_id=str(steps["landing"]["id"]),
        reason=args.reason,
        digest_key="dstack.approved_alignment_plan_sha256",
        pending_digest_key="dstack.pending_alignment_plan_sha256",
    )

    analysis = client.show(str(steps["analysis"]["id"]))
    _reset_alignment_plan_after_reauthorization(client, view, analysis)
    approval = client.show(str(steps["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    corrections = client.show(str(steps["corrections"]["id"]))
    states = {
        "analysis": analysis.get("status"),
        "human_gate": gate.get("status") if isinstance(gate, Mapping) else None,
        "approval": approval.get("status"),
        "corrections": corrections.get("status"),
    }
    ready = client.ready_children(str(corrections["id"]), label="dstack:work:correction")
    if any(status != "open" for status in states.values()) or ready:
        raise DstackError(f"alignment reauthorization did not restore blocking state: states={states}")
    emit(
        {
            "status": "ok",
            "audit": root_id,
            "states": states,
            "invalidation": diagnostics,
        }
    )
    return 0


def _is_unfinished_formula_analysis(description: Any) -> bool:
    return isinstance(description, str) and description.lstrip().startswith("Analyze ")


def cmd_alignment_finish_plan(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    if not getattr(args, "plan_file", None):
        raise DstackError("alignment plan requires --plan-file")
    plan, encoded_bytes, digest = parse_plan_file(args.plan_file)
    encoded = encoded_bytes.decode("utf-8")
    analysis = client.show(str(view["steps"]["analysis"]["id"]))
    pending, approved = root_plan_metadata(client, str(view["root"]["id"]))
    raw_description = analysis.get("description")
    if analysis.get("status") == "closed":
        existing, existing_text, existing_digest = canonical_description(analysis)
        if existing_digest != digest or existing != plan or existing_text != encoded:
            raise DstackError("closed alignment analysis has a different canonical plan")
        if approved not in (None, digest) or pending not in (None, digest):
            raise DstackError("closed alignment analysis has inconsistent plan identity")
        if pending is None and approved is None:
            raise DstackError("closed alignment analysis has no pending or approved plan identity")
        verify_correction_graph(client, view, plan)
        emit(
            {
                "status": "ok",
                "audit": view["root"]["id"],
                "analysis": analysis,
                "already_closed": True,
            }
        )
        return 0
    if approved is not None:
        raise DstackError("open alignment analysis has an approved plan identity; reauthorize before retry")
    if pending is not None and pending != digest:
        raise DstackError("open alignment analysis has a different pending plan identity")
    if (
        isinstance(raw_description, str)
        and raw_description.strip()
        and not _is_unfinished_formula_analysis(raw_description)
    ):
        try:
            existing, existing_text, existing_digest = canonical_description(analysis)
        except DstackError as exc:
            raise DstackError("open alignment analysis has a non-canonical plan; reauthorize before retry") from exc
        if existing_digest != digest or existing != plan or existing_text != encoded:
            raise DstackError("open alignment analysis has a different canonical plan")
    elif pending is not None:
        raise DstackError("open alignment analysis has pending identity without a canonical plan")
    verify_correction_graph(client, view, plan)
    if (
        _is_unfinished_formula_analysis(raw_description)
        or not isinstance(raw_description, str)
        or not raw_description.strip()
    ):
        analysis = client.update(str(analysis["id"]), "--description", encoded)
    observed = client.show(str(analysis["id"]))
    if observed.get("description") != encoded:
        raise DstackError("canonical alignment plan description did not converge")
    if pending != digest:
        client.update(
            str(view["root"]["id"]),
            "--set-metadata",
            f"dstack.pending_alignment_plan_sha256={digest}",
        )
    pending, _ = root_plan_metadata(client, str(view["root"]["id"]))
    if pending != digest:
        raise DstackError(f"pending alignment plan identity did not converge: {pending!r}")
    analysis = claim_ready_step(
        client,
        root_id=str(view["root"]["id"]),
        step=analysis,
        label="dstack:step:alignment-analysis",
        name="alignment analysis",
    )
    analysis = client.close(str(analysis["id"]), "Corrective plan prepared")
    emit({"status": "ok", "audit": view["root"]["id"], "analysis": analysis, "plan_sha256": digest})
    return 0


def cmd_alignment_approve(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    root_id = str(view["root"]["id"])
    analysis = client.show(str(view["steps"]["analysis"]["id"]))
    plan, _, digest = canonical_description(analysis)
    require_current_plan(plan)
    if analysis.get("status") != "closed":
        raise DstackError("alignment approval requires closed analysis")
    pending, approved = root_plan_metadata(client, root_id)
    approval = client.show(str(view["steps"]["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    if not isinstance(gate, dict):
        raise DstackError("alignment workflow has no unique human gate")
    native_closed = gate.get("status") == "closed" and approval.get("status") == "closed"
    if approved not in (None, digest):
        raise DstackError("alignment approval has a different approved plan identity")
    if pending not in (None, digest):
        raise DstackError("alignment approval has a different pending plan identity")
    if approved == digest and pending is None and not native_closed:
        raise DstackError("alignment approval has approved identity before native authorization converged")
    if approved is None and pending is None:
        raise DstackError("alignment approval requires matching pending plan identity")
    if approved == digest and pending == digest and not native_closed:
        raise DstackError("alignment approval has inconsistent pending and approved identity")
    verify_correction_graph(client, view, plan)

    if not native_closed:
        gate = resolve_gate_if_needed(client, gate, "Corrective plan approved")
        approval = close_issue_if_needed(client, client.show(str(approval["id"])), "Corrective execution authorized")
        gate = client.show(str(gate["id"]))
        approval = client.show(str(approval["id"]))
    states = {
        "analysis": analysis.get("status"),
        "human_gate": gate.get("status"),
        "approval": approval.get("status"),
    }
    if any(status != "closed" for status in states.values()):
        raise DstackError(f"alignment approval did not converge: states={states}")
    if approved != digest:
        client.update(
            root_id,
            "--set-metadata",
            f"dstack.approved_alignment_plan_sha256={digest}",
        )
        if root_plan_metadata(client, root_id)[1] != digest:
            raise DstackError("approved alignment plan identity did not converge")
    if pending is not None:
        client.update(root_id, "--unset-metadata", "dstack.pending_alignment_plan_sha256")
        if root_plan_metadata(client, root_id)[0] is not None:
            raise DstackError("pending alignment plan identity did not clear")
    authorized_view = alignment_context(client, root_id)
    authorized_view["human_gate"] = client.show(str(gate["id"]))
    require_alignment_authorized(client, authorized_view)
    emit(
        {
            "status": "ok",
            "audit": root_id,
            "human_gate": gate,
            "approval": approval,
            "plan_sha256": digest,
        }
    )
    return 0


def require_alignment_approval(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    # Older protocol-only test doubles omit new alignment metadata; real views
    # always include it through alignment_context and therefore take the strict
    # authorization predicate.
    if "approved_alignment_plan_sha256" not in view and "pending_alignment_plan_sha256" not in view:
        if view["steps"]["approval"].get("status") != "closed":
            raise DstackError("alignment approval milestone is not closed")
        return {}
    return require_alignment_authorized(client, view)


def alignment_branch_context(client: BeadsClient, view: Mapping[str, Any]) -> tuple[str, Path, str]:
    branch = f"audit/{view['slug']}"
    target = str(view.get("target_branch") or "")
    validate_git_branch(client.root, branch, name="alignment branch")
    validate_git_branch(client.root, target, name="target branch")
    validate_git_revision(client.root, target, name="target branch")
    validate_git_revision(client.root, branch, name="alignment branch")
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree for {branch}")
    worktree = verify_worktree_identity(client.root, worktree, branch)
    if not ancestry(client.root, target, branch):
        raise DstackError(f"alignment branch {branch} does not contain target {target}")
    return branch, worktree, target


def cmd_alignment_claim_next(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    require_alignment_approval(client, view)
    alignment_branch_context(client, view)
    claimed = claim_ready_work(
        client,
        parent_id=str(view["steps"]["corrections"]["id"]),
        label="dstack:work:correction",
        requested_id=args.task,
    )
    emit({"status": "ok", "correction": claimed, "audit": view["root"]["id"]})
    return 0


def cmd_alignment_finish_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    require_alignment_approval(client, view)
    branch, worktree, base = alignment_branch_context(client, view)
    ensure_clean_worktree(worktree)
    parent = str(view["steps"]["corrections"]["id"])
    task = claim_ready_work(
        client,
        parent_id=parent,
        label="dstack:work:correction",
        requested_id=args.task,
    )
    if task is None:
        raise DstackError(f"correction {args.task} is not currently ready")
    if task.get("status") == "closed":
        emit(
            {
                "status": "ok",
                "audit": view["root"]["id"],
                "correction": task,
                "already_closed": True,
            }
        )
        return 0
    reason = completion_reason(args, "Correction completed")
    evidence = evidence_for_bead(worktree, args.task, f"{base}..{branch}")
    if args.no_repository_change:
        if evidence:
            raise DstackError("--no-repository-change conflicts with reachable commit evidence")
    elif not evidence:
        raise DstackError(f"no commit on {branch} references Bead {args.task}")
    require_no_documentation_changes(evidence, stage="alignment correction")
    require_alignment_approval(client, alignment_context(client, args.selector))
    if args.summary_file:
        client.add_comment(args.task, read_text_file(args.summary_file))
    task = client.close(args.task, reason)
    workstream = finish_alignment_workstream(client, view, close=False)
    emit(
        {
            "status": "ok",
            "audit": view["root"]["id"],
            "correction": task,
            "evidence": evidence,
            "workstream": workstream,
        }
    )
    return 0


def finish_alignment_workstream(client: BeadsClient, view: Mapping[str, Any], *, close: bool = True) -> dict[str, Any]:
    workstream = client.show(str(view["steps"]["corrections"]["id"]))
    open_items = open_workstream_children(client, str(workstream["id"]))
    if close and not open_items and workstream.get("status") != "closed":
        require_alignment_approval(client, view)
        _, worktree, _ = alignment_branch_context(client, view)
        ensure_clean_worktree(worktree)
        client.close(str(workstream["id"]), "All corrections completed")
    return {
        "open_items": [item["id"] for item in open_items],
        "workstream": client.show(str(workstream["id"])),
    }


def cmd_alignment_finish_workstream(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    payload = {"status": "ok", **finish_alignment_workstream(client, view)}
    if not getattr(args, "quiet", False):
        emit(payload)
    return 0


def cmd_alignment_claim_landing(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    require_alignment_approval(client, view)
    alignment_branch_context(client, view)
    landing = client.show(str(view["steps"]["landing"]["id"]))
    if landing.get("status") == "closed":
        emit({"status": "ok", "landing": landing, "already_closed": True})
        return 0
    claimed = claim_ready_step_with_fan_in(
        client,
        root_id=str(view["root"]["id"]),
        step=landing,
        label="dstack:step:alignment-landing",
        name="alignment landing",
        fan_in_parent_id=str(view["steps"]["corrections"]["id"]),
        fan_in_name="alignment corrections",
    )
    emit({"status": "ok", "landing": claimed, "audit": view["root"]["id"]})
    return 0


def cmd_alignment_finish_landing(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    require_alignment_approval(client, view)
    landing_id = str(view["steps"]["landing"]["id"])
    landing = client.show(landing_id)
    summary = ""
    if landing.get("status") != "closed":
        if not args.summary_file:
            raise DstackError("alignment reconciliation requires --summary-file")
        summary = read_text_file(args.summary_file)
        validate_record(
            summary,
            "alignment-reconciliation",
            source=args.summary_file,
            source_root=client.root,
        )
    branch, worktree, _ = alignment_branch_context(client, view)
    ensure_clean_worktree(worktree)
    documentation = validate_docs(worktree)
    from dstack_delivery import (
        alignment_delivery_context,
        alignment_evidence_audit,
        docs_check,
    )

    delivery_view = alignment_delivery_context(client, str(view["root"]["id"]))
    evidence = alignment_evidence_audit(client, delivery_view)
    if evidence["status"] != "ok":
        raise DstackError(
            "alignment evidence audit failed: "
            f"missing={evidence['missing']}, "
            f"unexpected={evidence['unexpected_footer_ids']}"
        )
    policy = docs_check(worktree, str(view["target_branch"]), branch)
    if policy["violations"]:
        raise DstackError(
            "alignment documentation policy failed: " + "; ".join(item["line"] for item in policy["violations"])
        )
    if landing.get("status") != "closed":
        require_alignment_approval(client, alignment_context(client, args.selector))
        landing = claim_ready_step_with_fan_in(
            client,
            root_id=str(view["root"]["id"]),
            step=landing,
            label="dstack:step:alignment-landing",
            name="alignment landing",
            fan_in_parent_id=str(view["steps"]["corrections"]["id"]),
            fan_in_name="alignment corrections",
        )
        client.add_comment(landing_id, summary)
        landing = client.close(landing_id, args.reason)
    keep_root_open_for_delivery(client, str(view["root"]["id"]))
    emit(
        {
            "status": "ok",
            "audit": view["root"]["id"],
            "landing": landing,
            "documentation": documentation,
            "evidence": evidence,
            "documentation_policy": policy,
        }
    )
    return 0
