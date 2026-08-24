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
    ancestry,
    branch_exists,
    canonical_feature_design_path,
    commit_footer_ids,
    conventional_worktree,
    current_head,
    dependency_records,
    display_title,
    ensure_clean_worktree,
    feature_authorization_state,
    feature_context,
    feature_design_state,
    feature_slug,
    feature_view,
    file_sha256,
    git_file_sha256,
    git_root,
    has_label,
    human_gate_for_step,
    is_current_feature,
    issue_labels,
    issue_metadata,
    read_text_file,
    ref_exists,
    resolve_feature,
    root_metadata_value,
    run,
    slugify,
    worktree_for_branch,
)

from dstack_docs import validate_docs, validate_record
from dstack_commands import (
    BEADS_RUNTIME_DIR_PREFIXES,
    BEADS_RUNTIME_TOP_LEVEL_PATTERNS,
    BEADS_SENSITIVE_BASENAMES,
    DESIGN_SCAFFOLD,
    RECONCILIATION_SCAFFOLD,
    DSTACK_UNTRACKED_BEADS_FILES,
    FORBIDDEN_DOC_PATTERNS,
    NO_REPOSITORY_CHANGE_PREFIX,
    claim_issue_if_needed,
    claim_ready_step_with_fan_in,
    claim_ready_work,
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
    keep_root_open_for_delivery,
    open_workstream_children,
    package_root,
    preserve_external_blockers,
    require_approved_design,
    require_installed_formula,
    reopen_authorization_boundary,
    required_task_text,
    superseded_target,
    task_text,
    update_root_identity,
)


def approved_feature_context(
    client: BeadsClient, selector: str | None
) -> dict[str, Any]:
    context = feature_context(client, selector)
    context.update(feature_design_state(client, context))
    context.update(feature_authorization_state(client, context))
    require_approved_design(context)
    return context


