"""dStack feature identity and native Beads graph invariants."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .beads import (
    BeadsClient,
    dependency_targets,
    has_label,
    issue_labels,
    issue_parent,
    issue_type,
    metadata_value,
    step_by_label,
)
from .core import DstackError

FEATURE_STEP_TYPES = {
    "plan": "task",
    "review": "task",
    "approval": "task",
    "implementation": "epic",
    "audit": "task",
}
FEATURE_STEP_LABELS = {step: f"dstack:step:{step}" for step in FEATURE_STEP_TYPES}


def find_feature_root(client: BeadsClient, selector: str) -> dict[str, Any]:
    current = client.show(selector)
    seen: set[str] = set()
    while True:
        issue_id = str(current["id"])
        if issue_id in seen:
            raise DstackError(f"parent cycle while resolving feature root from {selector}")
        seen.add(issue_id)
        if issue_type(current) == "molecule" or has_label(current, "workflow:feature"):
            return current
        parent = issue_parent(current)
        if parent is None:
            raise DstackError(f"Bead {selector} is not inside a feature molecule")
        current = client.show(parent)


def feature_steps(client: BeadsClient, root_id: str) -> dict[str, dict[str, Any]]:
    children = client.children(root_id)
    steps = {name: step_by_label(children, label) for name, label in FEATURE_STEP_LABELS.items()}
    for name, expected_type in FEATURE_STEP_TYPES.items():
        if issue_type(steps[name]) != expected_type:
            raise DstackError(f"{name} step must be a {expected_type}")
    return steps


def feature_identity(client: BeadsClient, selector: str) -> tuple[dict[str, Any], str, str]:
    root = find_feature_root(client, selector)
    labels = issue_labels(root)
    slugs = sorted({label.removeprefix("feature:") for label in labels if label.startswith("feature:")})
    if len(slugs) != 1 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slugs[0]):
        raise DstackError(f"feature root {root['id']} must have exactly one valid feature:<slug> label")
    slug = slugs[0]

    base = metadata_value(root, "dstack.base_branch")
    if not base:
        raise DstackError(f"feature root {root['id']} lacks dstack.base_branch metadata")
    return root, slug, base


def implementation_task_graph_errors(task: Mapping[str, Any], steps: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Validate native graph membership without calculating task readiness."""

    errors: list[str] = []
    task_id = str(task.get("id") or "")
    implementation_id = str(steps["implementation"].get("id") or "")
    approval_id = str(steps["approval"].get("id") or "")

    parent_id = issue_parent(task)
    if parent_id != implementation_id:
        observed_parent = parent_id or "<none>"
        errors.append(
            f"implementation Bead must be a direct child of {implementation_id}; observed parent {observed_parent}"
        )
    implementation = steps["implementation"]
    if issue_type(implementation) != "epic":
        errors.append("feature implementation step is not an epic")
    if has_label(task, "dstack:step:implementation"):
        errors.append("implementation task inherited the structural dstack:step:implementation label")

    blockers = dependency_targets(task, "blocks")
    if approval_id not in blockers:
        errors.append(f"implementation Bead is not blocked by approval step {approval_id}")

    # Native Beads validates blocker existence, cross-feature relationships,
    # conditional dependencies, and readiness. Do not reconstruct that graph.

    if not task_id:
        errors.append("implementation Bead has no ID")
    return errors


def close_completion_dependency_errors(
    close_step: Mapping[str, Any],
    implementation_tasks: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Verify persistent Beads blockers from every implementation task to close."""

    errors: list[str] = []
    task_ids = {str(task.get("id") or "") for task in implementation_tasks if task.get("id")}
    blockers = set(dependency_targets(close_step, "blocks"))
    missing = sorted(task_ids - blockers)
    if missing:
        errors.append(
            "close step must be directly blocked by every implementation task; missing blockers: " + ", ".join(missing)
        )

    return errors


def implementation_tasks(client: BeadsClient, implementation_id: str) -> list[dict[str, Any]]:
    children = sorted(
        (
            child
            for child in client.children(implementation_id)
            if issue_type(child) not in {"epic", "molecule", "gate"}
        ),
        key=lambda child: str(child["id"]),
    )
    return client.show_many([str(child["id"]) for child in children])
