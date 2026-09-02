"""Read-only evidence collection for semantic feature audits."""

from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path
from typing import Any, Mapping

from .commands import client_for
from .core import (
    DstackError,
    branch_exists,
    changed_paths,
    commit_records,
    diff_stat,
    feature_identity,
    feature_steps,
    footer_mapping,
    has_label,
    issue_type,
    run,
    truncate_output,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)
from .docs import validate_docs
from .output import emit
from .policy import validate_plan_issue, validate_task_issue

ISSUE_FIELDS = (
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
    return {field: issue[field] for field in ISSUE_FIELDS if field in issue and issue[field] not in (None, "", [], {})}


def _validation(root: Path, command_text: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "not-run"}
    command = shlex.split(command_text)
    if not command:
        raise DstackError("validation command must not be empty")
    result = run(command, cwd=root, check=False)
    return {
        "status": "ok" if result.returncode == 0 else "failed",
        "command": command,
        "returncode": result.returncode,
        "stdout": truncate_output(result.stdout),
        "stderr": truncate_output(result.stderr),
    }


def _documentation(root: Path, paths: list[str], *, enabled: bool) -> dict[str, Any]:
    documentation_paths = [path for path in paths if path.startswith("docs/") or path.casefold().endswith(".md")]
    if not enabled:
        return {"status": "not-run", "changed_paths": documentation_paths}
    try:
        result = validate_docs(root)
    except DstackError as exc:
        return {"status": "failed", "changed_paths": documentation_paths, "error": str(exc)}
    return {"status": "ok", "changed_paths": documentation_paths, "result": result}


def collect_audit_evidence(
    root_path: Path,
    selector: str,
    *,
    include_history: bool = False,
    run_validation: bool = False,
    validation_command: str | None = None,
) -> dict[str, Any]:
    client = client_for(root_path)
    root, slug, base = feature_identity(client, selector)
    steps = feature_steps(client, str(root["id"]))
    implementation_id = str(steps["implementation"]["id"])
    implementation = [
        issue
        for issue in client.children(implementation_id)
        if has_label(issue, "dstack:work:implementation") or issue_type(issue) not in {"epic", "molecule", "gate"}
    ]
    decisions = client.list(all_statuses=True, labels=[f"feature:{slug}"], issue_type_filter="decision")
    gates = [
        issue
        for issue in client.list(all_statuses=True, parent=str(root["id"]), include_gates=True)
        if issue_type(issue) == "gate"
    ]

    branch = f"feat/{slug}"
    git: dict[str, Any] = {
        "base_branch": base,
        "feature_branch": branch,
        "branch_present": branch_exists(client.root, branch),
    }
    records: list[dict[str, Any]] = []
    paths: list[str] = []
    execution_root = client.root
    if git["branch_present"]:
        validate_git_revision(client.root, base, name="audit base branch")
        validate_git_revision(client.root, branch, name="audit feature branch")
        range_value = f"{base}..{branch}"
        records = commit_records(client.root, range_value)
        paths = changed_paths(client.root, base, branch)
        compact_records = [
            {
                "commit": str(record["commit"]),
                "subject": str(record["subject"]),
                "paths": list(record.get("paths", [])),
                "footer_ids": list(record.get("footer_ids", ())),
            }
            for record in records
        ]
        git.update(
            {
                "range": range_value,
                "commits": compact_records,
                "footer_mapping": footer_mapping(records),
                "changed_paths": paths,
                "diff_stat": diff_stat(client.root, base, branch),
            }
        )

    worktree_path = worktree_for_branch(client, branch)
    if worktree_path is None:
        git["worktree"] = {"status": "missing", "path": None}
    else:
        worktree = verify_worktree_identity(client.root, worktree_path, branch)
        execution_root = worktree
        status = run(["git", "status", "--short", "--untracked-files=all"], cwd=worktree, check=False)
        git["worktree"] = {
            "status": "clean" if status.returncode == 0 and not status.stdout.strip() else "dirty",
            "path": str(worktree),
            "details": truncate_output(status.stderr or status.stdout),
        }

    command = validation_command or os.environ.get("DSTACK_VALIDATION_COMMAND", "hk check -a")
    payload: dict[str, Any] = {
        "status": "ok",
        "feature": issue_view(root),
        "steps": {name: issue_view(issue) for name, issue in steps.items()},
        "plan_validation": validate_plan_issue(steps["plan"]),
        "implementation_tasks": [
            {"issue": issue_view(issue), "validation": validate_task_issue(issue)} for issue in implementation
        ],
        "decisions": [issue_view(issue) for issue in decisions],
        "gates": [issue_view(issue) for issue in gates],
        "git": git,
        "validation": _validation(execution_root, command, enabled=run_validation),
        "documentation": _documentation(execution_root, paths, enabled=run_validation),
    }
    if include_history:
        issues = [root, *steps.values(), *implementation, *decisions]
        payload["beads_history"] = {str(issue["id"]): client.history(str(issue["id"])) for issue in issues}
    return payload


def cmd_audit_evidence(args: argparse.Namespace) -> int:
    emit(
        collect_audit_evidence(
            args.root,
            args.feature,
            include_history=args.include_history,
            run_validation=args.run_validation,
            validation_command=args.validation_command,
        )
    )
    return 0
