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

from .core import (
    BeadsClient,
    DstackError,
    branch_exists,
    canonical_feature_design_path,
    conventional_worktree,
    display_title,
    dependency_records,
    ensure_clean_worktree,
    feature_authorization_state,
    feature_context,
    feature_design_state,
    feature_slug,
    feature_view,
    file_sha256,
    git_file_sha256,
    has_label,
    human_gate_for_step,
    is_current_feature,
    issue_type,
    issue_metadata,
    read_text_file,
    resolve_feature,
    root_metadata_value,
    safe_repository_path,
    run,
    slugify,
    validate_git_branch,
    validate_git_revision,
)

from .docs import create_foundation, validate_docs, validate_record
from .formula import (
    CREATED_FORMULA_VERSION_KEY,
    FEATURE_FORMULA,
    FormulaAuditRequired,
    formula_contract_version,
    metadata_formula_version,
    stamp_created_formula_version,
    stamp_formula_version,
    pour_current_formula,
)
from .commands import (
    DESIGN_SCAFFOLD,
    RECONCILIATION_SCAFFOLD,
    claim_ready_step,
    claim_ready_step_with_fan_in,
    claim_ready_work,
    close_issue_if_needed,
    resolve_gate_if_needed,
    client_for,
    completion_reason,
    emit,
    ensure_feature_worktree,
    evidence_for_bead,
    feature_branch_context,
    keep_root_open_for_delivery,
    open_workstream_children,
    preserve_external_blockers,
    require_approved_design,
    reject_documentation_work,
    require_no_documentation_changes,
    reopen_authorization_boundary,
    required_task_text,
    superseded_target,
    task_text,
    update_root_identity,
)


