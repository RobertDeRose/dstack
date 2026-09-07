"""Bounded, read-only evidence collection for semantic feature audits."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping, Sequence

from .commands import client_for, implementation_tasks
from .core import (
    DstackError,
    audit_fan_in_errors,
    branch_exists,
    changed_paths,
    commit_records,
    dependency_targets,
    diff_stat,
    feature_identity,
    feature_steps,
    implementation_task_graph_errors,
    issue_labels,
    issue_type,
    reject_beads_paths,
    require_common_history,
    run,
    truncate_output,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)
from .docs import validate_docs
from .git_ops import canonical_docs_message, canonical_task_message, commit_record_matches_message
from .output import emit
from .policy import implementation_notes, no_repository_change_reason, validate_plan_issue, validate_task_issue

MAX_AUDIT_ITEMS = 100
DETAIL_FIELDS = (
    "id",
    "title",
    "status",
    "issue_type",
    "type",
    "priority",
    "assignee",
    "description",
    "design",
    "acceptance_criteria",
    "notes",
    "labels",
    "metadata",
    "dependencies",
    "parent",
    "parent_id",
    "close_reason",
    "comment_count",
    "comments_omitted",
    "comments",
)


def issue_view(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Return full issue content only for explicitly requested audit details."""

    result = {field: issue[field] for field in DETAIL_FIELDS if field in issue and issue[field] not in (None, "", [], {})}
    if "comments" in issue:
        result["comments"] = issue["comments"]
    return result


def issue_summary(issue: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": str(issue.get("id") or ""),
        "title": str(issue.get("title") or ""),
        "status": str(issue.get("status") or ""),
        "issue_type": issue_type(issue),
    }
    if issue.get("priority") is not None:
        result["priority"] = issue["priority"]
    return result


def bounded(items: Sequence[Any], *, limit: int = MAX_AUDIT_ITEMS, offset: int = 0) -> dict[str, Any]:
    values = list(items)
    return {
        "count": len(values),
        "truncated": offset > 0 or len(values) > offset + limit,
        "items": values[offset : offset + limit],
        **({"offset": offset} if offset else {}),
        **({"next_offset": offset + limit} if len(values) > offset + limit else {}),
    }


