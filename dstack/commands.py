#!/usr/bin/env python3
"""Stateless deterministic controller for dstack workflows.

The controller delegates durable state to Beads and repository history to Git.
It performs mechanical validation and idempotent transitions so the agent can
focus on engineering decisions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any, Mapping, Sequence

from .formula import ensure_infrastructure
from .core import (
    BeadsClient,
    DstackError,
    FEATURE_STEPS,
    ancestry,
    branch_exists,
    commit_footer_ids,
    conventional_worktree,
    dependency_records,
    has_label,
    issue_parent,
    issue_type,
    read_text_file,
    root_metadata_value,
    run,
    validate_git_branch,
    validate_git_revision,
    verify_worktree_identity,
    worktree_for_branch,
)

# Beads repository configuration is allowed to be tracked. Only machine-local
# runtime/sensitive artifacts are forbidden. This mirrors the Beads 1.2.2
# doctor classification, with interactions.jsonl additionally excluded by the
# dStack Git-decoupling policy.
DSTACK_UNTRACKED_BEADS_FILES = {
    ".beads/interactions.jsonl",
}
BEADS_RUNTIME_DIR_PREFIXES = (
    ".beads/dolt/",
    ".beads/embeddeddolt/",
    ".beads/proxieddb/",
    ".beads/backup/",
    ".beads/export-state/",
    ".beads/dolt-pprof/",
)
BEADS_RUNTIME_TOP_LEVEL_PATTERNS = (
    "*.lock",
    "*.pid.lock",
    "daemon.*",
    "dolt-server.pid",
    "dolt-server.log",
    "dolt-server.lock",
    "dolt-server.port",
    "dolt-server.activity",
    "bd.sock",
    "bd.sock.startlock",
    ".exclusive-lock",
    "push-state.json",
    "export-state.json",
    "sync-state.json",
    "dolt-backup*.json",
    "last-touched",
    "last_pull",
    ".local_version",
    "redirect",
    ".sync.lock",
    "ephemeral.sqlite3",
    "ephemeral.sqlite3-journal",
    "ephemeral.sqlite3-wal",
    "ephemeral.sqlite3-shm",
    "proxied_server_client_info.json",
    ".env",
)
BEADS_SENSITIVE_BASENAMES = {
    ".beads-credential-key",
    "credential-key",
}
FORBIDDEN_DOC_PATTERNS = (
    re.compile(
        r"(?i)^\s*[-*]?\s*dstack(?:\s+workflow)?\s+status:\s*(in[- ]?progress|delivery[- ]?ready|blocked|review[- ]?active|completed)\b"
    ),
    re.compile(r"(?i)^\s*[-*]?\s*beads?\s+(root|id|task):"),
    re.compile(
        r"(?i)^\s*[-*]?\s*(gate id|feature branch|worktree|candidate commit|"
        r"reviewed commit|delivery commit):"
    ),
    re.compile(
        r"(?i)^\s*[-*]?\s*(next command|next action|resume with|suggested command):"
        r"\s*/(plan-features?|start-feature|review-feature-spec|implement-feature|close-feature)\b"
    ),
)
DESIGN_SCAFFOLD = """# Feature design

## Planned intent

{planned_intent}

## Planned acceptance

{planned_acceptance}

## Feature summary

## User intent

## Goals

## Non-goals

## User-visible behavior

## Requirements

## Existing patterns and reuse

## Proposed design

## Architecture consistency

## Interfaces and data flow

## Failure behavior

## Security implications

## Compatibility and migration implications

## Validation strategy

## Documentation impact

### End user and operator

- Usage and configuration:
- Deployment, upgrade, and rollback:
- Operations, troubleshooting, and recovery:

### Developer and reviewer

- Architecture and structure:
- Interfaces, contracts, and maintenance:

### Future auditor

- Decisions and rationale:
- Invariants, regression evidence, and known limitations:

## Risks and tradeoffs

## Rejected alternatives

