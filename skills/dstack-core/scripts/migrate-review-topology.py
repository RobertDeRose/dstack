#!/usr/bin/env python3
# ruff: noqa: EM101, EM102, S607
"""Upgrade existing Beads review gates to the current dstack workflow graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, NoReturn

from beads_workflow_lock import canonical_repository_root, WorkflowLock, WorkflowLockError


PLAN_SCHEMA = "dstack.review-topology-plan.v1"
MARKER_SCHEMA = "dstack.review-topology-cutover.v1"
ERROR_SCHEMA = "dstack.review-topology-error.v1"
TOPOLOGY_VERSION = 3
PHASES = frozenset({"unstarted", "spec-review", "implementation", "close-out", "delivered"})
OLD_KINDS = ("architecture", "simplicity", "documentation", "execution", "delivery", "drift")
TARGET_FOR_OLD = {
    "architecture": "specification-clarity",
    "simplicity": "specification-clarity",
    "documentation": "specification-clarity",
    "execution": "execution-readiness",
    "delivery": "delivery-integrity",
    "drift": "delivery-integrity",
}
TARGET_TITLES = {
    "specification-clarity": "Review specification clarity",
    "execution-readiness": "Review execution readiness",
    "implementation-integrity": "Review implementation integrity",
    "delivery-integrity": "Review delivery integrity",
}
TARGET_METADATA = {
    "specification-clarity": "review_specification_clarity_id",
    "execution-readiness": "review_execution_readiness_id",
    "implementation-integrity": "review_implementation_integrity_id",
    "delivery-integrity": "review_delivery_integrity_id",
}


class MigrationError(RuntimeError):
    """A visible topology migration failure."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class Bd:
    def __init__(self, repository: Path, executable: str = "bd") -> None:
        self.repository = repository
        self.executable = executable

    def run(self, *arguments: str, check: bool = True, input_text: str | None = None) -> CommandResult:
        completed = subprocess.run(  # noqa: S603
            [self.executable, "-C", str(self.repository), *arguments],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
        result = CommandResult(completed.returncode, completed.stdout, completed.stderr)
        if check and result.returncode:
            message = result.stderr.strip() or result.stdout.strip() or "unknown bd failure"
            raise MigrationError(f"bd {' '.join(arguments)} failed: {message}")
        return result

    def json(self, *arguments: str) -> Any:
        command = arguments if "--json" in arguments else (*arguments, "--json")
        result = self.run(*command)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MigrationError(f"bd {' '.join(arguments)} returned invalid JSON") from exc


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def one_issue(value: Any, issue_id: str) -> dict[str, Any]:
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return cast(dict[str, Any], value[0])
    raise MigrationError(f"expected exactly one issue for {issue_id}")


def metadata(issue: dict[str, Any]) -> dict[str, Any]:
    value = issue.get("metadata", {})
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def children(bd: Bd, root_id: str) -> list[dict[str, Any]]:
    value = bd.json("children", root_id)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise MigrationError("bd children returned an invalid payload")
    return cast(list[dict[str, Any]], value)


def review_kind(issue: dict[str, Any]) -> str | None:
    kind = metadata(issue).get("review_kind")
    return kind if isinstance(kind, str) else None


def snapshot(bd: Bd, root_id: str) -> dict[str, Any]:
    root = one_issue(bd.json("show", root_id), root_id)
    direct = children(bd, root_id)
    return {
        "root": root,
        "children": sorted(direct, key=lambda item: str(item.get("id", ""))),
    }


def topology_projection(snapshot_value: dict[str, Any]) -> dict[str, Any]:
    root = cast(dict[str, Any], snapshot_value["root"])
    projected_children = []
    for item in cast(list[dict[str, Any]], snapshot_value["children"]):
        projected_children.append(
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "labels": sorted(item.get("labels", [])),
                "metadata": metadata(item),
                "notes": item.get("notes", ""),
                "dependencies": sorted(
                    (
                        {
                            "id": dependency.get("id") or dependency.get("depends_on_id"),
                            "type": dependency.get("dependency_type") or dependency.get("type"),
                        }
                        for dependency in item.get("dependencies", [])
                        if isinstance(dependency, dict)
                    ),
                    key=lambda value: (str(value["id"]), str(value["type"])),
                ),
            }
        )
    return {
        "root": {"id": root.get("id"), "metadata": metadata(root)},
        "children": sorted(projected_children, key=lambda item: str(item["id"])),
    }