def cmd_feature_resolve(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root = resolve_feature(client, args.selector)
    emit(
        {
            "status": "ok",
            "root": root,
            "slug": feature_slug(root),
            "current": is_current_feature(client, root),
        }
    )
    return 0


def cmd_feature_inspect(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    emit({"status": "ok", **feature_view(client, args.selector)})
    return 0


def is_planned_legacy_feature(issue: Mapping[str, Any]) -> bool:
    metadata = issue_metadata(issue)
    classification = str(metadata.get("migration_classification") or "").casefold()
    roadmap = str(metadata.get("legacy_roadmap_status") or "").casefold()
    return classification == "planned" or "planned" in roadmap or has_label(issue, "dstack:feature-idea")


def default_design_path(_root: Path, slug: str) -> str:
    return canonical_feature_design_path(slug)


def cmd_feature_initialize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    selector = (args.selector or args.title or "").strip()
    if not selector:
        raise DstackError("feature selector/title is required")

    existing: dict[str, Any] | None = None
    try:
        existing = resolve_feature(client, selector)
    except DstackError as exc:
        if "no feature matches selector" not in str(exc):
            raise

    planned_source: dict[str, Any] | None = None
    if existing is not None:
        view = feature_context(client, str(existing["id"]))
        if existing.get("status") == "closed":
            replacement = superseded_target(existing)
            if replacement:
                replacement_view = feature_context(client, replacement)
                if replacement_view["current"] and not replacement_view["closed"]:
                    branch, worktree, _, _ = ensure_feature_worktree(
                        client,
                        str(replacement_view["slug"]),
                        str(replacement_view.get("base_branch") or args.base_branch),
                    )
                    emit(
                        {
                            "status": "ok",
                            "created": False,
                            "planned_source": existing["id"],
                            "branch": branch,
                            "worktree": str(worktree),
                            **replacement_view,
                        }
                    )
                    return 0
            raise DstackError(f"feature is already closed: {existing['id']}")
        if view["current"]:
            branch, worktree, _, _ = ensure_feature_worktree(
                client,
                str(view["slug"]),
                str(view.get("base_branch") or args.base_branch),
            )
            emit(
                {
                    "status": "ok",
                    "created": False,
                    "branch": branch,
                    "worktree": str(worktree),
                    **view,
                }
            )
            return 0
        if not is_planned_legacy_feature(existing):
            raise DstackError(
                f"feature {existing['id']} uses the active legacy workflow; run /adopt-feature {existing['id']}"
            )
        planned_source = existing

    title = (
        args.title or (display_title(str(planned_source.get("title", ""))) if planned_source else selector)
    ).strip()
    slug = args.slug or (feature_slug(planned_source) if planned_source else None) or slugify(title)
    inherited_base = root_metadata_value(planned_source, "base_branch") if planned_source else None
    base_branch = inherited_base or args.base_branch
    design_path = default_design_path(client.root, slug)
    if args.design_path and args.design_path != design_path:
        raise DstackError(f"feature design path must be {design_path} for the mdBook layout")
    require_installed_formula(client.root, "dstack-feature")
    pour = client.pour(
        "dstack-feature",
        {
            "feature_title": title,
            "feature_slug": slug,
            "design_path": design_path,
        },
    )
    root_id = str(pour.get("root_id") or pour.get("new_epic_id") or "")
    if not root_id:
        raise DstackError("bd mol pour returned no feature root")

    source_description = str(planned_source.get("description") or "") if planned_source else ""
    source_acceptance = (
        str(planned_source.get("acceptance_criteria") or planned_source.get("acceptance") or "")
        if planned_source
        else ""
    )
    source_priority = (
        int(planned_source["priority"]) if planned_source and planned_source.get("priority") is not None else None
    )
    created_branch = False
    created_worktree = False
    preserved_blockers: list[str] = []
    try:
        update_root_identity(
            client,
            root_id,
            title=title,
            slug=slug,
            base_branch=base_branch,
            design_path=design_path,
            description=source_description or None,
            acceptance=source_acceptance or None,
            priority=source_priority,
        )
        branch, worktree, created_branch, created_worktree = ensure_feature_worktree(client, slug, base_branch)
        if planned_source is not None:
            preserved_blockers = preserve_external_blockers(client, planned_source, root_id)
            client.supersede(str(planned_source["id"]), root_id)
    except Exception:
        if created_worktree:
            run(
                [
                    "bd",
                    "worktree",
                    "remove",
                    str(conventional_worktree(client.root, f"feat/{slug}")),
                    "--force",
                ],
                cwd=client.root,
                check=False,
            )
        if created_branch and branch_exists(client.root, f"feat/{slug}"):
            run(
                ["git", "branch", "-D", f"feat/{slug}"],
                cwd=client.root,
                check=False,
            )
        run(
            ["bd", "delete", root_id, "--cascade", "--force"],
            cwd=client.root,
            check=False,
        )
        raise

    emit(
        {
            "status": "ok",
            "created": True,
            "planned_source": planned_source["id"] if planned_source else None,
            "preserved_blockers": preserved_blockers,
            "branch": branch,
            "worktree": str(worktree),
            **feature_context(client, root_id),
        }
    )
    return 0


def safe_design_file(worktree: Path, design_path: str) -> tuple[Path, str]:
    relative = Path(design_path)
    if not design_path.strip() or relative.is_absolute() or ".." in relative.parts:
        raise DstackError("design path must be repository-relative without parent traversal")

    repository = worktree.resolve()
    resolved = (repository / relative).resolve()
    try:
        resolved.relative_to(repository)
    except ValueError as exc:
        raise DstackError("design path escapes the feature repository") from exc
    if resolved == repository:
        raise DstackError("design path must name a file")
    return resolved, relative.as_posix()


def ensure_feature_navigation(
    worktree: Path,
    *,
    slug: str,
    title: str,
    reconciled: bool = False,
) -> None:
    safe_title = title.replace("[", "").replace("]", "") or slug
    feature_source = worktree / "docs/src/features"
    feature_source.mkdir(parents=True, exist_ok=True)

    index = feature_source / "index.md"
    index_target = f"{slug}/{'index' if reconciled else 'design'}.md"
    index_lines = index.read_text().rstrip().splitlines() if index.is_file() else ["# Feature Records"]
    if index_lines and index_lines[0] == "# Feature designs":
        index_lines[0] = "# Feature Records"
    existing_index: str | None = None
    index_position: int | None = None
    filtered_index: list[str] = []
    for line in index_lines:
        if f"]({slug}/design.md)" in line or f"]({slug}/index.md)" in line:
            if existing_index is None:
                existing_index = line.replace(f"]({slug}/design.md)", f"]({index_target})").replace(
                    f"]({slug}/index.md)", f"]({index_target})"
                )
                index_position = len(filtered_index)
            continue
        filtered_index.append(line)
    if existing_index is not None and index_position is not None:
        filtered_index.insert(index_position, existing_index)
    else:
        while filtered_index and not filtered_index[-1]:
            filtered_index.pop()
        if filtered_index:
            filtered_index.append("")
        filtered_index.append(f"- [{safe_title}]({index_target})")
    index.write_text("\n".join(filtered_index) + "\n")

    summary = worktree / "docs/src/SUMMARY.md"
    summary_lines = summary.read_text().rstrip().splitlines() if summary.is_file() else ["# Summary"]
    old_anchor = "- [Feature designs](features/index.md)"
    anchor = "- [Feature Records](features/index.md)"
    summary_lines = [anchor if line == old_anchor else line for line in summary_lines]
    design_target = f"features/{slug}/design.md"
    reconciliation_target = f"features/{slug}/index.md"
    existing_design: str | None = None
    existing_reconciliation: str | None = None
    summary_position: int | None = None
    filtered_summary: list[str] = []
    for line in summary_lines:
        if f"]({design_target})" in line or f"]({reconciliation_target})" in line:
            if summary_position is None:
                summary_position = len(filtered_summary)
            if f"]({reconciliation_target})" in line and existing_reconciliation is None:
                existing_reconciliation = line
            elif f"]({design_target})" in line and existing_design is None:
                existing_design = line
            continue
        filtered_summary.append(line)
    if anchor not in filtered_summary:
        filtered_summary.extend(["", anchor])
    if reconciled:
        parent = existing_reconciliation or (
            existing_design.replace(f"]({design_target})", f"]({reconciliation_target})")
            if existing_design
            else f"  - [{safe_title}]({reconciliation_target})"
        )
        design = existing_design if existing_reconciliation and existing_design else f"    - [Design]({design_target})"
        block = [parent, design]
    else:
        parent = existing_design or (
            existing_reconciliation.replace(f"]({reconciliation_target})", f"]({design_target})")
            if existing_reconciliation
            else f"  - [{safe_title}]({design_target})"
        )
        block = [parent]
    if summary_position is None:
        summary_position = filtered_summary.index(anchor) + 1
        while summary_position < len(filtered_summary) and filtered_summary[summary_position].startswith("  "):
            summary_position += 1
    filtered_summary[summary_position:summary_position] = block
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("\n".join(filtered_summary) + "\n")


def cmd_feature_scaffold_design(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    if not view["current"]:
        raise DstackError("feature is not a current dstack molecule")
    design_path = str(view.get("design_path") or "")
    if not design_path:
        raise DstackError("feature root has no dstack.design_path metadata")

    _, worktree, _ = feature_branch_context(client, view)
    design_file, relative = safe_design_file(worktree, design_path)
    created = False
    if design_file.exists():
        if not design_file.is_file():
            raise DstackError("design path exists but is not a file")
    else:
        design_file.parent.mkdir(parents=True, exist_ok=True)
        planned_intent = str(view["root"].get("description") or "").strip()
        planned_acceptance = str(view["root"].get("acceptance_criteria") or "").strip()
        try:
            with design_file.open("x", encoding="utf-8") as handle:
                handle.write(
                    DESIGN_SCAFFOLD.format(
                        planned_intent=planned_intent or "_No durable planning description was provided._",
                        planned_acceptance=planned_acceptance
                        or "_No durable planning acceptance criteria were provided._",
                    )
                )
            created = True
        except FileExistsError:
            if not design_file.is_file():
                raise DstackError("design path exists but is not a file")

    ensure_feature_navigation(
        worktree,
        slug=str(view["slug"]),
        title=display_title(str(view["root"].get("title") or view["slug"])),
        reconciled=design_file.with_name("index.md").is_file(),
    )
    emit({"status": "ok", "created": created, "design_path": relative})
    return 0


def cmd_feature_scaffold_reconciliation(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    if not view["current"]:
        raise DstackError("feature is not a current dstack molecule")
    design_path = str(view.get("design_path") or "")
    _, worktree, _ = feature_branch_context(client, view)
    design_file, relative = safe_design_file(worktree, design_path)
    if not design_file.is_file():
        raise DstackError("feature design does not exist")

    reconciliation = design_file.with_name("index.md")
    title = display_title(str(view["root"].get("title") or view["slug"]))
    created = False
    try:
        with reconciliation.open("x", encoding="utf-8") as handle:
            handle.write(RECONCILIATION_SCAFFOLD.format(title=title))
        created = True
    except FileExistsError:
        if not reconciliation.is_file():
            raise DstackError("feature reconciliation path exists but is not a file")

    ensure_feature_navigation(
        worktree,
        slug=str(view["slug"]),
        title=title,
        reconciled=True,
    )
    emit(
        {
            "status": "ok",
            "created": created,
            "reconciliation_path": str(Path(relative).with_name("index.md")),
        }
    )
    return 0


def cmd_feature_add_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    if not view["current"]:
        raise DstackError("feature is not a current dstack molecule")
    acceptance = required_task_text(args.acceptance_file, args.acceptance)
    implementation = view["steps"]["implementation"]
    approval = view["steps"]["approval"]
    root = client.show(str(view["root"]["id"]))
    approval = client.show(str(approval["id"]))
    implementation = client.show(str(implementation["id"]))
    if (
        root_metadata_value(root, "dstack.approved_design_sha256")
        or approval.get("status") == "closed"
        or implementation.get("status") == "closed"
    ):
        raise DstackError("approved or closed feature scope requires explicit reauthorization")
    dependencies = [str(approval["id"]), *args.depends_on]
    item = client.create(
        args.title,
        parent=str(implementation["id"]),
        labels=["dstack:work:implementation"],
        dependencies=dependencies,
        description=task_text(args.description_file, args.description),
        acceptance=acceptance,
        priority=args.priority,
    )
    emit({"status": "ok", "task": item})
    return 0


def cmd_feature_reauthorize(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    root_id = str(view["root"]["id"])
    steps = view["steps"]
    approval = client.show(str(steps["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    if not isinstance(gate, dict):
        raise DstackError("feature approval task lacks one blocking human gate")
    reopen_authorization_boundary(
        client,
        root_id=root_id,
        planning_id=str(steps["specification"]["id"]),
        approval_id=str(approval["id"]),
        gate_id=str(gate["id"]),
        workstream_id=str(steps["implementation"]["id"]),
        terminal_id=str(steps["closeout"]["id"]),
        reason=args.reason,
        digest_key="dstack.approved_design_sha256",
    )

    root = client.show(root_id)
    specification = client.show(str(steps["specification"]["id"]))
    approval = client.show(str(steps["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    implementation = client.show(str(steps["implementation"]["id"]))
    states = {
        "specification": specification.get("status"),
        "human_gate": gate.get("status") if isinstance(gate, Mapping) else None,
        "approval": approval.get("status"),
        "implementation": implementation.get("status"),
    }
    ready = client.ready_children(str(implementation["id"]), label="dstack:work:implementation")
    if (
        root_metadata_value(root, "dstack.approved_design_sha256")
        or any(status != "open" for status in states.values())
        or ready
    ):
        raise DstackError(f"feature reauthorization did not restore blocking state: states={states}")
    emit(
        {
            "status": "ok",
            "feature": root_id,
            "states": states,
            "approved_design_sha256": None,
        }
    )
    return 0


def cmd_feature_claim_spec(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    specification = view["steps"]["specification"]
    claimed = claim_issue_if_needed(client, specification)
    emit({"status": "ok", "feature": view["root"]["id"], "specification": claimed})
    return 0


def approved_design_digest(client: BeadsClient, view: Mapping[str, Any]) -> str:
    design_path = str(view.get("design_path") or "")
    if not design_path:
        raise DstackError("feature root has no dstack.design_path metadata")
    branch, worktree, _ = feature_branch_context(client, view)
    expected = conventional_worktree(client.root, branch).resolve()
    if worktree.resolve() != expected:
        raise DstackError(f"feature worktree must use the conventional path {expected}: {worktree}")
    ensure_clean_worktree(worktree)
    design_file, relative = safe_design_file(worktree, design_path)
    if (
        run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=worktree,
            check=False,
        ).returncode
        != 0
    ):
        raise DstackError(f"feature design is not tracked: {relative}")
    head_digest = git_file_sha256(worktree, relative)
    if head_digest is None:
        raise DstackError(f"feature design is not committed at HEAD: {relative}")
    if file_sha256(design_file) != head_digest:
        raise DstackError(f"feature design differs from HEAD: {relative}")
    validate_record(
        design_file.read_text(encoding="utf-8"),
        "feature-design",
        source=design_file,
        source_root=worktree,
    )
    return head_digest


def cmd_feature_approve_spec(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    digest = approved_design_digest(client, view)
    root_id = str(view["root"]["id"])

    specification = client.show(str(view["steps"]["specification"]["id"]))
    approval = client.show(str(view["steps"]["approval"]["id"]))
    gate = human_gate_for_step(client, root_id=root_id, step=approval)
    if not isinstance(gate, dict):
        raise DstackError("feature approval task lacks one blocking human gate")
    root = client.show(root_id)
    previous = root_metadata_value(root, "dstack.approved_design_sha256")
    if previous and previous != digest and any(
        item.get("status") == "closed" for item in (specification, gate, approval)
    ):
        raise DstackError(
            "accepted design changed after approval began; explicitly reopen the "
            "specification and approval boundary before reauthorizing"
        )

    if specification.get("status") != "closed" and args.summary_file:
        client.add_comment(str(specification["id"]), read_text_file(args.summary_file))
    specification = close_issue_if_needed(client, specification, "Specification approved")
    gate = resolve_gate_if_needed(client, gate, "Specification approved")
    approval = close_issue_if_needed(client, client.show(str(approval["id"])), "Implementation authorized")

    specification = client.show(str(specification["id"]))
    gate = client.show(str(gate["id"]))
    approval = client.show(str(approval["id"]))
    states = {
        "specification": specification.get("status"),
        "human_gate": gate.get("status"),
        "approval": approval.get("status"),
    }
    if any(status != "closed" for status in states.values()):
        raise DstackError(
            f"specification approval did not converge: states={states}"
        )

    if previous != digest:
        client.update(
            root_id,
            "--set-metadata",
            f"dstack.approved_design_sha256={digest}",
        )
    observed_root = client.show(root_id)
    specification = client.show(str(specification["id"]))
    gate = client.show(str(gate["id"]))
    approval = client.show(str(approval["id"]))
    final_digest = root_metadata_value(observed_root, "dstack.approved_design_sha256")
    states = {
        "specification": specification.get("status"),
        "human_gate": gate.get("status"),
        "approval": approval.get("status"),
    }
    if final_digest != digest or any(status != "closed" for status in states.values()):
        raise DstackError(
            "specification approval did not converge: "
            f"digest={final_digest!r}, states={states}"
        )
    emit(
        {
            "status": "ok",
            "feature": root_id,
            "approved_design_sha256": digest,
            "specification": specification,
            "human_gate": gate,
            "approval": approval,
        }
    )
    return 0


def cmd_feature_claim_next(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = approved_feature_context(client, args.selector)
    claimed = claim_ready_work(
        client,
        parent_id=str(view["steps"]["implementation"]["id"]),
        label="dstack:work:implementation",
        requested_id=args.task,
    )
    emit({"status": "ok", "task": claimed, "feature": view["root"]["id"]})
    return 0


def cmd_feature_finish_task(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = approved_feature_context(client, args.selector)
    implementation_id = str(view["steps"]["implementation"]["id"])
    task = claim_ready_work(
        client,
        parent_id=implementation_id,
        label="dstack:work:implementation",
        requested_id=args.task,
    )
    if task is None:
        raise DstackError(f"task {args.task} is not currently ready")
    if task.get("status") == "closed":
        emit({"status": "ok", "feature": view["root"]["id"], "task": task, "already_closed": True})
        return 0

    branch, worktree, base = feature_branch_context(client, view)
    ensure_clean_worktree(worktree)
    reason = completion_reason(args, "Implementation completed")
    evidence = evidence_for_bead(worktree, args.task, f"{base}..{branch}")
    if args.no_repository_change:
        if evidence:
            raise DstackError("--no-repository-change conflicts with reachable commit evidence")
    elif not evidence:
        raise DstackError(f"no reachable commit on {branch} has footer 'Beads: {args.task}'")
    summary = read_text_file(args.summary_file)
    if summary:
        client.add_comment(args.task, summary)
    task = client.close(args.task, reason)
    workstream = finish_feature_workstream(client, view, close=False)
    emit(
        {
            "status": "ok",
            "feature": view["root"]["id"],
            "task": task,
            "evidence": evidence,
            "workstream": workstream,
        }
    )
    return 0


def finish_feature_workstream(
    client: BeadsClient,
    view: Mapping[str, Any],
    *,
    close: bool = True,
) -> dict[str, Any]:
    implementation = client.show(str(view["steps"]["implementation"]["id"]))
    open_items = open_workstream_children(client, str(implementation["id"]))
    closed = False
    if close and not open_items and implementation.get("status") != "closed":
        require_approved_design(view)
        _, worktree, _ = feature_branch_context(client, view)
        ensure_clean_worktree(worktree)
        client.close(str(implementation["id"]), "All implementation work completed")
        closed = True
    return {
        "workstream": client.show(str(implementation["id"])),
        "open_items": [item["id"] for item in open_items],
        "closed_now": closed,
        "closeout": client.show(str(view["steps"]["closeout"]["id"])),
    }


def cmd_feature_finish_workstream(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = approved_feature_context(client, args.selector)
    payload = {"status": "ok", **finish_feature_workstream(client, view)}
    if not getattr(args, "quiet", False):
        emit(payload)
    return 0


def cmd_feature_claim_closeout(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = approved_feature_context(client, args.selector)
    closeout = client.show(str(view["steps"]["closeout"]["id"]))
    if closeout.get("status") == "closed":
        emit({"status": "ok", "closeout": closeout, "already_closed": True})
        return 0
    claimed = claim_ready_step_with_fan_in(
        client,
        root_id=str(view["root"]["id"]),
        step=closeout,
        label="dstack:step:closeout",
        name="feature closeout",
        fan_in_parent_id=str(view["steps"]["implementation"]["id"]),
        fan_in_name="feature implementation",
    )
    emit({"status": "ok", "closeout": claimed, "feature": view["root"]["id"]})
    return 0


def validate_feature_documentation(
    client: BeadsClient, view: Mapping[str, Any]
) -> dict[str, object]:
    _, worktree, _ = feature_branch_context(client, view)
    ensure_clean_worktree(worktree)
    design_file, _ = safe_design_file(worktree, str(view.get("design_path") or ""))
    reconciliation = design_file.with_name("index.md")
    if not reconciliation.is_file():
        raise DstackError("feature reconciliation does not exist")
    title = display_title(str(view["root"].get("title") or view["slug"]))
    content = reconciliation.read_text(encoding="utf-8")
    untouched = RECONCILIATION_SCAFFOLD.format(title=title)
    if not content.strip() or content.strip() == untouched.strip():
        raise DstackError(
            "feature reconciliation is still the untouched scaffold; "
            "record the delivered result before closeout"
        )
    validate_record(
        content,
        "feature-reconciliation",
        source=reconciliation,
        source_root=worktree,
    )
    return validate_docs(worktree)


def cmd_feature_finish_closeout(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = approved_feature_context(client, args.selector)
    closeout_id = str(view["steps"]["closeout"]["id"])
    closeout = client.show(closeout_id)
    documentation = validate_feature_documentation(client, view)
    if closeout.get("status") != "closed":
        closeout = claim_ready_step_with_fan_in(
            client,
            root_id=str(view["root"]["id"]),
            step=closeout,
            label="dstack:step:closeout",
            name="feature closeout",
            fan_in_parent_id=str(view["steps"]["implementation"]["id"]),
            fan_in_name="feature implementation",
        )
        if args.summary_file:
            client.add_comment(closeout_id, read_text_file(args.summary_file))
        closeout = client.close(closeout_id, args.reason)
    keep_root_open_for_delivery(client, str(view["root"]["id"]))
    emit(
        {
            "status": "ok",
            "feature": view["root"]["id"],
            "closeout": closeout,
            "documentation": documentation,
        }
    )
    return 0