def _feature_contract_issues(
    client: BeadsClient,
    view: Mapping[str, Any],
    *,
    root: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    root_issue = root or client.show(str(view["root"]["id"]))
    issues: list[Mapping[str, Any]] = [root_issue]
    if not view.get("current"):
        return issues
    steps = view["steps"]
    issues.extend(steps.values())
    implementation_id = str(steps["implementation"]["id"])
    issues.extend(item for item in client.children(implementation_id) if item.get("status") != "closed")
    unique: dict[str, Mapping[str, Any]] = {}
    for issue in issues:
        issue_id = str(issue.get("id") or "")
        if issue_id:
            unique[issue_id] = issue
    return list(unique.values())


def feature_formula_contract_state(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    root = client.show(str(view["root"]["id"]))
    current = formula_contract_version(FEATURE_FORMULA)
    audited = metadata_formula_version(root)
    created = metadata_formula_version(root, CREATED_FORMULA_VERSION_KEY)
    approved = bool(root_metadata_value(root, "dstack.approved_design_sha256"))
    stale_issue_ids: list[str] = []
    if approved:
        stale_issue_ids = [
            str(issue["id"])
            for issue in _feature_contract_issues(client, view, root=root)
            if metadata_formula_version(issue) != current
        ]
    if not approved:
        state = "pending-review"
        audit_required = False
    elif not stale_issue_ids:
        state = "current"
        audit_required = False
    else:
        state = "audit-required"
        audit_required = True
    return {
        "formula": FEATURE_FORMULA,
        "current_version": current,
        "created_version": created,
        "audited_version": audited,
        "state": state,
        "audit_required": audit_required,
        "stale_issue_ids": stale_issue_ids,
    }


def _feature_contract_issue_ids(client: BeadsClient, view: Mapping[str, Any]) -> list[str]:
    return [str(issue["id"]) for issue in _feature_contract_issues(client, view)]


def stamp_feature_formula_contract(client: BeadsClient, view: Mapping[str, Any]) -> int:
    return stamp_formula_version(
        client,
        _feature_contract_issue_ids(client, view),
        formula_name=FEATURE_FORMULA,
    )


def require_feature_formula_current(client: BeadsClient, view: Mapping[str, Any]) -> None:
    state = feature_formula_contract_state(client, view)
    if not state["audit_required"]:
        return
    previous = state["audited_version"]
    previous_text = f"v{previous}" if previous is not None else "an unversioned contract"
    current = state["current_version"]
    feature_id = str(view["root"]["id"])
    stale = state["stale_issue_ids"]
    if previous == current:
        reason = f"active workflow records are missing the current v{current} audit stamp"
    else:
        reason = f"the feature was last reviewed against {previous_text}; the current contract is v{current}"
    raise FormulaAuditRequired(
        {
            "status": "audit_required",
            "feature": feature_id,
            "formula": FEATURE_FORMULA,
            "from_version": previous,
            "to_version": current,
            "skill": "dstack-beads-review-feature-spec",
            "stale_issue_ids": stale,
            "audit_complete": f"dstack ctl feature audit-complete {feature_id}",
            "message": f"feature {feature_id} requires a formula compatibility audit: {reason}",
            "user_input": (
                "Internal formula compatibility audit. "
                f"Feature {feature_id} requires review because {reason}. "
                f"The installed {FEATURE_FORMULA} contract is v{current}. "
                "Review the existing approved design and execution tasks semantically against the current "
                "review skill and formula expectations. Do not regenerate or normalize the historical graph. "
                "If no material changes are needed, run `dstack ctl feature audit-complete "
                f"{feature_id}` and retry the controller command that requested this audit. "
                "If changes are needed, present only the minimal design/task/dependency delta and ask the user "
                "for approval before reauthorization or any task mutation."
            ),
            "resume": "retry the controller command that returned audit_required",
        }
    )


def approved_feature_context(client: BeadsClient, selector: str | None) -> dict[str, Any]:
    context = feature_context(client, selector)
    context.update(feature_design_state(client, context))
    context.update(feature_authorization_state(client, context))
    require_approved_design(context)
    require_feature_formula_current(client, context)
    return context


def cmd_feature_plan(args: argparse.Namespace) -> int:
    """Create or update one planned feature through the controller."""

    client = client_for(args.root)
    title = str(args.title).strip()
    description = required_task_text(args.body_file, None)
    acceptance = required_task_text(None, args.acceptance)
    selector = (args.selector or "").strip()
    existing: dict[str, Any] | None = None
    if selector:
        try:
            existing = resolve_feature(client, selector)
        except DstackError as exc:
            if "no feature matches selector" not in str(exc):
                raise
    if existing is not None:
        if existing.get("status") == "closed":
            raise DstackError(f"planned feature is already closed: {existing['id']}")
        if is_current_feature(client, existing):
            raise DstackError("current feature scope must be changed through review and reauthorization")
        if issue_type(existing) not in {"epic", "molecule"} or not has_label(existing, "dstack:feature-idea"):
            raise DstackError("selected issue is not an open planned feature")
        issue_id = str(existing["id"])
        stable_slug = feature_slug(existing)
        if not stable_slug:
            raise DstackError("planned feature has no stable feature slug")
        if args.slug and args.slug != stable_slug:
            raise DstackError(f"planned feature slug is immutable: {stable_slug}")
        client.update(
            issue_id,
            "--title",
            title,
            "--description",
            description,
            "--acceptance",
            acceptance,
            "--priority",
            str(args.priority),
            "--add-label",
            "dstack:feature-idea",
            "--add-label",
            f"feature:{stable_slug}",
        )
        current = client.show(issue_id)
        existing_blockers = {
            str(record.get("depends_on_id") or record.get("id"))
            for record in dependency_records(current)
            if str(record.get("type") or record.get("dependency_type") or "blocks") == "blocks"
            and (record.get("depends_on_id") or record.get("id"))
        }
        wanted = set(args.depends_on)
        for blocker in sorted(wanted - existing_blockers):
            client.add_dependency(issue_id, blocker)
        for blocker in sorted(existing_blockers - wanted):
            client.remove_dependency(issue_id, blocker)
        created = False
    else:
        stable_slug = args.slug or slugify(title)
        item = client.create(
            title,
            issue_type_name="epic",
            labels=["dstack:feature-idea", f"feature:{stable_slug}"],
            dependencies=args.depends_on,
            description=description,
            acceptance=acceptance,
            priority=args.priority,
        )
        issue_id = str(item["id"])
        created = True

    observed = client.show(issue_id)
    observed_blockers = sorted(
        str(record.get("depends_on_id") or record.get("id"))
        for record in dependency_records(observed)
        if str(record.get("type") or record.get("dependency_type") or "blocks") == "blocks"
        and (record.get("depends_on_id") or record.get("id"))
    )
    if (
        str(observed.get("title") or "") != title
        or str(observed.get("description") or "") != description
        or str(observed.get("acceptance_criteria") or observed.get("acceptance") or "") != acceptance
        or observed.get("priority") != args.priority
        or not has_label(observed, "dstack:feature-idea")
        or feature_slug(observed) != stable_slug
        or observed_blockers != sorted(set(args.depends_on))
    ):
        raise DstackError("planned feature did not converge to the requested intent")
    emit({"status": "ok", "created": created, "planned_feature": observed, "slug": stable_slug})
    return 0


def cmd_feature_resolve(args: argparse.Namespace) -> int:
    client = client_for(args.root, initialize=False)
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
    client = client_for(args.root, initialize=False)
    view = feature_view(client, args.selector)
    view["formula_contract"] = feature_formula_contract_state(client, view)
    emit({"status": "ok", **view})
    return 0


def cmd_feature_audit_complete(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = feature_context(client, args.selector)
    if not view.get("current"):
        raise DstackError("formula compatibility audit requires a current dStack feature molecule")
    authorization = feature_authorization_state(client, view)
    view.update(feature_design_state(client, view))
    view.update(authorization)
    require_approved_design(view)
    version = stamp_feature_formula_contract(client, view)
    observed = feature_formula_contract_state(client, view)
    if observed["audited_version"] != version or observed["audit_required"]:
        raise DstackError("feature formula compatibility audit stamp did not converge")
    emit({"status": "ok", "feature": view["root"]["id"], "formula_contract": observed})
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
    validate_git_branch(client.root, args.base_branch, name="base branch")
    validate_git_revision(client.root, args.base_branch, name="base branch")

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
    validate_git_branch(client.root, base_branch, name="base branch")
    validate_git_revision(client.root, base_branch, name="base branch")
    validate_git_branch(client.root, f"feat/{slug}", name="feature branch")
    design_path = default_design_path(client.root, slug)
    if args.design_path and args.design_path != design_path:
        raise DstackError(f"feature design path must be {design_path} for the mdBook layout")
    pour = pour_current_formula(
        client,
        FEATURE_FORMULA,
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
        stamp_created_formula_version(client, root_id, formula_name=FEATURE_FORMULA)
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
                ["git", "branch", "-D", "--", f"feat/{slug}"],
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
    path = safe_repository_path(worktree, relative, purpose="feature design path")
    return path, relative.as_posix()


def ensure_feature_navigation(
    worktree: Path,
    *,
    slug: str,
    title: str,
    reconciled: bool = False,
) -> None:
    safe_title = title.replace("[", "").replace("]", "") or slug
    feature_source = safe_repository_path(worktree, "docs/src/features", purpose="feature documentation directory")
    feature_source.mkdir(parents=True, exist_ok=True)

    index = safe_repository_path(worktree, "docs/src/features/index.md", purpose="feature index")
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

    summary = safe_repository_path(worktree, "docs/src/SUMMARY.md", purpose="mdBook summary")
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
    create_foundation(worktree)
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
    reject_documentation_work(args.title, stage="implementation")
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
    stamp_formula_version(client, [str(item["id"])], formula_name=FEATURE_FORMULA)
    item = client.show(str(item["id"]))
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
        pending_digest_key="dstack.pending_design_sha256",
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
        or root_metadata_value(root, "dstack.pending_design_sha256")
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
    claimed = claim_ready_step(
        client,
        root_id=str(view["root"]["id"]),
        step=specification,
        label="dstack:step:specification",
        name="specification",
    )
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
    approved = root_metadata_value(root, "dstack.approved_design_sha256")
    pending = root_metadata_value(root, "dstack.pending_design_sha256")
    initial_states = {
        "specification": specification.get("status"),
        "human_gate": gate.get("status"),
        "approval": approval.get("status"),
    }
    if (approved and approved != digest) or (pending and pending != digest):
        raise DstackError(
            "accepted design changed after approval began; explicitly reopen the "
            "specification and approval boundary before reauthorizing"
        )
    if approved and any(status != "closed" for status in initial_states.values()):
        raise DstackError("approved design metadata conflicts with incomplete native approval state")
    if not approved and not pending:
        if any(status == "closed" for status in initial_states.values()):
            raise DstackError(
                "closed native approval state lacks pending or approved content identity; explicitly reauthorize"
            )
        client.update(
            root_id,
            "--set-metadata",
            f"dstack.pending_design_sha256={digest}",
        )
        pending = root_metadata_value(client.show(root_id), "dstack.pending_design_sha256")
        if pending != digest:
            raise DstackError(f"pending design identity did not converge: {pending!r}")

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
        raise DstackError(f"specification approval did not converge: states={states}")

    if approved != digest:
        client.update(
            root_id,
            "--set-metadata",
            f"dstack.approved_design_sha256={digest}",
        )
        approved = root_metadata_value(client.show(root_id), "dstack.approved_design_sha256")
        if approved != digest:
            raise DstackError(f"approved design identity did not converge: {approved!r}")
    if root_metadata_value(client.show(root_id), "dstack.pending_design_sha256"):
        client.update(
            root_id,
            "--unset-metadata",
            "dstack.pending_design_sha256",
        )

    observed_root = client.show(root_id)
    specification = client.show(str(specification["id"]))
    gate = client.show(str(gate["id"]))
    approval = client.show(str(approval["id"]))
    approved = root_metadata_value(observed_root, "dstack.approved_design_sha256")
    pending = root_metadata_value(observed_root, "dstack.pending_design_sha256")
    states = {
        "specification": specification.get("status"),
        "human_gate": gate.get("status"),
        "approval": approval.get("status"),
    }
    if approved != digest or pending or any(status != "closed" for status in states.values()):
        raise DstackError(
            f"specification approval did not converge: approved={approved!r}, pending={pending!r}, states={states}"
        )
    refreshed_view = feature_context(client, root_id)
    formula_version = stamp_feature_formula_contract(client, refreshed_view)
    emit(
        {
            "status": "ok",
            "feature": root_id,
            "approved_design_sha256": digest,
            "formula_version": formula_version,
            "specification": specification,
            "human_gate": gate,
            "approval": approval,
        }
    )
    return 0


def cmd_feature_claim_next(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    view = approved_feature_context(client, args.selector)
    feature_branch_context(client, view)
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
    branch, worktree, base = feature_branch_context(client, view)
    ensure_clean_worktree(worktree)
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

    reason = completion_reason(args, "Implementation completed")
    evidence = evidence_for_bead(worktree, args.task, f"{base}..{branch}")
    if args.no_repository_change:
        if evidence:
            raise DstackError("--no-repository-change conflicts with reachable commit evidence")
    elif not evidence:
        raise DstackError(f"no reachable commit on {branch} has footer 'Beads: {args.task}'")
    require_no_documentation_changes(evidence, stage="implementation")
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
    feature_branch_context(client, view)
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


def validate_feature_documentation(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, object]:
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
            "feature reconciliation is still the untouched scaffold; record the delivered result before closeout"
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