def by_step(items: list[dict[str, Any]], step: str) -> dict[str, Any]:
    matches = [item for item in items if metadata(item).get("workflow_phase") == step]
    if step == "closeout-review":
        raise AssertionError("review lookup must use review kind")
    if len(matches) != 1:
        raise MigrationError(f"expected one {step} lifecycle issue, found {len(matches)}")
    return matches[0]


def old_reviews(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped = {kind: [item for item in items if review_kind(item) == kind] for kind in OLD_KINDS}
    invalid = {kind: len(matches) for kind, matches in grouped.items() if len(matches) != 1}
    if invalid:
        raise MigrationError(f"old topology must have exactly one review per kind: {invalid}")
    return {kind: matches[0] for kind, matches in grouped.items()}


def target_ids(root_id: str) -> dict[str, str]:
    return {kind: f"{root_id}-{kind}" for kind in TARGET_TITLES}


def derived_phase(root: dict[str, Any], items: list[dict[str, Any]]) -> str:
    if root.get("status") == "closed":
        return "delivered"
    lifecycle = {str(metadata(item).get("workflow_phase")): item for item in items}
    if lifecycle.get("delivery", {}).get("status") == "closed":
        return "delivered"
    if lifecycle.get("implementation", {}).get("status") == "closed":
        return "close-out"
    if lifecycle.get("spec-ready", {}).get("status") == "closed":
        return "implementation"
    if lifecycle.get("design", {}).get("status") in {"closed", "in_progress"}:
        return "spec-review"
    return "unstarted"


def marker_from_root(root: dict[str, Any]) -> dict[str, Any] | None:
    value = metadata(root).get("review_topology_cutover")
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise MigrationError("review_topology_cutover metadata is malformed") from exc
    if not isinstance(value, dict):
        raise MigrationError("review_topology_cutover metadata must be an object")
    return cast(dict[str, Any], value)


def plan(snapshot_value: dict[str, Any], phase: str) -> dict[str, Any]:
    if phase not in PHASES:
        raise MigrationError(f"unknown migration phase: {phase}")
    root = cast(dict[str, Any], snapshot_value["root"])
    root_id = str(root["id"])
    items = cast(list[dict[str, Any]], snapshot_value["children"])
    actual_phase = derived_phase(root, items)
    if phase != actual_phase:
        raise MigrationError(f"requested phase {phase} disagrees with graph phase {actual_phase}")
    if phase == "delivered":
        return {
            "schema": PLAN_SCHEMA,
            "root_id": root_id,
            "phase": phase,
            "snapshot_digest": digest(topology_projection(snapshot_value)),
            "applicable": False,
            "reason": "delivered features retain historical topology",
        }
    old = old_reviews(items)
    ids = target_ids(root_id)
    design = by_step(items, "design")
    spec = by_step(items, "spec-ready")
    implementation = by_step(items, "implementation")
    docs = [item for item in items if metadata(item).get("closeout_kind") == "documentation"]
    validation = [item for item in items if metadata(item).get("closeout_kind") == "validation"]
    delivery = by_step(items, "delivery")
    if len(docs) != 1 or len(validation) != 1:
        raise MigrationError("old topology must have one documentation and one validation close-out issue")
    evidence = {
        kind: {
            "issue_id": item["id"],
            "status": item.get("status"),
            "notes_digest": digest(item.get("notes", "")),
            "superseded": "review:superseded" in item.get("labels", []),
        }
        for kind, item in old.items()
    }
    result: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "root_id": root_id,
        "feature_name": metadata(root).get("feature_name") or root.get("title"),
        "phase": phase,
        "snapshot_digest": digest(topology_projection(snapshot_value)),
        "applicable": True,
        "root_metadata": json.loads(json.dumps(metadata(root))),
        "target_ids": ids,
        "old_reviews": {kind: item["id"] for kind, item in old.items()},
        "evidence_map": evidence,
        "lifecycle": {
            "design": design["id"],
            "spec_reconcile": spec["id"],
            "implementation": implementation["id"],
            "docs_reconcile": docs[0]["id"],
            "validate": validation[0]["id"],
            "delivery": delivery["id"],
        },
        "lifecycle_statuses": {
            "design": design["status"],
            "spec_reconcile": spec["status"],
            "implementation": implementation["status"],
            "docs_reconcile": docs[0]["status"],
            "validate": validation[0]["status"],
            "delivery": delivery["status"],
        },
    }
    result["plan_digest"] = digest(result)
    return result


