"""Beads-native project-alignment review authority.

Alignment corrections and their relationships live in Beads.  The analysis
step stores only the human review summary.  dStack derives a compact canonical
authority digest from those two sources; no external JSON packet is part of the
workflow contract.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .core import (
    BeadsClient,
    DstackError,
    dependency_records,
    has_label,
    issue_parent,
    issue_type,
    root_metadata_value,
)

SCHEMA = "dstack.alignment-review/v1"
_PENDING_KEY = "dstack.pending_alignment_review_sha256"
_APPROVED_KEY = "dstack.approved_alignment_review_sha256"


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


def root_plan_metadata(client: BeadsClient, root_id: str) -> tuple[str | None, str | None]:
    root = client.show(root_id)
    return (
        root_metadata_value(root, _PENDING_KEY),
        root_metadata_value(root, _APPROVED_KEY),
    )


def _relationship_signature(record: Mapping[str, Any]) -> tuple[str, str]:
    relation = record.get("type") or record.get("dependency_type")
    target = record.get("depends_on_id") or record.get("id")
    if not isinstance(relation, str) or not relation.strip():
        raise DstackError("alignment correction graph has a relationship without a type")
    if not isinstance(target, str) or not target.strip():
        raise DstackError(f"alignment correction graph has an invalid {relation!r} relationship")
    return relation.strip(), target.strip()


def correction_graph(client: BeadsClient, view: Mapping[str, Any]) -> list[dict[str, Any]]:
    steps = view.get("steps")
    if not isinstance(steps, Mapping):
        raise DstackError("alignment view has no steps")
    approval = steps.get("approval")
    corrections = steps.get("corrections")
    if not isinstance(approval, Mapping) or not isinstance(corrections, Mapping):
        raise DstackError("alignment view lacks approval or correction steps")
    approval_id = str(approval.get("id") or "")
    corrections_id = str(corrections.get("id") or "")
    if not approval_id or not corrections_id:
        raise DstackError("alignment approval or correction step has no ID")

    items = list(client.children(corrections_id))
    ids = {str(item.get("id") or "") for item in items}
    if "" in ids or len(ids) != len(items):
        raise DstackError("alignment correction graph has missing or duplicate issue IDs")
    titles = [normalize_summary(item.get("title"), field="alignment correction title") for item in items]
    if len(set(titles)) != len(titles):
        raise DstackError("alignment correction graph has duplicate titles")

    result: list[dict[str, Any]] = []
    for item, title in zip(items, titles, strict=True):
        item_id = str(item["id"])
        if issue_parent(item) != corrections_id or not has_label(item, "dstack:work:correction"):
            raise DstackError(f"alignment correction is outside the native correction workstream: {item_id}")
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
                "relationships": [{"type": relation, "target": target} for relation, target in sorted(relationships)],
            }
        )
    return sorted(result, key=lambda item: item["id"])


def canonical_authority(
    client: BeadsClient,
    view: Mapping[str, Any],
    summary: str,
) -> tuple[dict[str, Any], bytes, str]:
    payload = {
        "schema": SCHEMA,
        "summary": normalize_summary(summary),
        "corrections": correction_graph(client, view),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return payload, encoded, hashlib.sha256(encoded).hexdigest()


def canonical_description(
    client: BeadsClient,
    view: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str]:
    summary = normalize_summary(analysis.get("description"))
    payload, _, digest = canonical_authority(client, view, summary)
    return payload, summary, digest


def verify_correction_graph(
    client: BeadsClient,
    view: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> None:
    expected = authority.get("corrections")
    if not isinstance(expected, list) or expected != correction_graph(client, view):
        raise DstackError("alignment correction graph changed after review")


def require_alignment_authorized(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    steps = view.get("steps")
    if not isinstance(steps, Mapping):
        raise DstackError("alignment view has no steps")
    analysis = client.show(str(steps["analysis"]["id"]))
    authority, _, digest = canonical_description(client, view, analysis)
    pending, approved = root_plan_metadata(client, str(view["root"]["id"]))
    gate = view.get("human_gate")
    if not isinstance(gate, Mapping):
        from .core import human_gate_for_step

        gate = human_gate_for_step(client, root_id=str(view["root"]["id"]), step=steps["approval"])
    if (
        analysis.get("status") != "closed"
        or steps["approval"].get("status") != "closed"
        or not gate
        or gate.get("status") != "closed"
    ):
        raise DstackError("alignment authorization is not closed")
    if pending or approved != digest:
        raise DstackError("alignment review authorization identity does not match current Beads state")
    return authority
