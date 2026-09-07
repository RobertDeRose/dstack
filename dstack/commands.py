"""Deterministic dStack control-plane commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from .core import (
    BeadsClient,
    DstackError,
    _assert_no_symlink_components,
    require_common_history,
    as_items,
    audit_fan_in_errors,
    branch_exists,
    changed_paths,
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
from .git_ops import canonical_task_message, commit_record_matches_message
from .output import emit
from .policy import implementation_notes, no_repository_change_reason, validate_plan_issue, validate_task_issue

MAX_REVIEW_ITEMS = 100


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
        require_common_history(client.root, base_branch, branch)
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
        else:
            require_common_history(client.root, base_branch, branch)

        run(["bd", "worktree", "create", str(worktree), "--branch", branch], cwd=client.root)
        created_worktree = True
        observed = worktree_for_branch(client, branch)
        if observed is None:
            raise DstackError(f"Beads created no discoverable worktree for {branch}")
        verified = verify_worktree_identity(client.root, observed, branch)
        require_common_history(client.root, base_branch, branch)
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
    root, slug, base = feature_identity(client, args.bead)
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
    plan = client.show(args.bead)
    root = feature_identity(client, args.bead)[0]
    expected = feature_steps(client, str(root["id"]))["plan"]
    result = validate_plan_issue(plan)
    if str(plan.get("id")) != str(expected.get("id")):
        result["errors"].append(f"plan Bead is not the fixed plan step {expected['id']}")
        result["status"] = "invalid"
    emit(result)
    return 0 if result["status"] == "ok" else 4


def review_graph_errors(
    client: BeadsClient,
    root: Mapping[str, Any],
    steps: Mapping[str, Mapping[str, Any]],
    tasks: list[dict[str, Any]],
    *,
    ready_task_ids: list[str],
) -> list[str]:
    """Validate the complete native graph immediately before human approval."""

    errors: list[str] = []
    plan = client.show(str(steps["plan"]["id"]))
    plan_result = validate_plan_issue(plan)
    errors.extend(f"plan: {error}" for error in plan_result["errors"])
    if str(plan.get("status")) != "closed":
        errors.append("fixed plan step must be closed before approval")
    if str(steps["review"].get("status")) != "in_progress":
        errors.append("fixed review step must be in_progress during preapproval validation")
    if str(steps["approval"].get("status")) != "open":
        errors.append("fixed approval step must remain open during preapproval validation")
    if not tasks:
        errors.append("review must create at least one implementation task")

    for task in tasks:
        validation = validate_task_issue(task)
        errors.extend(f"{task.get('id')}: {error}" for error in validation["errors"])
        errors.extend(implementation_task_graph_errors(client, task, root, steps))
    errors.extend(audit_fan_in_errors(client, steps, tasks))

    if ready_task_ids:
        errors.append("implementation tasks are ready before approval: " + ", ".join(sorted(ready_task_ids)))
    return errors


def cmd_review_check(args: argparse.Namespace) -> int:
    client = client_for(args.root)
    root, slug, _ = feature_identity(client, args.bead)
    steps = feature_steps(client, str(root["id"]))
    tasks = implementation_tasks(client, str(steps["implementation"]["id"]))
    ready = as_items(
        client.json(
            [
                "bd",
                "ready",
                "--parent",
                str(steps["implementation"]["id"]),
                "--label",
                "dstack:work:implementation",
                "--limit",
                "0",
                "--json",
            ]
        ),
        context="bd ready implementation",
    )
    errors = review_graph_errors(
        client,
        root,
        steps,
        tasks,
        ready_task_ids=[str(item["id"]) for item in ready],
    )
    emit(
        {
            "status": "ok" if not errors else "invalid",
            "feature": root["id"],
            "slug": slug,
            "tasks": [str(task["id"]) for task in tasks[:MAX_REVIEW_ITEMS]],
            "task_count": len(tasks),
            "tasks_truncated": len(tasks) > MAX_REVIEW_ITEMS,
            "errors": errors[:MAX_REVIEW_ITEMS],
            "error_count": len(errors),
            "errors_truncated": len(errors) > MAX_REVIEW_ITEMS,
        }
    )
    return 0 if not errors else 4


def _worktree_status(path: Path) -> dict[str, Any]:
    result = run(["git", "status", "--short", "--untracked-files=all"], cwd=path, check=False)
    return {
        "status": "clean" if result.returncode == 0 and not result.stdout.strip() else "dirty",
        "returncode": result.returncode,
        "details": truncate_output(result.stderr) or truncate_output(result.stdout),
    }


def implementation_tasks(client: BeadsClient, implementation_id: str) -> list[dict[str, Any]]:
    children = sorted(
        (child for child in client.children(implementation_id) if issue_type(child) not in {"epic", "molecule", "gate"}),
        key=lambda child: str(child["id"]),
    )
    return client.show_many([str(child["id"]) for child in children])


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
    if str(task.get("status") or "") != "in_progress":
        errors.append("implementation task must be in_progress during validation")

    feature_root, slug, base = feature_identity(client, args.bead)
    steps = feature_steps(client, str(feature_root["id"]))
    # A task check needs this task and the fixed fan-in, not every sibling's body.
    errors.extend(graph_errors_for_task(client, task, feature_root, steps, [dict(task)]))

    branch = f"feat/{slug}"
    validate_git_revision(client.root, base, name="task evidence base")
    validate_git_revision(client.root, branch, name="task evidence branch")
    require_common_history(client.root, base, branch)
    evidence_range = f"{base}..{branch}"
    records = commit_records(
        client.root,
        evidence_range,
        include_paths=False,
        owner_id=str(task["id"]),
    )
    task_records = [record for record in records if args.bead in record.get("footer_ids", ())]
    evidence = [
        {
            "commit": str(record["commit"]),
            "subject": str(record["subject"]),
        }
        for record in task_records
    ]
    try:
        reject_beads_paths(changed_paths(client.root, base, branch))
    except DstackError as exc:
        errors.append(str(exc))

    notes_valid = True
    try:
        execution_notes = implementation_notes(task)
    except DstackError as exc:
        notes_valid = False
        execution_notes = []
        errors.append(str(exc))
    no_change = no_repository_change_reason(task) if notes_valid else None
    if notes_valid and not no_change and not execution_notes:
        errors.append("implementation task requires at least one Implementation note before committing")
    if not evidence and not no_change:
        errors.append("no reachable Git commit references this task and no `No repository change:` reason is recorded")
    elif len(evidence) > 1:
        errors.append("implementation task must have exactly one reachable canonical commit")
    elif evidence:
        try:
            expected_message = canonical_task_message(task, slug)
        except DstackError:
            errors.append("implementation task commit does not match the deterministic message contract")
        else:
            if not commit_record_matches_message(task_records[0], expected_message):
                errors.append("implementation task commit does not match the deterministic message contract")

    invalid_footer_commits = sorted(
        str(record["commit"])
        for record in records
        if (
            args.bead in record.get("legacy_footer_ids", ())
            or (args.bead in record.get("footer_ids", ()) and tuple(record.get("footer_ids", ())) != (args.bead,))
        )
    )
    if invalid_footer_commits:
        errors.append(
            "task evidence commits must contain exactly one ownership footer for this task: "
            + ", ".join(invalid_footer_commits)
        )

    worktree_path = worktree_for_branch(client, branch)
    worktree: dict[str, Any]
    if worktree_path is None:
        worktree = {"status": "missing", "branch": branch, "path": None}
        errors.append(f"feature worktree is not registered for {branch}")
    else:
        verified = verify_worktree_identity(client.root, worktree_path, branch)
        worktree = {"branch": branch, "path": str(verified), **_worktree_status(verified)}
        if worktree["status"] != "clean":
            errors.append("feature worktree contains uncommitted changes")

    result.update(
        {
            "status": "ok" if not errors else "invalid",
            "errors": errors,
            "feature": feature_root["id"],
            "graph": {
                "implementation": steps["implementation"]["id"],
                "approval": steps["approval"]["id"],
            },
            "evidence": {
                "range": evidence_range,
                "commits": evidence,
                "no_repository_change": no_change,
                "invalid_footer_commits": invalid_footer_commits,
            },
            "worktree": worktree,
        }
    )
    emit(result)
    return 0 if result["status"] == "ok" else 4