def validate_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != PLAN_SCHEMA:
        raise MigrationError(f"plan schema must be {PLAN_SCHEMA}")
    result = cast(dict[str, Any], value)
    if result.get("applicable") is False:
        required = {"schema", "root_id", "phase", "snapshot_digest", "applicable", "reason"}
        if set(result) != required or result.get("phase") != "delivered":
            raise MigrationError(f"non-applicable plan fields are invalid: {sorted(set(result) ^ required)}")
        if not isinstance(result.get("root_id"), str) or not isinstance(result.get("reason"), str):
            raise MigrationError("non-applicable plan metadata is invalid")
        return result
    required = {
        "schema",
        "root_id",
        "feature_name",
        "phase",
        "snapshot_digest",
        "applicable",
        "root_metadata",
        "target_ids",
        "old_reviews",
        "evidence_map",
        "lifecycle",
        "lifecycle_statuses",
        "plan_digest",
    }
    if set(result) != required:
        raise MigrationError(f"plan fields are invalid: {sorted(set(result) ^ required)}")
    if result.get("phase") not in PHASES - {"delivered"} or result.get("applicable") is not True:
        raise MigrationError("apply requires an applicable non-delivered plan")
    root_id = result.get("root_id")
    if not isinstance(root_id, str) or result.get("target_ids") != target_ids(root_id):
        raise MigrationError("plan target IDs are invalid")
    for key in ("root_metadata", "old_reviews", "evidence_map", "lifecycle", "lifecycle_statuses"):
        if not isinstance(result.get(key), dict):
            raise MigrationError(f"plan {key} must be an object")
    expected_lifecycle = {"design", "spec_reconcile", "implementation", "docs_reconcile", "validate", "delivery"}
    if set(cast(dict[str, Any], result["lifecycle"])) != expected_lifecycle:
        raise MigrationError("plan lifecycle IDs are incomplete")
    if set(cast(dict[str, Any], result["lifecycle_statuses"])) != expected_lifecycle:
        raise MigrationError("plan lifecycle statuses are incomplete")
    old = cast(dict[str, Any], result["old_reviews"])
    evidence = cast(dict[str, Any], result["evidence_map"])
    if set(old) != set(OLD_KINDS) or set(evidence) != set(OLD_KINDS):
        raise MigrationError("plan old review evidence is incomplete")
    for kind in OLD_KINDS:
        if not isinstance(evidence[kind], dict) or evidence[kind].get("issue_id") != old[kind]:
            raise MigrationError(f"plan evidence map disagrees with old review: {kind}")
    payload = {key: item for key, item in result.items() if key != "plan_digest"}
    if result.get("plan_digest") != digest(payload):
        raise MigrationError("plan digest is invalid")
    return result


def verify_primary_worktree(repository: Path) -> None:
    common_root = canonical_repository_root(repository)
    if common_root != repository.resolve():
        raise MigrationError(f"migration mutations require canonical primary worktree: {common_root}")


def mapping_note(plan_value: dict[str, Any], target_kind: str) -> str:
    mapped = [kind for kind, target in TARGET_FOR_OLD.items() if target == target_kind]
    evidence = cast(dict[str, Any], plan_value["evidence_map"])
    payload = {
        "schema": "dstack.review-topology-evidence-map.v1",
        "target_kind": target_kind,
        "old_reviews": [evidence[kind] for kind in mapped],
        "approval_transferred": False,
    }
    return "Review topology evidence map: " + json.dumps(payload, sort_keys=True, separators=(",", ":"))


