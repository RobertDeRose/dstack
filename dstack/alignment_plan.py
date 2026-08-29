"""Canonical project-alignment plan identity and authorization predicates."""

from __future__ import annotations

import hashlib
import json
import re
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
    root_metadata_value,
)

SCHEMA = "dstack.alignment-plan/v2"
LEGACY_SCHEMA = "dstack.alignment-plan/v1"
PLAN_FIELDS = {
    "schema",
    "scope",
    "findings",
    "accepted_corrections",
    "rejected_corrections",
    "validation_expectations",
    "documentation_impact",
    "deferred_findings",
    "accepted_risks",
}
LEGACY_PLAN_FIELDS = PLAN_FIELDS | {"baseline_commit"}
BASELINE_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DstackError(f"alignment plan field {field!r} must be a non-empty string")
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def _strings(values: Any, field: str) -> list[str]:
    if not isinstance(values, list):
        raise DstackError(f"alignment plan field {field!r} must be an array")
    return sorted({_text(value, f"{field}[]") for value in values})


def _title_objects(values: Any, field: str, keys: set[str]) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        raise DstackError(f"alignment plan field {field!r} must be an array")
    result: list[dict[str, Any]] = []
    titles: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, dict) or set(value) != keys:
            raise DstackError(f"{field}[{index}] has the wrong fields")
        title = _text(value.get("title"), f"{field}[{index}].title")
        if title in titles:
            raise DstackError(f"duplicate correction title: {title}")
        titles.add(title)
        item = {key: value[key] for key in keys}
        item["title"] = title
        result.append(item)
    return result


