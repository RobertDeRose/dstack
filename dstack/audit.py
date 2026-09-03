"""Bounded, read-only evidence collection for semantic feature audits."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping, Sequence

from .commands import client_for, implementation_tasks, run_project_validation
from .core import (
    DstackError,
    ancestry,
    audit_fan_in_errors,
    branch_exists,
    changed_paths,
    commit_records,
    diff_stat,
    feature_identity,
    feature_steps,
    implementation_task_graph_errors,
    issue_type,
    run,
    truncate_output,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)
from .docs import validate_docs
from .output import emit
from .policy import no_repository_change_reason, validate_plan_issue, validate_task_issue

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
)


def issue_view(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Return full issue content only for explicitly requested audit details."""

    return {field: issue[field] for field in DETAIL_FIELDS if field in issue and issue[field] not in (None, "", [], {})}


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


def bounded(items: Sequence[Any], *, limit: int = MAX_AUDIT_ITEMS) -> dict[str, Any]:
    values = list(items)
    return {
        "count": len(values),
        "truncated": len(values) > limit,
        "items": values[:limit],
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
                }
            )
    return result


def _documentation(root: Path, paths: list[str]) -> dict[str, Any]:
    documentation_paths = sorted(path for path in paths if path.startswith("docs/") or path.casefold().endswith(".md"))
    try:
        result = validate_docs(root)
    except DstackError as exc:
        return {
            "status": "failed",
            "changed_paths": bounded(documentation_paths),
            "error": str(exc),
        }
    chapters = result.get("chapters", [])
    includes = result.get("includes", [])
    return {
        "status": "ok",
        "changed_paths": bounded(documentation_paths),
        "chapter_count": len(chapters) if isinstance(chapters, list) else None,
        "include_count": len(includes) if isinstance(includes, list) else None,
    }


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
        details["tasks"] = {task_id: issue_view(task_map[task_id]) for task_id in include_task_ids}

    decision_map = {str(decision["id"]): decision for decision in decisions}
    unknown_decisions = sorted(set(include_decision_ids) - set(decision_map))
    if unknown_decisions:
        raise DstackError("requested audit decision is not linked to the feature: " + ", ".join(unknown_decisions))
    if include_decision_ids:
        details["decisions"] = {
            decision_id: issue_view(decision_map[decision_id]) for decision_id in include_decision_ids
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
) -> dict[str, Any]:
    client = client_for(root_path)
    root, slug, base = feature_identity(client, selector)
    steps = feature_steps(client, str(root["id"]))
    implementation = implementation_tasks(client, str(steps["implementation"]["id"]))
    decisions = client.list(all_statuses=True, labels=[f"feature:{slug}"], issue_type_filter="decision")
    gates = [
        issue
        for issue in client.list(all_statuses=True, parent=str(root["id"]), include_gates=True)
        if issue_type(issue) == "gate"
    ]

    errors: list[str] = []
    plan_validation = validate_plan_issue(client.show(str(steps["plan"]["id"])))
    if plan_validation["status"] != "ok":
        errors.append("feature plan violates dStack policy")

    task_rows: list[dict[str, Any]] = []
    for task in implementation:
        validation = validate_task_issue(task)
        graph_errors = implementation_task_graph_errors(client, task, root, steps)
        task_errors = [*validation["errors"], *graph_errors]
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
            if not ancestry(client.root, base, branch):
                errors.append(f"feature branch {branch} does not contain base branch {base}")
            range_value = f"{base}..{branch}"
            records = commit_records(client.root, range_value)
            paths = changed_paths(client.root, base, branch)
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
                    "commits": bounded(compact_commits),
                    "changed_path_count": len(paths),
                    "diff_stat": diff_stat(client.root, base, branch),
                }
            )
            if include_commit_paths:
                git["changed_paths"] = bounded(paths)
        except DstackError as exc:
            errors.append(str(exc))

    task_ids = {str(task["id"]) for task in implementation}
    mapping = _footer_mapping(records)
    for row, task in zip(task_rows, implementation, strict=True):
        task_id = str(task["id"])
        commits = mapping.get(task_id, [])
        row["commit_count"] = len(commits)
        row["commits"] = bounded([{"commit": item["commit"], "subject": item["subject"]} for item in commits])
        if not commits and no_repository_change_reason(task) is None:
            errors.append(f"implementation task {task_id} has no reachable commit evidence")

    invalid_footer_commits = sorted(
        str(record["commit"])
        for record in records
        if len(tuple(record.get("footer_ids", ()))) != 1
        or any(str(bead_id) not in task_ids for bead_id in record.get("footer_ids", ()))
    )
    git["invalid_footer_commits"] = bounded(invalid_footer_commits)
    if invalid_footer_commits:
        errors.append("feature commits contain missing, multiple, or non-task Beads footers")

    try:
        worktree_path = worktree_for_branch(client, branch)
    except DstackError as exc:
        worktree_path = None
        errors.append(str(exc))

    if worktree_path is None:
        git["worktree"] = {"status": "missing", "path": None}
        validation = {"status": "blocked", "command": ["hk", "check", "-a"]}
        documentation = {"status": "blocked", "changed_paths": bounded([])}
        errors.append(f"feature worktree is not registered for {branch}")
    else:
        worktree = verify_worktree_identity(client.root, worktree_path, branch)
        status = run(["git", "status", "--short", "--untracked-files=all"], cwd=worktree, check=False)
        worktree_status = "clean" if status.returncode == 0 and not status.stdout.strip() else "dirty"
        git["worktree"] = {
            "status": worktree_status,
            "path": str(worktree),
            "details": truncate_output(status.stderr or status.stdout),
        }
        if worktree_status != "clean":
            errors.append("feature worktree contains uncommitted changes")

        validation = run_project_validation(worktree)
        if validation["status"] != "ok":
            errors.append("project validation failed")
        documentation = _documentation(worktree, paths)
        if documentation["status"] != "ok":
            errors.append("documentation validation failed")

        post_status = run(["git", "status", "--short", "--untracked-files=all"], cwd=worktree, check=False)
        post_clean = post_status.returncode == 0 and not post_status.stdout.strip()
        git["worktree"]["post_validation_status"] = "clean" if post_clean else "dirty"
        if not post_clean:
            errors.append("validation left uncommitted changes in the feature worktree")

    plan = client.show(str(steps["plan"]["id"]))
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
        "implementation_tasks": bounded(task_rows),
        "decisions": bounded([issue_summary(issue) for issue in decisions]),
        "gates": bounded([issue_summary(issue) for issue in gates]),
        "git": git,
        "validation": validation,
        "documentation": documentation,
    }
    if details:
        payload["details"] = details
    return payload


def cmd_audit_evidence(args: argparse.Namespace) -> int:
    payload = collect_audit_evidence(
        args.root,
        args.feature,
        include_plan=args.include_plan,
        include_task_ids=args.include_task,
        include_decision_ids=args.include_decision,
        history_ids=args.history_for,
        include_commit_paths=args.include_commit_paths,
    )
    emit(payload)
    return 0 if payload["checks"]["status"] == "ok" else 4