def target_prerequisites(plan_value: dict[str, Any], kind: str) -> list[str]:
    lifecycle = cast(dict[str, str], plan_value["lifecycle"])
    if kind in {"specification-clarity", "execution-readiness"}:
        return [lifecycle["design"]]
    return [lifecycle["docs_reconcile"], lifecycle["validate"]]


def create_target(bd: Bd, plan_value: dict[str, Any], kind: str, created: list[str]) -> None:
    ids = cast(dict[str, str], plan_value["target_ids"])
    prerequisites = target_prerequisites(plan_value, kind)
    labels = [
        "workflow:feature-lifecycle",
        "phase:spec-review" if kind in {"specification-clarity", "execution-readiness"} else "phase:closeout",
        f"review:{kind}",
    ]
    bd.run(
        "create",
        "--id",
        ids[kind],
        "--title",
        f"{TARGET_TITLES[kind]}: {plan_value['feature_name']}",
        "--type",
        "task",
        "--priority",
        "1",
        "--labels",
        ",".join(labels),
        "--metadata",
        json.dumps(
            {
                "workflow_phase": "spec-review"
                if kind in {"specification-clarity", "execution-readiness"}
                else "closeout-review",
                "review_kind": kind,
            }
        ),
        "--notes",
        mapping_note(plan_value, kind),
    )
    # Track the issue immediately so parent/dependency failures still roll it back.
    created.append(ids[kind])
    # Beads rejects combining an explicit ID with --parent. Set the parent in a
    # follow-up update while retaining deterministic target IDs.
    bd.run("update", ids[kind], "--parent", str(plan_value["root_id"]))
    for prerequisite in prerequisites:
        bd.run("dep", "add", ids[kind], prerequisite)


def command_exists(bd: Bd, issue_id: str) -> bool:
    return bd.run("show", issue_id, "--json", check=False).returncode == 0


def target_notes_match(notes: Any, expected: str) -> bool:
    """Match the immutable migration note while preserving appended Beads history."""
    return isinstance(notes, str) and (notes == expected or notes.startswith(expected + "\n"))


def target_identity_matches_plan(issue: dict[str, Any], plan_value: dict[str, Any], kind: str) -> bool:
    """Prove a target created by this migration even before parent/dependency writes finish."""
    expected_id = cast(dict[str, str], plan_value["target_ids"])[kind]
    labels = issue.get("labels", [])
    return (
        issue.get("id") == expected_id
        and metadata(issue).get("review_kind") == kind
        and f"review:{kind}" in labels
        and target_notes_match(issue.get("notes", ""), mapping_note(plan_value, kind))
    )


def target_matches_plan(issue: dict[str, Any], plan_value: dict[str, Any], kind: str) -> bool:
    return target_identity_matches_plan(issue, plan_value, kind) and issue.get("parent") == plan_value["root_id"]


