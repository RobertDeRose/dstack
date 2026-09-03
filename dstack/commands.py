"""Deterministic dStack control-plane commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from .core import (
    BeadsClient,
    DstackError,
    _assert_no_symlink_components,
    ancestry,
    audit_fan_in_errors,
    branch_exists,
    commit_records,
    conventional_worktree,
    feature_identity,
    feature_steps,
    implementation_task_graph_errors,
    issue_type,
    reject_beads_paths,
    run,
    serialized_repository_mutation,
    truncate_output,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)
from .formula import beads_workspace, check_formula, init_workspace, install_formula
from .output import emit
from .policy import no_repository_change_reason, validate_plan_issue, validate_task_issue

VALIDATION_COMMAND = ("hk", "check", "-a")


@serialized_repository_mutation
def cmd_init(args: argparse.Namespace) -> int:
    emit(init_workspace(args.root, update=args.update))
    return 0


def client_for(root: Path) -> BeadsClient:
    repository = Path(root).expanduser()
    beads_workspace(repository)
    client = BeadsClient(repository)
    client.check_version()
    return client


@serialized_repository_mutation
def cmd_formula_install(args: argparse.Namespace) -> int:
    emit(install_formula(args.root, update=args.update))
    return 0


def cmd_formula_check(args: argparse.Namespace) -> int:
    emit(check_formula(args.root))
    return 0


def ensure_branch_worktree(client: BeadsClient, branch: str, base_branch: str) -> tuple[Path, bool, bool]:
    validate_git_branch(client.root, branch, name="feature branch")
    validate_git_branch(client.root, base_branch, name="base branch")
    validate_git_revision(client.root, base_branch, name="base branch")

    existing = worktree_for_branch(client, branch)
    if existing is not None:
        worktree = verify_worktree_identity(client.root, existing, branch)
        if not ancestry(client.root, base_branch, branch):
            raise DstackError(f"feature branch {branch} does not contain base branch {base_branch}")
        return worktree, False, False

    worktree = conventional_worktree(client.root, branch)
    _assert_no_symlink_components(worktree, purpose="feature worktree")
    if worktree.exists():
        raise DstackError(f"conventional worktree path exists but Beads does not register it for {branch}: {worktree}")

    created_branch = False
    created_worktree = False
    try:
        if not branch_exists(client.root, branch):
            run(["git", "branch", "--", branch, base_branch], cwd=client.root)
            created_branch = True
        elif not ancestry(client.root, base_branch, branch):
            raise DstackError(f"feature branch {branch} does not contain base branch {base_branch}")

        run(["bd", "worktree", "create", str(worktree), "--branch", branch], cwd=client.root)
        created_worktree = True
        observed = worktree_for_branch(client, branch)
        if observed is None:
            raise DstackError(f"Beads created no discoverable worktree for {branch}")
        verified = verify_worktree_identity(client.root, observed, branch)
        if not ancestry(client.root, base_branch, branch):
            raise DstackError(f"created feature branch {branch} does not contain base branch {base_branch}")
        return verified, created_branch, created_worktree
    except Exception as primary:
        cleanup: list[str] = []
        try:
            observed = worktree_for_branch(client, branch)
        except Exception:
            observed = None

        retained = observed or (worktree if worktree.exists() else None)
        if created_worktree and observed is not None and observed.resolve() == worktree.resolve():
            result = run(["bd", "worktree", "remove", str(worktree), "--force"], cwd=client.root, check=False)
            if result.returncode:
                cleanup.append(result.stderr.strip() or result.stdout.strip() or "worktree removal failed")
            retained = worktree if worktree.exists() else None

        if created_branch and retained is None and branch_exists(client.root, branch):
            result = run(["git", "branch", "-D", "--", branch], cwd=client.root, check=False)
            if result.returncode:
                cleanup.append(result.stderr.strip() or result.stdout.strip() or "branch removal failed")

        if cleanup:
            raise DstackError(f"{primary}; cleanup failed: {'; '.join(cleanup)}") from primary
        if retained is not None:
            raise DstackError(
                f"{primary}; retained_path={retained}; inspect `bd worktree list --json` and Git before retrying"
            ) from primary
        raise


@serialized_repository_mutation
def cmd_worktree_ensure(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root, slug, base = feature_identity(client, args.feature)
    branch = f"feat/{slug}"
    worktree, created_branch, created_worktree = ensure_branch_worktree(client, branch, base)
    emit(
        {
            "status": "ok",
            "feature": root["id"],
            "branch": branch,
            "base_branch": base,
            "worktree": str(worktree),
            "created_branch": created_branch,
            "created_worktree": created_worktree,
        }
    )
    return 0


def cmd_plan_check(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    result = validate_plan_issue(client.show(args.bead))
    emit(result)
    return 0 if result["status"] == "ok" else 4


def _worktree_status(path: Path) -> dict[str, Any]:
    result = run(["git", "status", "--short", "--untracked-files=all"], cwd=path, check=False)
    return {
        "status": "clean" if result.returncode == 0 and not result.stdout.strip() else "dirty",
        "returncode": result.returncode,
        "details": truncate_output(result.stderr) or truncate_output(result.stdout),
    }


def run_project_validation(path: Path) -> dict[str, Any]:
    result = run(VALIDATION_COMMAND, cwd=path, check=False)
    payload: dict[str, Any] = {
        "status": "ok" if result.returncode == 0 else "failed",
        "command": list(VALIDATION_COMMAND),
        "returncode": result.returncode,
    }
    if result.returncode != 0:
        payload["stdout"] = truncate_output(result.stdout)
        payload["stderr"] = truncate_output(result.stderr)
    return payload


def implementation_tasks(
    client: BeadsClient,
    implementation_id: str,
    *,
    limit: int | None = None,
    known_task: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for child in client.children(implementation_id, limit=limit):
        if issue_type(child) in {"epic", "molecule", "gate"}:
            continue
        child_id = str(child["id"])
        if known_task is not None and str(known_task.get("id")) == child_id:
            tasks.append(dict(known_task))
        else:
            tasks.append(client.show(child_id))
    return tasks


def graph_errors_for_task(
    client: BeadsClient,
    task: Mapping[str, Any],
    feature_root: Mapping[str, Any],
    steps: Mapping[str, Mapping[str, Any]],
    tasks: list[dict[str, Any]],
) -> list[str]:
    errors = implementation_task_graph_errors(client, task, feature_root, steps)
    errors.extend(audit_fan_in_errors(client, steps, tasks))
    return errors


def cmd_task_check(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    task = client.show(args.bead)
    result = validate_task_issue(task)
    errors = list(result["errors"])

    feature_root, slug, base = feature_identity(client, args.bead)
    steps = feature_steps(client, str(feature_root["id"]))
    tasks = implementation_tasks(
        client,
        str(steps["implementation"]["id"]),
        known_task=task,
    )
    errors.extend(graph_errors_for_task(client, task, feature_root, steps, tasks))

    branch = f"feat/{slug}"
    validate_git_revision(client.root, base, name="task evidence base")
    validate_git_revision(client.root, branch, name="task evidence branch")
    if not ancestry(client.root, base, branch):
        errors.append(f"feature branch {branch} does not contain base branch {base}")
    evidence_range = f"{base}..{branch}"
    records = commit_records(client.root, evidence_range)
    evidence = [
        {
            "commit": str(record["commit"]),
            "subject": str(record["subject"]),
            "paths": list(record.get("paths", [])),
        }
        for record in records
        if args.bead in record.get("footer_ids", ())
    ]
    try:
        reject_beads_paths([path for record in records for path in record.get("paths", [])])
    except DstackError as exc:
        errors.append(str(exc))

    no_change = no_repository_change_reason(task)
    if not evidence and not no_change:
        errors.append("no reachable Git commit references this Bead and no `No repository change:` reason is recorded")

    invalid_footer_commits = sorted(
        str(record["commit"])
        for record in records
        if args.bead in record.get("footer_ids", ()) and tuple(record.get("footer_ids", ())) != (args.bead,)
    )
    if invalid_footer_commits:
        errors.append(
            "task evidence commits must contain exactly one Beads footer for this task: "
            + ", ".join(invalid_footer_commits)
        )

    worktree_path = worktree_for_branch(client, branch)
    worktree: dict[str, Any]
    if worktree_path is None:
        worktree = {"status": "missing", "branch": branch, "path": None}
        validation = {"status": "blocked", "command": list(VALIDATION_COMMAND)}
        errors.append(f"feature worktree is not registered for {branch}")
    else:
        verified = verify_worktree_identity(client.root, worktree_path, branch)
        worktree = {"branch": branch, "path": str(verified), **_worktree_status(verified)}
        if worktree["status"] != "clean":
            errors.append("feature worktree contains uncommitted changes")

        validation = run_project_validation(verified)
        if validation["status"] == "failed":
            errors.append("project validation failed")
        post_validation_status = _worktree_status(verified)
        worktree["post_validation_status"] = post_validation_status["status"]
        worktree["post_validation_details"] = post_validation_status["details"]
        if (
            post_validation_status["status"] != "clean"
            and "feature worktree contains uncommitted changes" not in errors
        ):
            errors.append("project validation left uncommitted changes in the feature worktree")

    result.update(
        {
            "status": "ok" if not errors else "invalid",
            "errors": errors,
            "feature": feature_root["id"],
            "graph": {
                "implementation": steps["implementation"]["id"],
                "approval": steps["approval"]["id"],
                "audit": steps["audit"]["id"],
            },
            "evidence": {
                "range": evidence_range,
                "commits": evidence,
                "no_repository_change": no_change,
                "invalid_footer_commits": invalid_footer_commits,
            },
            "worktree": worktree,
            "validation": validation,
        }
    )
    emit(result)
    return 0 if result["status"] == "ok" else 4
