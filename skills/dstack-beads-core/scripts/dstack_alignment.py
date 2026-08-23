#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from dstacklib import (
    BeadsClient,
    DstackError,
    alignment_context,
    alignment_view,
    ancestry,
    branch_exists,
    commit_footer_ids,
    conventional_worktree,
    current_head,
    dependency_records,
    display_title,
    ensure_clean_tracked,
    ensure_clean_worktree,
    feature_slug,
    file_sha256,
    git_root,
    has_label,
    human_gate_for_step,
    issue_labels,
    issue_metadata,
    issue_parent,
    read_text_file,
    ref_exists,
    resolve_feature,
    root_metadata_value,
    run,
    slugify,
    worktree_for_branch,
)

from dstack_commands import (
    BEADS_RUNTIME_DIR_PREFIXES,
    BEADS_RUNTIME_TOP_LEVEL_PATTERNS,
    BEADS_SENSITIVE_BASENAMES,
    DESIGN_SCAFFOLD,
    DSTACK_UNTRACKED_BEADS_FILES,
    DURABLE_STATUS_PATTERN,
    FORBIDDEN_DOC_PATTERNS,
    NO_REPOSITORY_CHANGE_PREFIX,
    claim_issue_if_needed,
    claim_ready_step_with_fan_in,
    close_issue_if_needed,
    resolve_gate_if_needed,
    client_for,
    completion_reason,
    descendants,
    emit,
    ensure_feature_worktree,
    evidence_for_bead,
    fail,
    feature_branch_context,
    package_root,
    preserve_external_blockers,
    require_approved_design,
    require_installed_formula,
    required_task_text,
    superseded_target,
    task_text,
    update_root_identity,
)
from dstack_docs import validate_docs

def cmd_alignment_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    emit({"status": "ok", **alignment_view(client, args.selector)})
    return 0


def cmd_alignment_initialize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    slug = args.slug or slugify(args.title)
    try:
        existing = alignment_context(client, slug)
    except DstackError as exc:
        if "resolved to 0 roots" not in str(exc):
            raise
    else:
        if existing["root"].get("status") != "closed":
            branch = f"audit/{slug}"
            worktree = worktree_for_branch(client.root, branch)
            if worktree is None:
                target_branch = str(existing.get("target_branch") or args.target_branch)
                if not branch_exists(client.root, branch):
                    run(["git", "branch", branch, target_branch], cwd=client.root)
                path = conventional_worktree(client.root, branch)
                run(["bd", "worktree", "create", str(path), "--branch", branch], cwd=client.root)
                worktree = worktree_for_branch(client.root, branch)
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
    branch = f"audit/{slug}"
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
        if not branch_exists(client.root, branch):
            run(["git", "branch", branch, args.target_branch], cwd=client.root)
            created_branch = True
        worktree = worktree_for_branch(client.root, branch)
        if worktree is None:
            path = conventional_worktree(client.root, branch)
            run(["bd", "worktree", "create", str(path), "--branch", branch], cwd=client.root)
            created_worktree = True
            worktree = worktree_for_branch(client.root, branch)
        if worktree is None:
            raise DstackError(f"failed to register worktree for {branch}")
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
            run(["git", "branch", "-D", branch], cwd=client.root, check=False)
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
    item = client.create(
        args.title,
        parent=str(view["steps"]["corrections"]["id"]),
        labels=["dstack:work:correction"],
        dependencies=[str(view["steps"]["approval"]["id"]), *args.depends_on],
        description=task_text(args.description_file, args.description),
        acceptance=required_task_text(args.acceptance_file, args.acceptance),
        priority=args.priority,
    )
    emit({"status": "ok", "correction": item})
    return 0


def cmd_alignment_finish_plan(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    analysis = claim_issue_if_needed(client, view["steps"]["analysis"])
    if args.summary_file:
        client.add_comment(str(analysis["id"]), read_text_file(args.summary_file))
    analysis = client.close(str(analysis["id"]), "Corrective plan prepared")
    emit(
        {
            "status": "ok",
            "audit": view["root"]["id"],
            "analysis": analysis,
        }
    )
    return 0


def cmd_alignment_approve(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    root_id = str(view["root"]["id"])
    approval = client.show(str(view["steps"]["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    if not isinstance(gate, dict):
        raise DstackError("alignment workflow has no unique human gate")

    gate = resolve_gate_if_needed(client, gate, "Corrective plan approved")
    approval = close_issue_if_needed(
        client, client.show(str(approval["id"])), "Corrective execution authorized"
    )
    gate = client.show(str(gate["id"]))
    approval = client.show(str(approval["id"]))
    states = {
        "human_gate": gate.get("status"),
        "approval": approval.get("status"),
    }
    if any(status != "closed" for status in states.values()):
        raise DstackError(f"alignment approval did not converge: states={states}")
    emit(
        {
            "status": "ok",
            "audit": root_id,
            "human_gate": gate,
            "approval": approval,
        }
    )
    return 0


def cmd_alignment_claim_next(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    parent = str(view["steps"]["corrections"]["id"])
    if args.task:
        task = client.show(args.task)
        if issue_parent(task) != parent:
            raise DstackError(f"task {args.task} is not a correction under {parent}")
        if task.get("status") == "open":
            ready_ids = {
                str(candidate["id"])
                for candidate in client.ready_children(
                    parent,
                    label="dstack:work:correction",
                )
            }
            if args.task not in ready_ids:
                raise DstackError(f"correction {args.task} is not currently ready")
        claimed = claim_issue_if_needed(client, task)
    else:
        items = client.ready_children(parent, label="dstack:work:correction", claim=True)
        claimed = items[0] if items else None
    emit({"status": "ok", "correction": claimed, "audit": view["root"]["id"]})
    return 0


def cmd_alignment_finish_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = alignment_context(client, args.selector)
    parent = str(view["steps"]["corrections"]["id"])
    task = client.show(args.task)
    if issue_parent(task) != parent:
        raise DstackError(f"task {args.task} is not a correction under {parent}")
    task = claim_issue_if_needed(client, task)
    slug = str(view["slug"])
    branch = f"audit/{slug}"
    base = str(view["target_branch"])
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree for {branch}")
    reason = completion_reason(args, "Correction completed")
    evidence = evidence_for_bead(worktree, args.task, f"{base}..{branch}")
    if args.no_repository_change:
        ensure_clean_tracked(worktree)
        if evidence:
            raise DstackError("--no-repository-change conflicts with reachable commit evidence")
    elif not evidence:
        raise DstackError(f"no commit on {branch} references Bead {args.task}")
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
    landing_id = str(view["steps"]["landing"]["id"])
    landing = client.show(landing_id)
    branch = f"audit/{view['slug']}"
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree for {branch}")
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
        landing = claim_ready_step_with_fan_in(
            client,
            root_id=str(view["root"]["id"]),
            step=landing,
            label="dstack:step:alignment-landing",
            name="alignment landing",
            fan_in_parent_id=str(view["steps"]["corrections"]["id"]),
            fan_in_name="alignment corrections",
        )
        if args.summary_file:
            client.add_comment(landing_id, read_text_file(args.summary_file))
        landing = client.close(landing_id, args.reason)
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