def rollback(bd: Bd, plan_value: dict[str, Any], created: list[str]) -> None:
    lifecycle = cast(dict[str, str], plan_value["lifecycle"])
    old = cast(dict[str, str], plan_value["old_reviews"])
    ids = cast(dict[str, str], plan_value["target_ids"])
    for target in ids.values():
        bd.run("dep", "remove", lifecycle["spec_reconcile"], target, check=False)
        bd.run("dep", "remove", lifecycle["delivery"], target, check=False)
    for kind in ("architecture", "simplicity", "documentation", "execution"):
        issue = one_issue(bd.json("show", lifecycle["spec_reconcile"]), lifecycle["spec_reconcile"])
        if (old[kind], "blocks") not in dependency_pairs(issue):
            bd.run("dep", "add", lifecycle["spec_reconcile"], old[kind])
    for kind in ("delivery", "drift"):
        issue = one_issue(bd.json("show", lifecycle["delivery"]), lifecycle["delivery"])
        if (old[kind], "blocks") not in dependency_pairs(issue):
            bd.run("dep", "add", lifecycle["delivery"], old[kind])
    lifecycle_statuses = cast(dict[str, str], plan_value["lifecycle_statuses"])
    for step, issue_id in lifecycle.items():
        issue = one_issue(bd.json("show", issue_id), issue_id)
        if issue.get("status") != lifecycle_statuses[step]:
            bd.run("update", issue_id, "--status", lifecycle_statuses[step])
    evidence = cast(dict[str, dict[str, Any]], plan_value["evidence_map"])
    for item in evidence.values():
        issue = one_issue(bd.json("show", str(item["issue_id"])), str(item["issue_id"]))
        if issue.get("status") != item["status"]:
            bd.run("update", str(item["issue_id"]), "--status", str(item["status"]))
        superseded = bool(item.get("superseded", False))
        has_superseded = "review:superseded" in issue.get("labels", [])
        if superseded and not has_superseded:
            bd.run("update", str(item["issue_id"]), "--add-label", "review:superseded")
        elif not superseded and has_superseded:
            bd.run("update", str(item["issue_id"]), "--remove-label", "review:superseded")
    for key in (*TARGET_METADATA.values(), "review_topology_cutover"):
        old_value = cast(dict[str, Any], plan_value["root_metadata"]).get(key)
        if old_value is None:
            bd.run("update", str(plan_value["root_id"]), "--unset-metadata", key)
        else:
            restored = old_value if isinstance(old_value, str) else json.dumps(old_value)
            bd.run("update", str(plan_value["root_id"]), "--set-metadata", f"{key}={restored}")
    for issue_id in reversed(created):
        issue = one_issue(bd.json("show", issue_id), issue_id)
        kind = next(
            (name for name, value in cast(dict[str, str], plan_value["target_ids"]).items() if value == issue_id), None
        )
        if kind is None or not target_identity_matches_plan(issue, plan_value, kind):
            raise MigrationError(f"refusing to delete unproven migration target: {issue_id}")
        bd.run("delete", issue_id, "--force")


def marker(plan_value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": MARKER_SCHEMA,
        "topology_version": TOPOLOGY_VERSION,
        "root_id": plan_value["root_id"],
        "phase": plan_value["phase"],
        "plan_digest": plan_value["plan_digest"],
        "snapshot_digest": plan_value["snapshot_digest"],
        "target_ids": plan_value["target_ids"],
        "approval_transferred": False,
        "plan": json.loads(json.dumps(plan_value)),
    }


def dependency_pairs(issue: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (
            str(item.get("id") or item.get("depends_on_id")),
            str(item.get("dependency_type") or item.get("type")),
        )
        for item in issue.get("dependencies", [])
        if isinstance(item, dict)
    }


def interaction_command(repository: Path, *arguments: str) -> dict[str, Any]:
    script = Path(__file__).with_name("reconcile-beads-interactions.py")
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(script), *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip() or "interaction verification failed"
        raise MigrationError(message)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise MigrationError("interaction reconciliation returned invalid JSON") from error
    if not isinstance(result, dict):
        raise MigrationError("interaction reconciliation returned an invalid result")
    return result


def interaction_preflight(repository: Path, root_id: str) -> str:
    try:
        interaction_command(repository, "preflight", "--worktree", str(repository), "--root-id", root_id)
    except MigrationError as preflight_error:
        report = interaction_command(repository, "inspect", "--worktree", str(repository), "--root-id", root_id)
        if report.get("clean") is not False or report.get("foreign") or not report.get("selected"):
            raise preflight_error
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise MigrationError("unable to capture interaction baseline commit")
    return completed.stdout.strip()


def interaction_verify(repository: Path, root_id: str, baseline: str) -> None:
    interaction_command(
        repository,
        "verify-feature",
        "--worktree",
        str(repository),
        "--root-id",
        root_id,
        "--issue-id",
        root_id,
        "--baseline-commit",
        baseline,
        "--allow-clean",
        "--lineage-only",
    )