def _footer_mapping(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return compact Beads-to-commit evidence without duplicating changed paths."""

    result: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for bead_id in record.get("footer_ids", ()):
            result.setdefault(str(bead_id), []).append(
                {
                    "commit": str(record.get("commit") or ""),
                    "subject": str(record.get("subject") or ""),
                    "body": str(record.get("body") or ""),
                }
            )
    return result


def _selected_details(
    *,
    include_plan: bool,
    include_task_ids: Sequence[str],
    include_decision_ids: Sequence[str],
    history_ids: Sequence[str],
    plan: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    allowed_history: Mapping[str, Mapping[str, Any]],
    client: Any,
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if include_plan:
        details["plan"] = issue_view(plan)

    task_map = {str(task["id"]): task for task in tasks}
    unknown_tasks = sorted(set(include_task_ids) - set(task_map))
    if unknown_tasks:
        raise DstackError("requested audit task is not an implementation child: " + ", ".join(unknown_tasks))
    if include_task_ids:
        details["tasks"] = {
            task_id: issue_view(client.show(task_id, include_comments=True)) for task_id in dict.fromkeys(include_task_ids)
        }

    decision_map = {str(decision["id"]): decision for decision in decisions}
    unknown_decisions = sorted(set(include_decision_ids) - set(decision_map))
    if unknown_decisions:
        raise DstackError("requested audit decision is not linked to the feature: " + ", ".join(unknown_decisions))
    if include_decision_ids:
        details["decisions"] = {
            decision_id: issue_view(client.show(decision_id, include_comments=True))
            for decision_id in dict.fromkeys(include_decision_ids)
        }

    unknown_history = sorted(set(history_ids) - set(allowed_history))
    if unknown_history:
        raise DstackError("requested history issue is outside the feature graph: " + ", ".join(unknown_history))
    if history_ids:
        history: dict[str, Any] = {}
        for issue_id in history_ids:
            value = client.history(issue_id)
            history[issue_id] = bounded(value) if isinstance(value, list) else value
        details["history"] = history
    return details


def collect_audit_evidence(
    root_path: Path,
    selector: str,
    *,
    include_plan: bool = False,
    include_task_ids: Sequence[str] = (),
    include_decision_ids: Sequence[str] = (),
    history_ids: Sequence[str] = (),
    include_commit_paths: bool = False,
    require_docs: bool = False,
    offset: int = 0,
) -> dict[str, Any]:
    if offset < 0:
        raise DstackError("audit offset must be non-negative")
    client = client_for(root_path)
    root, slug, base = feature_identity(client, selector)
    steps = feature_steps(client, str(root["id"]))
    errors: list[str] = []
    for name, values in (
        ("task details", include_task_ids),
        ("decision details", include_decision_ids),
        ("history details", history_ids),
    ):
        if len(values) > MAX_AUDIT_ITEMS:
            raise DstackError(f"requested audit {name} exceed the {MAX_AUDIT_ITEMS}-item bound")
    implementation = implementation_tasks(
        client,
        str(steps["implementation"]["id"]),
    )
    decisions = sorted(
        (
            issue
            for issue in client.list(
                all_statuses=True,
                labels=[f"decision:{slug}"],
                issue_type_filter="decision",
            )
            if f"decision:{slug}" in issue_labels(issue) and str(root["id"]) in dependency_targets(issue, "relates-to")
        ),
        key=lambda issue: str(issue.get("id") or ""),
    )
    audit_step = steps["audit"]
    gate_ids = sorted(set(dependency_targets(audit_step, "blocks")))
    gates = sorted(
        (issue for issue in client.show_many(gate_ids) if issue_type(issue) == "gate"),
        key=lambda issue: str(issue.get("id") or ""),
    )

    plan = client.show(str(steps["plan"]["id"]))
    plan_validation = validate_plan_issue(plan)
    if plan_validation["status"] != "ok":
        errors.append("feature plan violates dStack policy")

    task_rows: list[dict[str, Any]] = []
    no_change_by_task: dict[str, str | None] = {}
    for task in implementation:
        validation = validate_task_issue(task)
        graph_errors = implementation_task_graph_errors(client, task, root, steps)
        task_errors = [*validation["errors"], *graph_errors]
        try:
            execution_notes = implementation_notes(task)
        except DstackError:
            execution_notes = []
            no_change = None
        else:
            no_change = no_repository_change_reason(task)
        no_change_by_task[str(task["id"])] = no_change
        if not no_change and execution_notes == [] and not any("implementation note" in error for error in task_errors):
            task_errors.append("implementation task requires at least one Implementation note before committing")
        task_rows.append(
            {
                **issue_summary(task),
                "validation": {
                    "status": "ok" if not task_errors else "invalid",
                    "errors": task_errors,
                },
            }
        )
        if task_errors:
            errors.append(f"implementation task {task['id']} violates dStack policy or graph invariants")
        if str(task.get("status") or "") != "closed":
            errors.append(f"implementation task {task['id']} is not closed")

    fan_in_errors = audit_fan_in_errors(client, steps, implementation)
    errors.extend(fan_in_errors)

    branch = f"feat/{slug}"
    git: dict[str, Any] = {
        "base_branch": base,
        "feature_branch": branch,
        "branch_present": branch_exists(client.root, branch),
    }
    records: list[dict[str, Any]] = []
    paths: list[str] = []

    if not git["branch_present"]:
        errors.append(f"feature branch is missing: {branch}")
    else:
        try:
            validate_git_revision(client.root, base, name="audit base branch")
            validate_git_revision(client.root, branch, name="audit feature branch")
            require_common_history(client.root, base, branch)
            range_value = f"{base}..{branch}"
            records = commit_records(
                client.root,
                range_value,
                include_paths=include_commit_paths,
            )
            paths = changed_paths(client.root, base, branch)
            try:
                reject_beads_paths(paths)
            except DstackError as exc:
                errors.append(str(exc))
            compact_commits: list[dict[str, Any]] = []
            for record in records:
                row = {
                    "commit": str(record["commit"]),
                    "subject": str(record["subject"]),
                    "footer_ids": list(record.get("footer_ids", ())),
                }
                if include_commit_paths:
                    row["paths"] = bounded(list(record.get("paths", [])))
                compact_commits.append(row)
            git.update(
                {
                    "range": range_value,
                    "commit_count": len(records),
                    "commits": bounded(compact_commits, offset=offset),
                    "changed_path_count": len(paths),
                    "diff_stat": truncate_output(diff_stat(client.root, base, branch)),
                }
            )
            if include_commit_paths:
                git["changed_paths"] = bounded(paths)
        except DstackError as exc:
            errors.append(str(exc))

    task_ids = {str(task["id"]) for task in implementation}
    close_id = str(audit_step["id"])
    accepted_ids = {*task_ids, close_id}
    mapping = _footer_mapping(records)
    for row, task in zip(task_rows, implementation, strict=True):
        task_id = str(task["id"])
        commits = mapping.get(task_id, [])
        row["commit_count"] = len(commits)
        row["commits"] = bounded([{"commit": item["commit"], "subject": item["subject"]} for item in commits])
        expected_count = 0 if no_change_by_task.get(task_id) is not None else 1
        if len(commits) != expected_count:
            errors.append(
                f"implementation task {task_id} must own {expected_count} canonical commit(s); observed {len(commits)}"
            )
        elif commits:
            try:
                expected_message = canonical_task_message(task, slug)
            except DstackError:
                errors.append(f"implementation task {task_id} commit message is not canonical")
            else:
                if not commit_record_matches_message(commits[0], expected_message):
                    errors.append(f"implementation task {task_id} commit message is not canonical")

    close_commits = mapping.get(close_id, [])
    git["close_commit"] = close_commits[0] if len(close_commits) == 1 else None
    if len(close_commits) > 1:
        errors.append(f"close step {close_id} may own at most one documentation commit")
    elif close_commits and not commit_record_matches_message(
        close_commits[0], canonical_docs_message(root, slug, close_id)
    ):
        errors.append("close documentation commit message is not canonical")

    invalid_footer_commits = sorted(
        str(record["commit"])
        for record in records
        if record.get("legacy_footer_ids")
        or len(tuple(record.get("footer_ids", ()))) != 1
        or any(str(owner_id) not in accepted_ids for owner_id in record.get("footer_ids", ()))
    )
    git["invalid_footer_commits"] = bounded(invalid_footer_commits)
    if invalid_footer_commits:
        errors.append("feature commits contain missing, multiple, or unaccepted ownership footers")

    try:
        worktree_path = worktree_for_branch(client, branch)
    except DstackError as exc:
        worktree_path = None
        errors.append(str(exc))

    project_validation = {
        "status": "external",
        "owner": "target repository",
        "note": "run the repository's documented validation contract before close",
    }
    feature_docs: dict[str, Any] = {"status": "not_checked"}
    if worktree_path is None:
        git["worktree"] = {"status": "missing", "path": None}
        feature_docs = {"status": "blocked"}
        errors.append(f"feature worktree is not registered for {branch}")
    else:
        worktree = verify_worktree_identity(client.root, worktree_path, branch)
        status = run(["git", "status", "--short", "--untracked-files=all"], cwd=worktree, check=False)
        worktree_status = "clean" if status.returncode == 0 and not status.stdout.strip() else "dirty"
        git["worktree"] = {
            "status": worktree_status,
            "path": str(worktree),
            "details": truncate_output(status.stderr) or truncate_output(status.stdout),
        }
        if worktree_status != "clean":
            errors.append("feature worktree contains uncommitted changes")
        try:
            feature_docs = {"status": "ok", **validate_docs(worktree, feature=slug, expected_design=str(plan.get("design") or ""))}
        except DstackError as exc:
            feature_docs = {"status": "invalid", "errors": [str(exc)]}
            if require_docs:
                errors.append("feature documentation validation failed")

    allowed_history = {str(item["id"]): item for item in [root, *steps.values(), *implementation, *decisions, *gates]}
    details = _selected_details(
        include_plan=include_plan,
        include_task_ids=include_task_ids,
        include_decision_ids=include_decision_ids,
        history_ids=history_ids,
        plan=plan,
        tasks=implementation,
        decisions=decisions,
        allowed_history=allowed_history,
        client=client,
    )

    payload: dict[str, Any] = {
        "status": "collected",
        "checks": {
            "status": "ok" if not errors else "invalid",
            "error_count": len(errors),
            "errors_truncated": len(errors) > MAX_AUDIT_ITEMS,
            "errors": errors[:MAX_AUDIT_ITEMS],
        },
        "feature": issue_summary(root),
        "steps": {name: issue_summary(issue) for name, issue in steps.items()},
        "plan_validation": {
            "status": plan_validation["status"],
            "errors": plan_validation["errors"],
        },
        "implementation_tasks": bounded(task_rows, offset=offset),
        "decisions": bounded([issue_summary(issue) for issue in decisions], offset=offset),
        "gates": bounded([issue_summary(issue) for issue in gates], offset=offset),
        "git": git,
        "validation": {
            "project": project_validation,
            "feature_docs": feature_docs,
        },
    }
    if details:
        payload["details"] = details
    return payload


def cmd_audit_evidence(args: argparse.Namespace) -> int:
    payload = collect_audit_evidence(
        args.root,
        args.bead,
        include_plan=args.include_plan,
        include_task_ids=args.include_task,
        include_decision_ids=args.include_decision,
        history_ids=args.history_for,
        include_commit_paths=args.include_commit_paths,
        require_docs=args.require_docs,
        offset=getattr(args, "offset", 0),
    )
    emit(payload)
    return 0 if payload["checks"]["status"] == "ok" else 4
