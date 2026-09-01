"""Live Beads-native project-alignment authorization checks."""

from __future__ import annotations

import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .core import (
    ALIGNMENT_STEPS,
    BeadsClient,
    DstackError,
    dependency_records,
    has_label,
    human_gate_for_step,
    issue_parent,
    issue_type,
)


def normalize_summary(value: Any, *, field: str = "alignment review summary") -> str:
    if not isinstance(value, str):
        raise DstackError(f"{field} must be a non-empty string")
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not normalized:
        raise DstackError(f"{field} must be a non-empty string")
    return normalized


def read_summary_file(path: Path) -> str:
    try:
        return normalize_summary(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot read alignment review summary: {path}") from exc


def _relationship_signature(record: Mapping[str, Any]) -> tuple[str, str]:
    relation = record.get("type") or record.get("dependency_type")
    target = record.get("depends_on_id") or record.get("id")
    if not isinstance(relation, str) or not relation.strip():
        raise DstackError("alignment correction graph has a relationship without a type")
    if not isinstance(target, str) or not target.strip():
        raise DstackError(f"alignment correction graph has an invalid {relation!r} relationship")
    return relation.strip(), target.strip()


def _live_steps(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    root = view.get("root")
    steps = view.get("steps")
    if not isinstance(root, Mapping) or not isinstance(steps, Mapping):
        raise DstackError("alignment view has no root or stable steps")
    root_id = str(root.get("id") or "")
    if not root_id:
        raise DstackError("alignment root has no ID")

    expected_types = {
        "analysis": "task",
        "approval": "task",
        "corrections": "epic",
        "landing": "task",
    }
    result: dict[str, dict[str, Any]] = {}
    for name, label in ALIGNMENT_STEPS.items():
        candidate = steps.get(name)
        if not isinstance(candidate, Mapping) or not candidate.get("id"):
            raise DstackError(f"alignment view lacks {name} step")
        issue = client.show(str(candidate["id"]))
        issue_id = str(issue["id"])
        if issue_parent(issue) != root_id:
            raise DstackError(f"alignment {name} step is not a direct child of {root_id}: {issue_id}")
        if not has_label(issue, label):
            raise DstackError(f"alignment {name} step lacks required label {label}: {issue_id}")
        if issue_type(issue) != expected_types[name]:
            raise DstackError(
                f"alignment {name} step has invalid type {issue_type(issue)!r}; expected {expected_types[name]!r}"
            )
        result[name] = issue
    return result


def correction_graph(
    client: BeadsClient,
    view: Mapping[str, Any],
    *,
    steps: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    live_steps = dict(steps) if steps is not None else _live_steps(client, view)
    approval_id = str(live_steps["approval"]["id"])
    corrections_id = str(live_steps["corrections"]["id"])

    summaries = list(client.children(corrections_id))
    ids = [str(item.get("id") or "") for item in summaries]
    if "" in ids or len(set(ids)) != len(ids):
        raise DstackError("alignment correction graph has missing or duplicate issue IDs")
    items = [client.show(issue_id) for issue_id in ids]
    titles = [normalize_summary(item.get("title"), field="alignment correction title") for item in items]

    result: list[dict[str, Any]] = []
    for item, title in zip(items, titles, strict=True):
        item_id = str(item["id"])
        if issue_parent(item) != corrections_id or not has_label(item, "dstack:work:correction"):
            raise DstackError(f"alignment correction is outside the native correction workstream: {item_id}")
        if issue_type(item) not in {"task", "bug", "chore"}:
            raise DstackError(f"alignment correction is not executable work: {item_id}")
        priority = item.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise DstackError(f"alignment correction has invalid priority: {item_id}")
        description = normalize_summary(item.get("description"), field=f"correction {item_id} description")
        acceptance = normalize_summary(
            item.get("acceptance_criteria") or item.get("acceptance"),
            field=f"correction {item_id} acceptance criteria",
        )
        relationships = [_relationship_signature(record) for record in dependency_records(item)]
        if Counter(relationships)[("blocks", approval_id)] != 1:
            raise DstackError(f"alignment correction does not have exactly one approval blocker: {item_id}")
        if len(set(relationships)) != len(relationships):
            raise DstackError(f"alignment correction has duplicate relationships: {item_id}")
        for relation, target in relationships:
            if relation == "parent-child" and target != corrections_id:
                raise DstackError(f"alignment correction has conflicting parent relationship: {item_id}")
            if relation == "blocks" and target in ids and target == item_id:
                raise DstackError(f"alignment correction blocks itself: {item_id}")
        result.append(
            {
                "id": item_id,
                "type": issue_type(item),
                "title": title,
                "description": description,
                "acceptance": acceptance,
                "priority": priority,
                "parent": corrections_id,
                "status": item.get("status"),
                "relationships": [{"type": relation, "target": target} for relation, target in sorted(relationships)],
            }
        )
    return sorted(result, key=lambda item: item["id"])


def require_alignment_authorized(
    client: BeadsClient,
    view: Mapping[str, Any],
    *,
    allow_closed_root: bool = False,
) -> dict[str, Any]:
    root = view.get("root")
    if not isinstance(root, Mapping):
        raise DstackError("alignment view has no root")
    root_id = str(root.get("id") or "")
    live_root = client.show(root_id)
    root_status = live_root.get("status")
    if root_status != "open" and not (allow_closed_root and root_status == "closed"):
        suffix = " and is inspect-only" if root_status == "closed" else ""
        raise DstackError(f"alignment root must be open{suffix}: status={root_status!r}")

    steps = _live_steps(client, {**view, "root": live_root})
    summary = normalize_summary(steps["analysis"].get("description"))
    gate = human_gate_for_step(client, root_id=root_id, step=steps["approval"])
    if (
        steps["analysis"].get("status") != "closed"
        or steps["approval"].get("status") != "closed"
        or not gate
        or gate.get("status") != "closed"
    ):
        raise DstackError("alignment authorization is not closed")
    corrections = correction_graph(client, {**view, "root": live_root, "steps": steps}, steps=steps)
    return {"summary": summary, "corrections": corrections, "human_gate": gate, "steps": steps}