def verify_cutover(bd: Bd, plan_value: dict[str, Any], *, check_prerequisites: bool = True) -> dict[str, Any]:
    current = snapshot(bd, str(plan_value["root_id"]))
    root = cast(dict[str, Any], current["root"])
    found = marker_from_root(root)
    expected = marker(plan_value)
    if found != expected:
        raise MigrationError("cutover marker is absent or disagrees with the plan")
    items = cast(list[dict[str, Any]], current["children"])
    by_id = {str(item.get("id")): item for item in items}
    ids = cast(dict[str, str], plan_value["target_ids"])
    lifecycle = cast(dict[str, str], plan_value["lifecycle"])
    expected_target_status = {kind: {"open", "in_progress", "closed"} for kind in TARGET_TITLES}
    for kind, issue_id in ids.items():
        item = by_id.get(issue_id)
        if item is None or not target_matches_plan(item, plan_value, kind):
            raise MigrationError(f"cutover target does not match plan: {issue_id}")
        if item.get("status") not in expected_target_status[kind]:
            raise MigrationError(f"cutover target status is invalid: {issue_id}")
    if check_prerequisites:
        for kind, issue_id in ids.items():
            item = by_id[issue_id]
            target_edges = dependency_pairs(item)
            for prerequisite in target_prerequisites(plan_value, kind):
                if (prerequisite, "blocks") not in target_edges:
                    raise MigrationError(f"target prerequisite edge is missing: {kind}")
                if (issue_id, "blocks") in dependency_pairs(by_id[prerequisite]):
                    raise MigrationError(f"target prerequisite edge is reversed: {kind}")
    root_metadata = metadata(root)
    for kind, issue_id in ids.items():
        if root_metadata.get(TARGET_METADATA[kind]) != issue_id:
            raise MigrationError(f"root review ID is invalid: {kind}")
    spec = by_id[lifecycle["spec_reconcile"]]
    delivery = by_id[lifecycle["delivery"]]
    spec_edges = dependency_pairs(spec)
    delivery_edges = dependency_pairs(delivery)
    old = cast(dict[str, str], plan_value["old_reviews"])
    for kind in ("specification-clarity", "execution-readiness"):
        if (ids[kind], "blocks") not in spec_edges:
            raise MigrationError(f"specification edge is missing: {kind}")
    for kind in ("implementation-integrity", "delivery-integrity"):
        if (ids[kind], "blocks") not in delivery_edges:
            raise MigrationError(f"delivery edge is missing: {kind}")
    if any(
        (old[kind], "blocks") in spec_edges for kind in ("architecture", "simplicity", "documentation", "execution")
    ):
        raise MigrationError("obsolete specification edge remains")
    if any((old[kind], "blocks") in delivery_edges for kind in ("delivery", "drift")):
        raise MigrationError("obsolete delivery edge remains")
    for kind, issue_id in old.items():
        item = by_id[issue_id]
        if item.get("status") != "closed" or "review:superseded" not in item.get("labels", []):
            raise MigrationError(f"old review is not superseded: {issue_id}")
        evidence = cast(dict[str, Any], plan_value["evidence_map"])[kind]
        if evidence["issue_id"] != issue_id:
            raise MigrationError(f"old evidence mapping is invalid: {issue_id}")
    return {"schema": MARKER_SCHEMA, "status": "verified", "marker": found}


def repair_reversed_prerequisite_edges(bd: Bd, plan_value: dict[str, Any]) -> None:
    """Repair the pre-versioned migration's reversed prerequisite edges."""
    verify_cutover(bd, plan_value, check_prerequisites=False)
    current = snapshot(bd, str(plan_value["root_id"]))
    by_id = {str(item.get("id")): item for item in cast(list[dict[str, Any]], current["children"])}
    ids = cast(dict[str, str], plan_value["target_ids"])
    for kind, issue_id in ids.items():
        target_edges = dependency_pairs(by_id[issue_id])
        for prerequisite in target_prerequisites(plan_value, kind):
            expected = (prerequisite, "blocks") in target_edges
            reversed_edge = (issue_id, "blocks") in dependency_pairs(by_id[prerequisite])
            if expected and not reversed_edge:
                continue
            if not reversed_edge:
                bd.run("dep", "add", issue_id, prerequisite)
                continue
            bd.run("dep", "remove", prerequisite, issue_id)
            try:
                bd.run("dep", "add", issue_id, prerequisite)
            except MigrationError:
                bd.run("dep", "add", prerequisite, issue_id)
                raise


