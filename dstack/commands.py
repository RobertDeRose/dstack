"""Deterministic dStack control-plane commands."""

from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path
from typing import Any

from .core import (
    BeadsClient,
    DstackError,
    _assert_no_symlink_components,
    ancestry,
    branch_exists,
    commit_records,
    commits_for_bead,
    conventional_worktree,
    feature_identity,
    has_label,
    issue_parent,
    run,
    serialized_repository_mutation,
    truncate_output,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)
from .formula import check_infrastructure, ensure_beads_initialized, install_infrastructure
from .output import emit
from .policy import no_repository_change_reason, validate_plan_issue, validate_task_issue


def client_for(root: Path) -> BeadsClient:
    repository, _ = ensure_beads_initialized(root, initialize=False)
    client = BeadsClient(repository)
    client.check_version()
    return client


@serialized_repository_mutation
def cmd_infra_install(args: argparse.Namespace) -> int:
    emit(install_infrastructure(args.root, update_formula=args.update_formula))
    return 0


def cmd_infra_check(args: argparse.Namespace) -> int:
    emit(check_infrastructure(args.root))
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
        raise DstackError(f"conventional worktree path exists but is not registered for {branch}: {worktree}")

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
        observed: Path | None = None
        try:
            observed = worktree_for_branch(client, branch)
        except Exception:
            observed = None

        if created_worktree and observed is not None and observed.resolve() == worktree.resolve():
            result = run(["bd", "worktree", "remove", str(worktree), "--force"], cwd=client.root, check=False)
            if result.returncode:
                cleanup.append(result.stderr.strip() or result.stdout.strip() or "worktree removal failed")
        elif not created_worktree and (worktree.exists() or observed is not None):
            retained = observed or worktree
            raise DstackError(
                f"{primary}; worktree creation may have changed native state; retained_path={retained}; "
                "inspect `bd worktree list --json` before retrying"
            ) from primary

        if created_branch and worktree_for_branch(client, branch) is None and branch_exists(client.root, branch):
            result = run(["git", "branch", "-D", "--", branch], cwd=client.root, check=False)
            if result.returncode:
                cleanup.append(result.stderr.strip() or result.stdout.strip() or "branch removal failed")
        if cleanup:
            raise DstackError(f"{primary}; cleanup failed: {'; '.join(cleanup)}") from primary
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
        "details": truncate_output(result.stderr or result.stdout),
    }


def _validation(path: Path, command_text: str, *, enabled: bool) -> dict[str, Any]:
    command = shlex.split(command_text)
    if not enabled:
        return {"status": "not-run", "command": command}
    if not command:
        raise DstackError("validation command must not be empty")
    result = run(command, cwd=path, check=False)
    return {
        "status": "ok" if result.returncode == 0 else "failed",
        "command": command,
        "returncode": result.returncode,
        "stdout": truncate_output(result.stdout),
        "stderr": truncate_output(result.stderr),
    }


def cmd_task_check(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    task = client.show(args.bead)
    result = validate_task_issue(task)
    errors = list(result["errors"])

    parent_id = issue_parent(task)
    if parent_id is None:
        errors.append("implementation Bead has no native parent")
    else:
        parent = client.show(parent_id)
        if not has_label(parent, "dstack:step:implementation"):
            errors.append("implementation Bead is not a child of the feature implementation epic")

    feature_root, slug, inferred_base = feature_identity(client, args.bead)
    base = args.base or inferred_base
    head = args.head or f"feat/{slug}"
    validate_git_revision(client.root, base, name="task evidence base")
    validate_git_revision(client.root, head, name="task evidence head")
    evidence_range = f"{base}..{head}"
    records = commit_records(client.root, evidence_range)
    evidence = commits_for_bead(client.root, evidence_range, args.bead)
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

    branch = f"feat/{slug}"
    worktree_path = worktree_for_branch(client, branch)
    worktree: dict[str, Any]
    execution_root = client.root
    if worktree_path is None:
        worktree = {"status": "missing", "branch": branch, "path": None}
        errors.append(f"feature worktree is not registered for {branch}")
    else:
        verified = verify_worktree_identity(client.root, worktree_path, branch)
        execution_root = verified
        worktree = {"branch": branch, "path": str(verified), **_worktree_status(verified)}
        if worktree["status"] != "clean":
            errors.append("feature worktree contains uncommitted changes")

    validation_command = args.validation_command or os.environ.get("DSTACK_VALIDATION_COMMAND", "hk check -a")
    validation = _validation(execution_root, validation_command, enabled=args.run_validation)
    if validation["status"] == "failed":
        errors.append("project validation failed")
    if worktree_path is not None:
        post_validation_status = _worktree_status(execution_root)
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