## Open or intentionally deferred decisions
"""

RECONCILIATION_SCAFFOLD = """# {title}

[Design record](design.md)

## Delivered capability

## User-visible behavior

## Architecture integration

## Design reconciliation

### Delivered as designed

### Intentional differences

### Deferred scope

### Removed or rejected scope

## Documentation

### End user and operator

### Developer and reviewer

### Future auditor

## Validation and limitations
"""

ALIGNMENT_RECONCILIATION_SCAFFOLD = """# Alignment reconciliation

## Delivered corrections

## Remaining findings and limitations

## Architecture integration

## Documentation and operator effects

## Validation evidence

## Recovery and follow-up obligations
"""

RECORD_SUBJECTS = {
    "feature-design": (
        "Feature summary",
        "User intent",
        "Goals",
        "Non-goals",
        "User-visible behavior",
        "Requirements",
        "Existing patterns and reuse",
        "Proposed design",
        "Architecture consistency",
        "Interfaces and data flow",
        "Failure behavior",
        "Security implications",
        "Compatibility and migration implications",
        "Validation strategy",
        "Documentation impact",
        "End user and operator",
        "Developer and reviewer",
        "Future auditor",
        "Risks and tradeoffs",
        "Rejected alternatives",
        "Open or intentionally deferred decisions",
    ),
    "feature-reconciliation": (
        "Delivered capability",
        "User-visible behavior",
        "Architecture integration",
        "Design reconciliation",
        "Delivered as designed",
        "Intentional differences",
        "Deferred scope",
        "Removed or rejected scope",
        "Documentation",
        "End user and operator",
        "Developer and reviewer",
        "Future auditor",
        "Validation and limitations",
    ),
    "alignment-reconciliation": (
        "Delivered corrections",
        "Remaining findings and limitations",
        "Architecture integration",
        "Documentation and operator effects",
        "Validation evidence",
        "Recovery and follow-up obligations",
    ),
}

NO_REPOSITORY_CHANGE_PREFIX = "no-repository-change: "
_RECONCILIATION_TITLE = re.compile(r"(?i)\b(?:reconcil\w*|document\w*|docs?)\b")


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def fail(message: str) -> int:
    json.dump({"status": "error", "error": message}, sys.stderr)
    sys.stderr.write("\n")
    return 1


def client_for(root: Path, *, initialize: bool = True) -> BeadsClient:
    if initialize:
        infrastructure = ensure_infrastructure(root)
        return BeadsClient(Path(infrastructure["root"]))
    client = BeadsClient(root)
    client.check_version()
    return client


def cmd_infra_check(args: argparse.Namespace) -> int:
    infrastructure = ensure_infrastructure(args.root)
    emit(
        {
            "status": "ok",
            "root": str(infrastructure["root"]),
            "initialized": infrastructure["initialized"],
            "formula_versions": infrastructure["formula_versions"],
            "beads_version": infrastructure["beads_version"],
        }
    )
    return 0


def update_root_identity(
    client: BeadsClient,
    root_id: str,
    *,
    title: str,
    slug: str,
    base_branch: str,
    design_path: str,
    description: str | None = None,
    acceptance: str | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    arguments = [
        "--title",
        f"Feature: {title}",
        "--add-label",
        "workflow:feature",
        "--add-label",
        f"feature:{slug}",
        "--set-metadata",
        f"dstack.base_branch={base_branch}",
        "--set-metadata",
        f"dstack.design_path={design_path}",
    ]
    if description:
        arguments.extend(["--description", description])
    if acceptance:
        arguments.extend(["--acceptance", acceptance])
    if priority is not None:
        arguments.extend(["--priority", str(priority)])
    return client.update(root_id, *arguments)


def ensure_branch_worktree(
    client: BeadsClient,
    branch: str,
    base_branch: str,
) -> tuple[str, Path, bool, bool]:
    validate_git_branch(client.root, branch, name="candidate branch")
    validate_git_branch(client.root, base_branch, name="base branch")
    validate_git_revision(client.root, base_branch, name="base branch")

    created_branch = False
    created_worktree = False
    worktree = worktree_for_branch(client.root, branch)
    if worktree is not None:
        resolved = verify_worktree_identity(client.root, worktree, branch)
        if not ancestry(client.root, base_branch, branch):
            raise DstackError(f"candidate branch {branch} does not contain base {base_branch}")
        return branch, resolved, created_branch, created_worktree

    worktree = conventional_worktree(client.root, branch)
    if worktree.exists():
        raise DstackError(f"conventional worktree path exists but is not registered for {branch}: {worktree}")

    try:
        if not branch_exists(client.root, branch):
            run(["git", "branch", "--", branch, base_branch], cwd=client.root)
            created_branch = True
        elif not ancestry(client.root, base_branch, branch):
            raise DstackError(f"candidate branch {branch} does not contain base {base_branch}")

        created_worktree = True
        run(
            ["bd", "worktree", "create", str(worktree), "--branch", branch],
            cwd=client.root,
        )
        resolved = worktree_for_branch(client.root, branch)
        if resolved is None:
            raise DstackError(f"Beads created no discoverable worktree for {branch}")
        resolved = verify_worktree_identity(client.root, resolved, branch)
        if not ancestry(client.root, base_branch, branch):
            raise DstackError(f"created candidate branch {branch} does not contain base {base_branch}")
        return branch, resolved, created_branch, created_worktree
    except Exception as primary:
        cleanup: list[str] = []
        if created_worktree and (worktree.exists() or worktree_for_branch(client.root, branch) is not None):
            result = run(
                ["bd", "worktree", "remove", str(worktree), "--force"],
                cwd=client.root,
                check=False,
            )
            if result.returncode:
                cleanup.append(result.stderr.strip() or "worktree removal failed")
        if created_branch and branch_exists(client.root, branch):
            result = run(
                ["git", "branch", "-D", "--", branch],
                cwd=client.root,
                check=False,
            )
            if result.returncode:
                cleanup.append(result.stderr.strip() or "branch removal failed")
        if cleanup:
            raise DstackError(f"{primary}; cleanup failed: " + "; ".join(cleanup)) from primary
        raise


def ensure_feature_worktree(
    client: BeadsClient,
    slug: str,
    base_branch: str,
) -> tuple[str, Path, bool, bool]:
    return ensure_branch_worktree(client, f"feat/{slug}", base_branch)


def descendants(client: BeadsClient, root_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    queue = deque([root_id])
    seen = {root_id}
    while queue:
        parent = queue.popleft()
        for child in client.children(parent):
            child_id = str(child["id"])
            if child_id in seen:
                continue
            seen.add(child_id)
            result.append(child)
            queue.append(child_id)
    return result


def superseded_target(issue: Mapping[str, Any]) -> str | None:
    for record in dependency_records(issue):
        relation = str(record.get("type") or record.get("dependency_type") or "")
        if relation not in {"superseded-by", "superseded_by", "supersedes"}:
            continue
        target = record.get("depends_on_id") or record.get("id")
        if isinstance(target, str) and target != issue.get("id"):
            return target
    return None


def task_text(path: Path | None, inline: str | None) -> str:
    if path:
        return read_text_file(path)
    return (inline or "").strip()


def required_task_text(path: Path | None, inline: str | None) -> str:
    text = task_text(path, inline)
    if not text:
        raise DstackError("acceptance criteria is required")
    return text


def claim_issue_if_needed(client: BeadsClient, issue: Mapping[str, Any]) -> dict[str, Any]:
    if issue.get("status") == "closed":
        return dict(issue)
    return client.update(str(issue["id"]), "--claim")


def release_claim(client: BeadsClient, issue_id: str) -> dict[str, Any]:
    """Restore a newly raced claim and verify that ownership is clear."""

    try:
        client.update(
            issue_id,
            "--status",
            "open",
            "--assignee",
            "",
        )
        observed = client.show(issue_id)
    except DstackError as exc:
        raise DstackError(f"failed to release raced claim {issue_id}; ownership is uncertain") from exc
    if observed.get("status") != "open" or observed.get("assignee"):
        raise DstackError(f"failed to release raced claim {issue_id}; ownership is uncertain")
    return observed


def release_claims(client: BeadsClient, claimed: Sequence[Mapping[str, Any]]) -> list[str]:
    errors = []
    for item in claimed:
        try:
            release_claim(client, str(item["id"]))
        except DstackError as exc:
            errors.append(str(exc))
    return errors


def claim_ready_work(
    client: BeadsClient,
    *,
    parent_id: str,
    label: str,
    requested_id: str | None = None,
) -> dict[str, Any] | None:
    def validate(item: Mapping[str, Any]) -> None:
        item_id = str(item["id"])
        if issue_parent(item) != parent_id:
            raise DstackError(f"task {item_id} is not a direct child of {parent_id}")
        if not has_label(item, label):
            raise DstackError(f"task {item_id} lacks required label {label}")

    if requested_id:
        requested = client.show(requested_id)
        validate(requested)
        if requested.get("status") == "closed":
            return dict(requested)
        if requested.get("status") in {"claimed", "in_progress"}:
            return client.update(requested_id, "--claim")
        if requested.get("status") != "open":
            raise DstackError(f"task {requested_id} cannot be claimed from status {requested.get('status')!r}")
        ready = client.ready_children(parent_id, label=label)
        if not any(str(item.get("id")) == requested_id for item in ready):
            raise DstackError(f"task {requested_id} is not currently ready")

    # Do not preselect a no-selector candidate: the native atomic claim owns
    # selection, including races between ready candidates.
    claimed = client.ready_children(parent_id, label=label, claim=True)
    expected_id = requested_id
    if not claimed:
        raise DstackError(
            "native ready claim returned no task" + (f" for requested {requested_id}" if requested_id else "")
        )
    if len(claimed) != 1 or (expected_id is not None and str(claimed[0].get("id")) != expected_id):
        recovery_errors = release_claims(client, claimed)
        detail = f"; {'; '.join(recovery_errors)}" if recovery_errors else ""
        expected = expected_id or "a valid singleton"
        raise DstackError(f"native ready claim did not return requested singleton {expected}{detail}")
    try:
        validate(claimed[0])
    except DstackError:
        recovery_errors = release_claims(client, claimed)
        if recovery_errors:
            raise DstackError("; ".join(recovery_errors))
        raise
    return claimed[0]


def close_issue_if_needed(client: BeadsClient, issue: Mapping[str, Any], reason: str) -> dict[str, Any]:
    if issue.get("status") == "closed":
        return dict(issue)
    claimed = claim_issue_if_needed(client, issue)
    return client.close(str(claimed["id"]), reason)


def resolve_gate_if_needed(client: BeadsClient, gate: Mapping[str, Any], reason: str) -> dict[str, Any]:
    if gate.get("status") == "closed":
        return dict(gate)
    return client.resolve_gate(str(gate["id"]), reason)


def open_workstream_children(client: BeadsClient, parent_id: str) -> list[dict[str, Any]]:
    return [item for item in client.children(parent_id) if item.get("status") not in {"closed", "deferred"}]


def require_complete_fan_in(client: BeadsClient, *, parent_id: str, name: str) -> None:
    # ponytail: Beads 1.2.2 can miss open dynamic children in children-of();
    # remove this guard when a supported Beads release fixes native fan-in.
    open_items = open_workstream_children(client, parent_id)
    if open_items:
        ids = ", ".join(str(item["id"]) for item in open_items)
        raise DstackError(f"{name} has nonterminal children: {ids}")


def claim_ready_step(
    client: BeadsClient,
    *,
    root_id: str,
    step: Mapping[str, Any],
    label: str,
    name: str,
) -> dict[str, Any]:
    """Claim one known lifecycle step through Beads-native readiness."""

    status = str(step.get("status") or "")
    if status == "closed":
        return dict(step)
    if status in {"in_progress", "claimed"}:
        return client.update(str(step["id"]), "--claim")
    claimed = client.ready_children(root_id, label=label, claim=True)
    if not claimed:
        raise DstackError(f"{name} is not ready according to Beads")
    if len(claimed) != 1 or str(claimed[0].get("id")) != str(step.get("id")):
        ids = ", ".join(str(item.get("id")) for item in claimed)
        recovery_errors = release_claims(client, claimed)
        detail = f"; {'; '.join(recovery_errors)}" if recovery_errors else ""
        raise DstackError(f"Beads claimed an unexpected {name} step: {ids or 'none'}{detail}")
    return claimed[0]


def claim_ready_step_with_fan_in(
    client: BeadsClient,
    *,
    root_id: str,
    step: Mapping[str, Any],
    label: str,
    name: str,
    fan_in_parent_id: str,
    fan_in_name: str,
) -> dict[str, Any]:
    require_complete_fan_in(client, parent_id=fan_in_parent_id, name=fan_in_name)
    newly_claimed = step.get("status") not in {"closed", "in_progress", "claimed"}
    claimed = claim_ready_step(client, root_id=root_id, step=step, label=label, name=name)
    try:
        require_complete_fan_in(client, parent_id=fan_in_parent_id, name=fan_in_name)
    except DstackError as fan_in_error:
        if newly_claimed:
            try:
                release_claim(client, str(claimed["id"]))
            except DstackError as recovery_error:
                raise DstackError(f"{fan_in_error}; {recovery_error}") from recovery_error
        raise
    return claimed


def require_open_unassigned_terminal(issue: Mapping[str, Any], *, name: str) -> None:
    if issue.get("status") != "open" or issue.get("assignee") not in (None, ""):
        raise DstackError(
            f"{name} must be exactly open and unassigned before reauthorization: "
            f"status={issue.get('status')!r}, assignee={issue.get('assignee')!r}"
        )


def reopen_authorization_boundary(
    client: BeadsClient,
    *,
    root_id: str,
    planning_id: str,
    approval_id: str,
    gate_id: str,
    workstream_id: str,
    terminal_id: str,
    reason: str,
    digest_key: str | None = None,
    pending_digest_key: str | None = None,
) -> None:
    reason = reason.strip()
    if not reason:
        raise DstackError("reauthorization requires a non-empty reason")
    terminal = client.show(terminal_id)
    require_open_unassigned_terminal(terminal, name="terminal reconciliation")
    in_flight = [item for item in client.children(workstream_id) if item.get("status") in {"claimed", "in_progress"}]
    if in_flight:
        ids = ", ".join(str(item["id"]) for item in in_flight)
        raise DstackError(f"cannot reauthorize while work is claimed: {ids}")

    for key in (digest_key, pending_digest_key):
        if key and root_metadata_value(client.show(root_id), key):
            client.update(root_id, "--unset-metadata", key)

    for issue_id in (approval_id, gate_id, planning_id, workstream_id):
        issue = client.show(issue_id)
        status = issue.get("status")
        if status == "closed":
            client.reopen(issue_id, f"Reauthorize workflow: {reason}")
        elif status in {"claimed", "in_progress"}:
            client.update(issue_id, "--status", "open")
        elif status != "open":
            raise DstackError(f"cannot reauthorize {issue_id} from unsupported status {status!r}")
    require_open_unassigned_terminal(client.show(terminal_id), name="terminal reconciliation")


def keep_root_open_for_delivery(client: BeadsClient, root_id: str) -> None:
    """Compensate for Beads 1.2.2 closing a molecule at its terminal step."""

    root = client.show(root_id)
    if root.get("status") == "closed" and root.get("close_reason") == "all steps complete":
        client.reopen(root_id, "Await delivery")


def feature_branch_context(client: BeadsClient, view: Mapping[str, Any]) -> tuple[str, Path, str]:
    slug = str(view.get("slug") or "")
    base = str(view.get("base_branch") or "")
    if not slug or not base:
        raise DstackError("feature root lacks slug or base branch")
    branch = f"feat/{slug}"
    validate_git_branch(client.root, branch, name="feature branch")
    validate_git_branch(client.root, base, name="base branch")
    validate_git_revision(client.root, base, name="base branch")
    worktree = worktree_for_branch(client.root, branch)
    if worktree is None:
        raise DstackError(f"no worktree is registered for {branch}")
    worktree = verify_worktree_identity(client.root, worktree, branch)
    if not ancestry(client.root, base, branch):
        raise DstackError(f"feature branch {branch} does not contain base {base}")
    return branch, worktree, base


def evidence_for_bead(root: Path, bead_id: str, ref_range: str) -> list[dict[str, Any]]:
    return commit_footer_ids(root, ref_range).get(bead_id, [])


def reject_documentation_work(title: str, *, stage: str) -> None:
    if _RECONCILIATION_TITLE.search(title):
        raise DstackError(
            f"{stage} tasks cannot own documentation or reconciliation; use the sole final reconciliation"
        )


def require_no_documentation_changes(evidence: Sequence[Mapping[str, Any]], *, stage: str) -> None:
    paths = sorted(
        {
            str(path)
            for record in evidence
            for path in record.get("paths", [])
            if str(path).startswith("docs/") or str(path).casefold().endswith((".md", ".mdx", ".rst"))
        }
    )
    if paths:
        raise DstackError(
            f"{stage} work must defer documentation changes to the final reconciliation: " + ", ".join(paths)
        )


def completion_reason(args: argparse.Namespace, default: str) -> str:
    if args.no_repository_change:
        reason = (args.reason or "").strip()
        if not reason:
            raise DstackError("--no-repository-change requires a non-empty --reason")
        return f"{NO_REPOSITORY_CHANGE_PREFIX}{reason}"
    return (args.reason or default).strip() or default


def require_approved_design(view: Mapping[str, Any]) -> None:
    if not view.get("approved_design_sha256"):
        raise DstackError("feature specification has no approved design digest")
    if not view.get("native_approved"):
        raise DstackError("feature native approval state is incomplete")
    if not view.get("design_approved"):
        raise DstackError("feature design is not the committed approved specification; rerun /review-feature-spec")


def preserve_external_blockers(
    client: BeadsClient,
    source: Mapping[str, Any],
    target_id: str,
) -> list[str]:
    source_id = str(source["id"])
    source_ids = {source_id, *[str(item["id"]) for item in descendants(client, source_id)]}
    target = client.show(target_id)
    target_kind = issue_type(target)
    compatible_target = target_id
    if target_kind == "molecule":
        children = client.children(target_id)
        compatible_steps = {
            "epic": [
                item
                for item in children
                if issue_type(item) == "epic" and has_label(item, FEATURE_STEPS["implementation"])
            ],
            "task": [
                item for item in children if issue_type(item) == "task" and has_label(item, FEATURE_STEPS["approval"])
            ],
        }
    else:
        compatible_steps = {}

    preserved: list[str] = []
    for record in dependency_records(source):
        relation = str(record.get("type") or record.get("dependency_type") or "blocks")
        blocker_id = record.get("depends_on_id") or record.get("id")
        if relation != "blocks" or not isinstance(blocker_id, str) or blocker_id in source_ids:
            continue
        blocker = client.show_optional(blocker_id)
        if blocker is None or blocker.get("status") == "closed":
            continue
        blocker_kind = issue_type(blocker)
        destination = compatible_target
        if blocker_kind != target_kind:
            candidates = compatible_steps.get(blocker_kind, [])
            if len(candidates) != 1:
                raise DstackError(f"cannot preserve {blocker_kind} blocker {blocker_id} on {target_id} ({target_kind})")
            destination = str(candidates[0]["id"])
        client.add_dependency(destination, blocker_id)
        preserved.append(blocker_id)
    return preserved