def apply(
    repository: Path, plan_value: dict[str, Any], bd_executable: str, lock_dir: Path | None, fail_after: int | None
) -> dict[str, Any]:
    if not plan_value.get("applicable", False):
        return {"schema": MARKER_SCHEMA, "status": "not_applicable", "reason": plan_value.get("reason")}
    verify_primary_worktree(repository)
    bd = Bd(repository, bd_executable)
    created: list[str] = []
    operations = 0

    def checkpoint() -> None:
        nonlocal operations
        operations += 1
        if fail_after is not None and operations >= fail_after:
            raise MigrationError(f"injected migration failure after operation {operations}")

    interaction_baseline = ""
    try:
        with WorkflowLock(repository, lock_dir=lock_dir, run_id=f"review-topology:{plan_value['root_id']}"):
            interaction_baseline = interaction_preflight(repository, str(plan_value["root_id"]))
            current = snapshot(bd, str(plan_value["root_id"]))
            existing = marker_from_root(cast(dict[str, Any], current["root"]))
            if existing is not None:
                try:
                    return verify_cutover(bd, plan_value)
                except MigrationError:
                    repair_reversed_prerequisite_edges(bd, plan_value)
                    result = verify_cutover(bd, plan_value)
                    interaction_verify(repository, str(plan_value["root_id"]), interaction_baseline)
                    return result
            if digest(topology_projection(current)) == plan_value["snapshot_digest"]:
                canonical_plan = plan(current, str(plan_value["phase"]))
                if canonical_plan != plan_value:
                    raise MigrationError("plan does not match the current topology snapshot")
            root_before = cast(dict[str, Any], current["root"])
            target_values = cast(dict[str, str], plan_value["target_ids"])
            partial_targets: list[str] = []
            for kind, issue_id in target_values.items():
                if not command_exists(bd, issue_id):
                    continue
                candidate = one_issue(bd.json("show", issue_id), issue_id)
                if not target_identity_matches_plan(candidate, plan_value, kind):
                    raise MigrationError(f"target issue ID collides with unrelated work: {issue_id}")
                partial_targets.append(issue_id)
            partial_root = any(
                key in metadata(root_before) for key in (*TARGET_METADATA.values(), "review_topology_cutover")
            )
            if partial_targets or partial_root:
                rollback(bd, plan_value, partial_targets)
                current = snapshot(bd, str(plan_value["root_id"]))
                root_before = cast(dict[str, Any], current["root"])
            if digest(topology_projection(current)) != plan_value["snapshot_digest"]:
                raise MigrationError("topology snapshot changed after planning")
            try:
                for kind in TARGET_TITLES:
                    issue_id = cast(dict[str, str], plan_value["target_ids"])[kind]
                    if command_exists(bd, issue_id):
                        raise MigrationError(f"target issue already exists without cutover marker: {issue_id}")
                    create_target(bd, plan_value, kind, created)
                    checkpoint()
                lifecycle = cast(dict[str, str], plan_value["lifecycle"])
                old = cast(dict[str, str], plan_value["old_reviews"])
                ids = cast(dict[str, str], plan_value["target_ids"])
                for kind in ("specification-clarity", "execution-readiness"):
                    bd.run("dep", "add", lifecycle["spec_reconcile"], ids[kind])
                for kind in ("implementation-integrity", "delivery-integrity"):
                    bd.run("dep", "add", lifecycle["delivery"], ids[kind])
                for kind in ("architecture", "simplicity", "documentation", "execution"):
                    bd.run("dep", "remove", lifecycle["spec_reconcile"], old[kind])
                for kind in ("delivery", "drift"):
                    bd.run("dep", "remove", lifecycle["delivery"], old[kind])
                checkpoint()
                evidence = cast(dict[str, dict[str, Any]], plan_value["evidence_map"])
                for item in evidence.values():
                    bd.run("update", str(item["issue_id"]), "--status", "closed", "--add-label", "review:superseded")
                if plan_value["phase"] == "implementation":
                    bd.run("reopen", lifecycle["spec_reconcile"])
                if plan_value["phase"] == "close-out":
                    for kind in ("specification-clarity", "execution-readiness"):
                        bd.run(
                            "close",
                            ids[kind],
                            "--reason",
                            "Migration after specification completion; no approval transferred",
                        )
                checkpoint()
                for kind in TARGET_TITLES:
                    bd.run(
                        "update",
                        str(plan_value["root_id"]),
                        "--set-metadata",
                        f"{TARGET_METADATA[kind]}={ids[kind]}",
                    )
                    checkpoint()
                bd.run(
                    "update",
                    str(plan_value["root_id"]),
                    "--set-metadata",
                    "review_topology_cutover=" + json.dumps(marker(plan_value), sort_keys=True, separators=(",", ":")),
                )
                checkpoint()
                result = verify_cutover(bd, plan_value)
                interaction_verify(repository, str(plan_value["root_id"]), interaction_baseline)
            except Exception as error:
                rollback(bd, plan_value, created)
                interaction_verify(repository, str(plan_value["root_id"]), interaction_baseline)
                rolled_back = snapshot(bd, str(plan_value["root_id"]))
                if digest(topology_projection(rolled_back)) != plan_value["snapshot_digest"]:
                    message = f"rollback did not restore the planned topology snapshot after: {error}"
                    raise MigrationError(message) from None
                raise
    except WorkflowLockError as exc:
        raise MigrationError(str(exc)) from exc
    return result