def canonicalize_plan(value: Any, *, allow_legacy: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DstackError("alignment plan must be a JSON object")
    schema = value.get("schema")
    legacy = schema == LEGACY_SCHEMA
    expected_fields = LEGACY_PLAN_FIELDS if legacy and allow_legacy else PLAN_FIELDS
    if set(value) != expected_fields:
        missing = sorted(expected_fields - set(value))
        unknown = sorted(set(value) - expected_fields)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown {', '.join(unknown)}")
        raise DstackError("invalid alignment plan fields: " + "; ".join(detail))
    if schema != SCHEMA and not (legacy and allow_legacy):
        raise DstackError(f"alignment plan schema must be {SCHEMA}")
    baseline = None
    if legacy:
        baseline = _text(value["baseline_commit"], "baseline_commit").lower()
        if not BASELINE_RE.fullmatch(baseline):
            raise DstackError("baseline_commit must be a full Git commit ID")
    scope = _text(value["scope"], "scope")
    findings = _title_objects(value["findings"], "findings", {"title", "evidence", "rationale"})
    for item in findings:
        item["evidence"] = _text(item["evidence"], "findings.evidence")
        item["rationale"] = _text(item["rationale"], "findings.rationale")
    accepted = _title_objects(
        value["accepted_corrections"],
        "accepted_corrections",
        {"title", "description", "acceptance", "priority", "depends_on"},
    )
    titles = {item["title"] for item in accepted}
    for item in accepted:
        item["description"] = _text(item["description"], "accepted_corrections.description")
        item["acceptance"] = _text(item["acceptance"], "accepted_corrections.acceptance")
        priority = item["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise DstackError("accepted correction priority must be an integer")
        deps = _strings(item["depends_on"], "accepted_corrections.depends_on")
        if any(dep not in titles for dep in deps):
            raise DstackError("accepted correction depends_on references an unknown title")
        item["depends_on"] = deps
    # Detect dependency cycles with a small title-local DFS.
    graph = {item["title"]: set(item["depends_on"]) for item in accepted}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise DstackError("accepted correction dependencies contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    rejected = _title_objects(value["rejected_corrections"], "rejected_corrections", {"title", "rationale"})
    deferred = _title_objects(value["deferred_findings"], "deferred_findings", {"title", "rationale"})
    risks = _title_objects(value["accepted_risks"], "accepted_risks", {"title", "rationale"})
    for collection in (rejected, deferred, risks):
        for item in collection:
            item["rationale"] = _text(item["rationale"], "rationale")
    impact = value["documentation_impact"]
    if not isinstance(impact, dict) or set(impact) != {
        "end_user_operator",
        "developer_reviewer",
        "future_auditor",
    }:
        raise DstackError("documentation_impact must contain exactly the three audience fields")
    impact = {key: _strings(impact[key], f"documentation_impact.{key}") for key in impact}
    result = {
        "schema": schema,
        "scope": scope,
        "findings": sorted(findings, key=lambda item: item["title"]),
        "accepted_corrections": sorted(accepted, key=lambda item: item["title"]),
        "rejected_corrections": sorted(rejected, key=lambda item: item["title"]),
        "validation_expectations": _strings(value["validation_expectations"], "validation_expectations"),
        "documentation_impact": impact,
        "deferred_findings": sorted(deferred, key=lambda item: item["title"]),
        "accepted_risks": sorted(risks, key=lambda item: item["title"]),
    }
    if legacy:
        result["baseline_commit"] = baseline
    return result


def canonical_plan_bytes(value: Any) -> bytes:
    return json.dumps(
        canonicalize_plan(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def plan_digest(value: Any) -> str:
    return hashlib.sha256(canonical_plan_bytes(value)).hexdigest()


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DstackError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_plan_file(path: Path) -> tuple[dict[str, Any], bytes, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DstackError(f"invalid alignment plan JSON: {path}") from exc
    canonical = canonicalize_plan(value)
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    return canonical, encoded, hashlib.sha256(encoded).hexdigest()


def root_plan_metadata(client: BeadsClient, root_id: str) -> tuple[str | None, str | None]:
    root = client.show(root_id)
    return (
        root_metadata_value(root, "dstack.pending_alignment_plan_sha256"),
        root_metadata_value(root, "dstack.approved_alignment_plan_sha256"),
    )


def _relationship_signature(record: Mapping[str, Any]) -> tuple[str, str]:
    relation = str(record.get("type") or record.get("dependency_type") or "blocks")
    target = record.get("depends_on_id") or record.get("id")
    if not isinstance(target, str) or not target:
        raise DstackError(f"alignment correction graph has an invalid {relation} relationship")
    return relation, target


def _expected_relationships(
    *,
    correction_parent: str,
    approval_id: str,
    internal_ids: set[str],
) -> list[tuple[str, str]]:
    return [
        ("parent-child", correction_parent),
        ("blocks", approval_id),
        *(("blocks", item_id) for item_id in sorted(internal_ids)),
    ]


def verify_correction_graph(client: BeadsClient, view: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    approval = client.show(str(view["steps"]["approval"]["id"]))
    corrections = client.children(str(view["steps"]["corrections"]["id"]))
    expected = {item["title"]: item for item in plan["accepted_corrections"]}
    actual = list(corrections)
    if any(not has_label(item, "dstack:work:correction") for item in actual):
        raise DstackError("alignment correction graph contains an unlabelled child")
    if len(actual) != len(expected) or {str(item.get("title")) for item in actual} != set(expected):
        raise DstackError("alignment correction set does not match the approved plan")
    by_title = {str(item["title"]): item for item in actual}
    for title, spec in expected.items():
        item = by_title[title]
        actual_description = unicodedata.normalize(
            "NFC", str(item.get("description") or "").replace("\r\n", "\n").replace("\r", "\n")
        )
        actual_acceptance = unicodedata.normalize(
            "NFC",
            str(item.get("acceptance_criteria") or item.get("acceptance") or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n"),
        )
        if (
            actual_description != spec["description"]
            or actual_acceptance != spec["acceptance"]
            or item.get("priority") != spec["priority"]
            or issue_parent(item) != str(view["steps"]["corrections"]["id"])
            or not has_label(item, "dstack:work:correction")
        ):
            raise DstackError(f"alignment correction content changed: {title}")
        expected_internal = {str(by_title[dep_title]["id"]) for dep_title in spec["depends_on"]}
        expected_relationships = _expected_relationships(
            correction_parent=str(view["steps"]["corrections"]["id"]),
            approval_id=str(approval["id"]),
            internal_ids=expected_internal,
        )
        try:
            actual_relationships = [_relationship_signature(record) for record in dependency_records(item)]
        except DstackError as exc:
            raise DstackError(f"alignment correction graph changed: {title}: {exc}") from exc
        if Counter(actual_relationships) != Counter(expected_relationships):
            raise DstackError(
                f"alignment correction graph changed: {title}; "
                f"expected={sorted(expected_relationships)!r}, "
                f"observed={sorted(actual_relationships)!r}"
            )


def canonical_description(analysis: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    raw = analysis.get("description")
    if not isinstance(raw, str) or not raw.strip():
        raise DstackError("alignment analysis has no canonical plan description")
    try:
        value = json.loads(raw, object_pairs_hook=_object_pairs)
    except json.JSONDecodeError as exc:
        raise DstackError("alignment analysis description is not canonical JSON") from exc
    canonical = canonicalize_plan(value, allow_legacy=True)
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    if raw != encoded.decode("utf-8"):
        raise DstackError("alignment analysis description is not canonical plan JSON")
    return canonical, encoded.decode("utf-8"), hashlib.sha256(encoded).hexdigest()


def require_current_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema") != SCHEMA:
        raise DstackError("legacy alignment plan requires re-review before execution")


def require_alignment_authorized(client: BeadsClient, view: Mapping[str, Any]) -> dict[str, Any]:
    analysis = client.show(str(view["steps"]["analysis"]["id"]))
    plan, _, digest = canonical_description(analysis)
    require_current_plan(plan)
    pending, approved = root_plan_metadata(client, str(view["root"]["id"]))
    gate = view.get("human_gate")
    if not isinstance(gate, Mapping):
        from .core import human_gate_for_step

        gate = human_gate_for_step(client, root_id=str(view["root"]["id"]), step=view["steps"]["approval"])
    if (
        analysis.get("status") != "closed"
        or view["steps"]["approval"].get("status") != "closed"
        or not gate
        or gate.get("status") != "closed"
    ):
        raise DstackError("alignment authorization is not closed")
    if pending or approved != digest:
        raise DstackError("alignment plan authorization identity does not match")
    verify_correction_graph(client, view, plan)
    return plan