def load_json(path: Path | None) -> Any:
    if path is None or str(path) == "-":
        return json.load(sys.stdin)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(value: object, path: Path | None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None or str(path) == "-":
        sys.stdout.write(text)
    else:
        path.write_text(text, encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repository-root", type=Path, default=Path.cwd())
    result.add_argument("--bd", default="bd")
    result.add_argument("--lock-dir", type=Path)
    commands = result.add_subparsers(dest="command", required=True)
    create = commands.add_parser("plan")
    create.add_argument("--root-id", required=True)
    create.add_argument("--phase", choices=sorted(PHASES), required=True)
    create.add_argument("--output", type=Path)
    execute = commands.add_parser("apply")
    execute.add_argument("--plan", type=Path)
    execute.add_argument("--fail-after", type=int, help=argparse.SUPPRESS)
    verify = commands.add_parser("verify")
    verify.add_argument("--plan", type=Path)
    guard = commands.add_parser("guard")
    guard.add_argument("--root-id", required=True)
    guard.add_argument("--controller-topology-version", type=int, required=True)
    return result


def fail(message: str) -> NoReturn:
    print(json.dumps({"schema": ERROR_SCHEMA, "error": message}, sort_keys=True))
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repository = args.repository_root.expanduser().resolve()
    bd = Bd(repository, args.bd)
    try:
        if args.command == "plan":
            result = plan(snapshot(bd, args.root_id), args.phase)
            write_json(result, args.output)
            return 0
        if args.command == "apply":
            plan_value = validate_plan(load_json(args.plan))
            result = apply(repository, plan_value, args.bd, args.lock_dir, args.fail_after)
            write_json(result, None)
            return 0
        if args.command == "verify":
            plan_value = validate_plan(load_json(args.plan))
            if not plan_value.get("applicable", False):
                write_json(
                    {"schema": MARKER_SCHEMA, "status": "not_applicable", "reason": plan_value.get("reason")}, None
                )
                return 0
            write_json(verify_cutover(bd, plan_value), None)
            return 0
        current = snapshot(bd, args.root_id)
        root = cast(dict[str, Any], current["root"])
        found = marker_from_root(root)
        if found is None:
            kinds = {review_kind(item) for item in cast(list[dict[str, Any]], current["children"])}
            if kinds & set(OLD_KINDS):
                raise MigrationError("feature uses unmigrated old review topology")
            if kinds & set(TARGET_TITLES) and args.controller_topology_version < TOPOLOGY_VERSION:
                raise MigrationError("installed controller predates the markerless review topology")
        else:
            if args.controller_topology_version < int(found.get("topology_version", 0)):
                raise MigrationError("installed controller predates the feature's review-topology cutover")
            embedded = found.get("plan")
            plan_value = validate_plan(embedded)
            verify_cutover(bd, plan_value)
        write_json({"schema": MARKER_SCHEMA, "status": "compatible", "marker": found}, None)
        return 0
    except (OSError, json.JSONDecodeError, MigrationError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
