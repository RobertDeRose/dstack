"""Pure closed-world planning for explicit legacy workflow adoption.

This module only reads Beads/Git and returns an in-memory plan.  Native
creation, relationship changes, and supersession belong to the adoption apply
boundary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from dstack_commands import descendants, reject_documentation_work
from dstacklib import (
    DstackError,
    FEATURE_STEPS,
    dependency_records,
    BeadsClient,
    canonical_feature_design_path,
    commit_footer_ids,
    feature_slug,
    issue_type,
    validate_git_revision,
)

SCHEMA = "dstack.adoption-classification/v1"
PLAN_SCHEMA = "dstack.adoption-plan/v1"
CLASSIFICATIONS = frozenset(
    {
        "completed-history",
        "remaining-implementation",
        "obsolete-specification-ceremony",
        "obsolete-implementation-ceremony",
        "obsolete-closeout-delivery-ceremony",
        "unresolved-decision",
        "preserved-unchanged",
    }
)
EVIDENCE_KINDS = frozenset({"git-footer", "source", "test", "documentation"})
STRATEGIES = frozenset({"reparent", "recreate", "keep-legacy-root"})
RELATIONS = frozenset(
    {
        "blocks",
        "relates-to",
        "parent-child",
        "superseded-by",
        "supersedes",
        "duplicates",
    }
)
_EXECUTABLE_TYPES = frozenset({"task", "bug", "chore"})
_SUPPORTED_ISSUE_TYPES = frozenset({"task", "bug", "feature", "epic", "molecule", "gate", "chore", "message"})
_DESIGN_SECTION = re.compile(r"^(?P<path>[^#]+)#(?P<heading>[^#]+)$")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DstackError(f"{name} must be an object")
    return dict(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DstackError(f"{name} must be a nonempty string")
    return value.strip()


def _nullable_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _exact_fields(value: Mapping[str, Any], required: set[str], name: str) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required)
    if missing or unknown:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise DstackError(f"invalid {name} fields: {'; '.join(detail)}")


def _safe_path(root: Path, value: Any, name: str) -> str:
    path = _text(value, name)
    if "\\" in path or any(char in path for char in "\r\n\0") or path.startswith("/") or Path(path).is_absolute():
        raise DstackError(f"{name} must be a repository-relative POSIX path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DstackError(f"{name} is not normalized")
    candidate = (root / Path(*parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise DstackError(f"{name} escapes the repository") from exc
    return "/".join(parts)


def _replacement(value: Any, name: str) -> dict[str, Any]:
    replacement = _object(value, name)
    _exact_fields(replacement, {"title", "description", "acceptance", "priority"}, name)
    title = _text(replacement["title"], f"{name}.title")
    description = _text(replacement["description"], f"{name}.description")
    acceptance = _text(replacement["acceptance"], f"{name}.acceptance")
    priority = replacement["priority"]
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise DstackError(f"{name}.priority must be an integer")
    if priority < 0:
        raise DstackError(f"{name}.priority must not be negative")
    return {
        "title": title,
        "description": description,
        "acceptance": acceptance,
        "priority": priority,
    }


def _evidence(root: Path, legacy_id: str, value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise DstackError(f"entry {legacy_id} evidence must be a nonempty array")
    result: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        record = _object(raw, f"entry {legacy_id} evidence[{index}]")
        _exact_fields(record, {"kind", "reference", "explanation"}, "evidence")
        kind = _text(record["kind"], "evidence.kind")
        if kind not in EVIDENCE_KINDS:
            raise DstackError(f"unknown evidence kind: {kind}")
        reference = record["reference"]
        explanation = _text(record["explanation"], "evidence.explanation")
        if kind == "git-footer":
            reference = validate_git_revision(root, _text(reference, "evidence.reference"), name="evidence ref")
            commits = commit_footer_ids(root, reference).get(legacy_id, [])
            if not commits:
                raise DstackError(f"git-footer evidence for {legacy_id} is not reachable from {reference}")
        else:
            reference = _safe_path(root, reference, "evidence.reference")
            path = root / Path(*reference.split("/"))
            if not path.is_file() or path.is_symlink():
                raise DstackError(f"evidence path is not a regular file: {reference}")
        result.append({"kind": kind, "reference": str(reference), "explanation": explanation})
    ordered = sorted(result, key=lambda item: (item["kind"], item["reference"], item["explanation"]))
    if result != ordered:
        raise DstackError(f"evidence for {legacy_id} must be sorted")
    return result


def _section(root: Path, value: Any, design_path: str | None) -> str:
    section = _text(value, "specification_section")
    match = _DESIGN_SECTION.fullmatch(section)
    if not match:
        raise DstackError("specification_section must be path#heading")
    path = _safe_path(root, match.group("path"), "specification_section path")
    if design_path is not None and path != design_path:
        raise DstackError(f"specification_section path must be {design_path}")
    if design_path is None and not re.fullmatch(r"docs/src/features/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?/design\.md", path):
        raise DstackError("specification_section path must be canonical target design")
    heading = _text(match.group("heading"), "specification_section heading")
    content_path = root / Path(*path.split("/"))
    if not content_path.is_file() or content_path.is_symlink():
        raise DstackError(f"specification_section file is missing: {path}")
    lines = content_path.read_text(encoding="utf-8").splitlines()
    wanted = heading.casefold()
    found = False
    substantive: list[str] = []
    for line in lines:
        if line.startswith("#"):
            current = line.lstrip("#").strip().casefold()
            if found:
                break
            found = current == wanted
            continue
        if found and line.strip() and not line.lstrip().startswith("<!--"):
            substantive.append(line.strip())
    if not found or not substantive:
        raise DstackError("specification_section heading has no substantive content")
    return f"{path}#{heading}"


def canonicalize_classification(
    value: Any,
    *,
    root: Path,
    legacy_root_id: str,
    design_path: str | None = None,
) -> dict[str, Any]:
    payload = _object(value, "adoption classification")
    _exact_fields(payload, {"schema", "legacy_root_id", "entries"}, "adoption classification")
    if payload["schema"] != SCHEMA:
        raise DstackError(f"adoption classification schema must be {SCHEMA}")
    if _text(payload["legacy_root_id"], "legacy_root_id") != legacy_root_id:
        raise DstackError("classification legacy_root_id does not match selected root")
    entries = payload["entries"]
    if not isinstance(entries, list):
        raise DstackError("classification entries must be an array")
    result: list[dict[str, Any]] = []
    previous: str | None = None
    for index, raw in enumerate(entries):
        entry = _object(raw, f"entries[{index}]")
        legacy_id = _text(entry.get("legacy_id"), f"entries[{index}].legacy_id")
        if previous is not None and legacy_id <= previous:
            raise DstackError("classification entries must be sorted and unique")
        previous = legacy_id
        classification = _text(entry.get("classification"), f"entry {legacy_id}.classification")
        if classification not in CLASSIFICATIONS:
            raise DstackError(f"unknown classification: {classification}")
        reason = _text(entry.get("reason"), f"entry {legacy_id}.reason")
        fields = {"legacy_id", "classification", "reason"}
        normalized: dict[str, Any] = {
            "legacy_id": legacy_id,
            "classification": classification,
            "reason": reason,
        }
        if classification == "completed-history":
            fields |= {"evidence", "evidence_assessment", "accepted_risk_reason"}
            _exact_fields(entry, fields, f"entry {legacy_id}")
            assessment = _text(entry["evidence_assessment"], "evidence_assessment")
            if assessment not in {"verified", "accepted-risk"}:
                raise DstackError(f"invalid evidence assessment for {legacy_id}")
            risk = entry["accepted_risk_reason"]
            if assessment == "verified" and risk is not None:
                raise DstackError(f"verified history {legacy_id} must have null accepted_risk_reason")
            if assessment == "accepted-risk":
                risk = _text(risk, "accepted_risk_reason")
            normalized.update(
                evidence=_evidence(root, legacy_id, entry["evidence"]),
                evidence_assessment=assessment,
                accepted_risk_reason=risk,
            )
        elif classification == "remaining-implementation":
            fields.add("replacement")
            _exact_fields(entry, fields, f"entry {legacy_id}")
            normalized["replacement"] = _replacement(entry["replacement"], f"entry {legacy_id}.replacement")
        elif classification == "unresolved-decision":
            fields |= {"strategy", "specification_section", "blocking_target"}
            _exact_fields(entry, fields, f"entry {legacy_id}")
            strategy = _text(entry["strategy"], "strategy")
            if strategy not in {"incorporated", "preserve-blocker"}:
                raise DstackError(f"invalid unresolved-decision strategy for {legacy_id}")
            section = entry["specification_section"]
            blocking = entry["blocking_target"]
            if strategy == "incorporated":
                section = _section(root, section, design_path)
                if blocking is not None:
                    raise DstackError(f"incorporated decision {legacy_id} must have null blocking_target")
            else:
                if section is not None:
                    raise DstackError(f"preserved decision {legacy_id} must have null specification_section")
                blocking = _text(blocking, "blocking_target")
                valid_targets = set(FEATURE_STEPS) | set(FEATURE_STEPS.values())
                if blocking not in valid_targets:
                    raise DstackError(f"unsupported blocking_target for {legacy_id}")
            normalized.update(strategy=strategy, specification_section=section, blocking_target=blocking)
        elif classification == "preserved-unchanged":
            fields |= {"strategy", "surviving_parent", "replacement"}
            _exact_fields(entry, fields, f"entry {legacy_id}")
            strategy = _text(entry["strategy"], "strategy")
            if strategy not in STRATEGIES:
                raise DstackError(f"invalid preserved strategy for {legacy_id}")
            surviving = entry["surviving_parent"]
            replacement = entry["replacement"]
            if strategy == "reparent":
                surviving = _text(surviving, "surviving_parent")
                if replacement is not None:
                    raise DstackError(f"reparented work {legacy_id} must have null replacement")
            elif strategy == "recreate":
                if surviving is not None:
                    raise DstackError(f"recreated work {legacy_id} must have null surviving_parent")
                replacement = _replacement(replacement, f"entry {legacy_id}.replacement")
            elif surviving is not None or replacement is not None:
                raise DstackError(f"keep-legacy-root work {legacy_id} must use null strategy fields")
            normalized.update(strategy=strategy, surviving_parent=surviving, replacement=replacement)
        else:
            _exact_fields(entry, fields, f"entry {legacy_id}")
        result.append(normalized)
    return {"schema": SCHEMA, "legacy_root_id": legacy_root_id, "entries": result}


def _compatible_root_step(source_kind: str, target_kind: str, *, outgoing: bool) -> str:
    if outgoing:
        if target_kind in {"task", "bug", "chore", "gate"}:
            return "approval"
        if target_kind == "epic":
            return "implementation"
    elif source_kind in {"task", "bug", "chore"}:
        return "closeout"
    elif source_kind == "epic":
        return "implementation"
    raise DstackError(f"no compatible native lifecycle step for root graph edge ({source_kind} -> {target_kind})")


def _validate_relation_compatibility(
    source_id: str,
    target_id: str,
    relation: str,
    issues: Mapping[str, Mapping[str, Any]],
    *,
    legacy_root_id: str,
) -> None:
    source = issues.get(source_id)
    target = issues.get(target_id)
    if source is None or target is None:
        return
    source_kind = issue_type(source)
    target_kind = issue_type(target)
    if not source_kind or not target_kind or not source.get("status") or not target.get("status"):
        raise DstackError(f"relationship endpoint lacks native status/type: {source_id} -> {target_id}")
    if relation == "blocks" and source_id != legacy_root_id and target_id != legacy_root_id:
        compatible_gate = source_kind in _EXECUTABLE_TYPES and target_kind == "gate"
        if source_kind != target_kind and not compatible_gate:
            raise DstackError(
                f"incompatible blocks relationship: {source_id} ({source_kind}) -> {target_id} ({target_kind})"
            )
    if relation == "parent-child" and target_kind not in {"epic", "molecule", "feature"}:
        raise DstackError(f"parent-child target is not a container: {target_id}")


def _relation(record: Mapping[str, Any]) -> tuple[str, str] | None:
    target = record.get("depends_on_id") or record.get("id")
    if not isinstance(target, str) or not target:
        return None
    relation = str(record.get("type") or record.get("dependency_type") or "blocks")
    return target, relation


def _replacement_ref(entry: Mapping[str, Any]) -> str | None:
    classification = entry["classification"]
    if classification in {"remaining-implementation", "preserved-unchanged"}:
        if classification == "remaining-implementation":
            return str(entry["legacy_id"])
        if entry.get("strategy") == "recreate":
            return str(entry["legacy_id"])
    return None


_SNAPSHOT_ISSUE_FIELDS = (
    "id",
    "status",
    "issue_type",
    "type",
    "parent",
    "parent_id",
    "assignee",
    "labels",
    "priority",
    "title",
    "description",
    "acceptance_criteria",
    "metadata",
    "gate_ids",
    "dependencies",
)


def _snapshot_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    return {key: issue[key] for key in _SNAPSHOT_ISSUE_FIELDS if key in issue}


def adoption_graph_snapshot(client: BeadsClient, legacy_root_id: str) -> dict[str, Any]:
    """Read the legacy graph from native authorities for drift reconciliation."""
    root = client.show(legacy_root_id)
    child_records = descendants(client, legacy_root_id)
    legacy_records = [dict(root), *[dict(item) for item in child_records]]
    raw_ids = [item.get("id") for item in legacy_records]
    legacy_ids = {str(item_id) for item_id in raw_ids if item_id}
    if any(not item_id for item_id in raw_ids) or len(legacy_ids) != len(legacy_records):
        raise DstackError("legacy graph snapshot contains duplicate or missing IDs")
    all_records = [*client.list(all_statuses=True), *client.gates(all_statuses=True)]
    all_issues: dict[str, dict[str, Any]] = {}
    for item in all_records:
        item_id = item.get("id")
        if not item_id:
            continue
        key = str(item_id)
        if key in all_issues and all_issues[key] != dict(item):
            raise DstackError(f"native graph snapshot has conflicting issue records: {key}")
        all_issues[key] = dict(item)
    for item in legacy_records:
        all_issues[str(item["id"])] = item

    internal: list[dict[str, str]] = []
    outgoing: list[dict[str, str]] = []
    incoming: list[dict[str, str]] = []
    for source_id, issue in sorted(((str(item["id"]), item) for item in legacy_records), key=lambda pair: pair[0]):
        for record in dependency_records(issue):
            target = record.get("depends_on_id") or record.get("id")
            if not isinstance(target, str) or not target:
                raise DstackError(f"legacy graph snapshot has invalid edge: {source_id}")
            relation = str(record.get("type") or record.get("dependency_type") or "blocks")
            edge = {
                "source_id": source_id,
                "target_id": target,
                "relationship_type": relation,
            }
            (internal if target in legacy_ids else outgoing).append(edge)
            if target not in legacy_ids and target not in all_issues:
                raise DstackError(f"legacy graph snapshot points to unknown issue: {target}")
    for source_id, issue in sorted(all_issues.items()):
        if source_id in legacy_ids:
            continue
        for record in dependency_records(issue):
            target = record.get("depends_on_id") or record.get("id")
            if not isinstance(target, str) or not target:
                raise DstackError(f"native graph snapshot has invalid edge: {source_id}")
            if target not in legacy_ids:
                continue
            incoming.append(
                {
                    "source_id": source_id,
                    "target_id": target,
                    "relationship_type": str(record.get("type") or record.get("dependency_type") or "blocks"),
                }
            )
    for edges in (internal, outgoing, incoming):
        edges.sort(key=lambda item: (item["source_id"], item["target_id"], item["relationship_type"]))
    return {
        "legacy_root_id": legacy_root_id,
        "legacy_ids": sorted(legacy_ids),
        "legacy_records": sorted(
            (_snapshot_issue(item) for item in legacy_records),
            key=lambda item: str(item["id"]),
        ),
        "internal": internal,
        "outgoing_external": outgoing,
        "incoming_external": incoming,
    }


def adoption_graph_signature(
    snapshot: Mapping[str, Any],
    *,
    ignored_edges: set[tuple[str, str, str]] | frozenset[tuple[str, str, str]] = frozenset(),
    ignored_ids: set[str] | frozenset[str] = frozenset(),
) -> str:
    """Canonicalize a snapshot while ignoring only explicitly expected native edges."""
    value = {
        "legacy_root_id": snapshot.get("legacy_root_id"),
        "legacy_ids": sorted(str(item) for item in snapshot.get("legacy_ids", []) if str(item) not in ignored_ids),
    }
    for name in ("internal", "outgoing_external", "incoming_external"):
        value[name] = [
            dict(edge)
            for edge in snapshot.get(name, [])
            if (
                str(edge.get("source_id")) not in ignored_ids
                and str(edge.get("target_id")) not in ignored_ids
                and (
                    str(edge.get("source_id")),
                    str(edge.get("target_id")),
                    str(edge.get("relationship_type")),
                )
                not in ignored_edges
            )
        ]
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def reconcile_adoption_graph(
    client: BeadsClient,
    expected: Mapping[str, Any],
    legacy_root_id: str,
    *,
    ignored_edges: set[tuple[str, str, str]] | frozenset[tuple[str, str, str]] = frozenset(),
    ignored_ids: set[str] | frozenset[str] = frozenset(),
) -> None:
    actual = adoption_graph_snapshot(client, legacy_root_id)
    if adoption_graph_signature(
        expected, ignored_edges=ignored_edges, ignored_ids=ignored_ids
    ) != adoption_graph_signature(actual, ignored_edges=ignored_edges, ignored_ids=ignored_ids):
        raise DstackError("legacy adoption graph drifted; no destructive mutation is safe")


def adoption_plan_graph_matches(plan: Mapping[str, Any], snapshot: Mapping[str, Any]) -> bool:
    inventory = plan.get("inventory")
    if not isinstance(inventory, Mapping):
        return False
    if sorted(str(item) for item in inventory.get("legacy_ids", [])) != sorted(
        str(item) for item in snapshot.get("legacy_ids", [])
    ):
        return False
    for key in ("internal", "outgoing_external", "incoming_external"):
        if inventory.get(key, []) != snapshot.get(key, []):
            return False
    return True


def plan_adoption(
    client: BeadsClient,
    legacy_root_id: str,
    classification: Mapping[str, Any],
    *,
    target_root: Mapping[str, Any] | None = None,
    target_design_path: str | None = None,
) -> dict[str, Any]:
    """Validate classification and return a deterministic, mutation-free plan."""
    legacy = client.show(legacy_root_id)
    if legacy.get("status") == "closed":
        raise DstackError("cannot plan adoption for a closed legacy root")
    all_descendants = descendants(client, legacy_root_id)
    for item in all_descendants:
        if not item.get("status") or not issue_type(item):
            raise DstackError(f"legacy descendant {item.get('id', '<unknown>')} lacks native status/type")
    by_id = {str(item["id"]): dict(item) for item in all_descendants}
    if len(by_id) != len(all_descendants):
        raise DstackError("legacy descendant inventory contains duplicate IDs")
    target_design = target_design_path or (
        str(target_root.get("design_path")) if target_root and target_root.get("design_path") else None
    )
    target_slug = feature_slug(target_root) if target_root is not None else None
    if target_slug is None and target_design:
        match = re.fullmatch(r"docs/src/features/([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)/design\.md", target_design)
        target_slug = match.group(1) if match else None
    if target_slug is None:
        target_slug = feature_slug(legacy)
    if target_design is None and target_slug:
        target_design = canonical_feature_design_path(target_slug)
    raw_entries = classification.get("entries") if isinstance(classification, Mapping) else None
    if (
        any(
            isinstance(item, Mapping)
            and item.get("classification") == "unresolved-decision"
            and item.get("strategy") == "incorporated"
            for item in (raw_entries if isinstance(raw_entries, list) else [])
        )
        and target_design is None
    ):
        raise DstackError("incorporated decisions require a canonical target design path")
    if target_root is not None and target_design is not None and not target_slug:
        raise DstackError("target feature has no canonical slug for its design path")
    if target_slug and target_design != canonical_feature_design_path(target_slug):
        raise DstackError("target design path is not canonical for the feature slug")
    entries = canonicalize_classification(
        classification,
        root=client.root,
        legacy_root_id=legacy_root_id,
        design_path=target_design,
    )["entries"]
    executable = sorted(
        item_id
        for item_id, item in by_id.items()
        if item.get("status") not in {"closed", "deferred"} and issue_type(item) in _EXECUTABLE_TYPES
    )
    entry_ids = [str(item["legacy_id"]) for item in entries]
    if len(set(entry_ids)) != len(entry_ids):
        raise DstackError("classification contains duplicate legacy IDs")
    unknown = sorted(set(entry_ids) - set(by_id))
    missing = sorted(set(executable) - set(entry_ids))
    if unknown:
        raise DstackError("classification contains foreign IDs: " + ", ".join(unknown))
    if missing:
        raise DstackError("classification omits open executable descendants: " + ", ".join(missing))
    if target_root is not None:
        target_id = str(target_root.get("id") or "")
        if not target_id:
            raise DstackError("target feature root has no ID")
        target_children = client.children(target_id)
        steps = {
            str(label): str(item["id"])
            for item in target_children
            for label in item.get("labels", [])
            if str(label) in FEATURE_STEPS.values()
        }
    else:
        steps = {}
    issues = {legacy_root_id: dict(legacy), **by_id}
    all_records = list(client.list(all_statuses=True))
    all_records.extend(client.gates(all_statuses=True))
    all_issues = {str(item["id"]): dict(item) for item in all_records if item.get("id")}
    for item_id, item in {**all_issues, **issues}.items():
        kind = issue_type(item)
        if kind and kind not in _SUPPORTED_ISSUE_TYPES:
            raise DstackError(f"unsupported issue type for {item_id}: {kind}")
    all_issues.update(issues)
    for entry in entries:
        if entry["classification"] != "preserved-unchanged" or entry["strategy"] != "reparent":
            continue
        parent_id = str(entry["surviving_parent"])
        if parent_id in by_id or parent_id == legacy_root_id:
            raise DstackError(f"surviving_parent remains inside the legacy root: {parent_id}")
        parent = all_issues.get(parent_id)
        if parent is None:
            raise DstackError(f"surviving_parent is not a known issue: {parent_id}")
        if parent.get("status") in {"closed", "deferred"}:
            raise DstackError(f"surviving_parent is not open: {parent_id}")
        if issue_type(parent) not in {"epic", "molecule"}:
            raise DstackError(f"surviving_parent is not an open container: {parent_id}")
    for entry in entries:
        if entry["classification"] != "unresolved-decision":
            continue
        old_kind = issue_type(by_id.get(str(entry["legacy_id"]), {}))
        if entry["strategy"] == "incorporated":
            target_kind = "task"
        else:
            target_name = str(entry["blocking_target"])
            target_key = FEATURE_STEPS.get(target_name, target_name)
            target_kind = "epic" if target_key == FEATURE_STEPS["implementation"] else "task"
        if old_kind and old_kind != target_kind:
            raise DstackError(f"decision blocker is incompatible with target step: {entry['legacy_id']}")
    internal = set(issues)
    internal_edges: list[dict[str, Any]] = []
    outgoing: list[dict[str, Any]] = []
    incoming: list[dict[str, Any]] = []
    for source_id, issue in sorted(issues.items()):
        for record in dependency_records(issue):
            pair = _relation(record)
            if pair is None:
                raise DstackError(f"invalid relationship record on {source_id}")
            target_id, relation = pair
            if relation not in RELATIONS:
                raise DstackError(f"unsupported relationship type: {relation}")
            if target_id in internal:
                _validate_relation_compatibility(
                    source_id,
                    target_id,
                    relation,
                    all_issues,
                    legacy_root_id=legacy_root_id,
                )
                internal_edges.append({"source_id": source_id, "target_id": target_id, "relationship_type": relation})
            else:
                if target_id not in all_issues:
                    raise DstackError(f"relationship points to unknown issue: {target_id}")
                _validate_relation_compatibility(
                    source_id,
                    target_id,
                    relation,
                    all_issues,
                    legacy_root_id=legacy_root_id,
                )
                outgoing.append({"source_id": source_id, "target_id": target_id, "relationship_type": relation})
    for source_id, issue in sorted(all_issues.items()):
        if source_id in internal:
            continue
        for record in dependency_records(issue):
            pair = _relation(record)
            if pair is None:
                raise DstackError(f"invalid relationship record on {source_id}")
            target_id, relation = pair
            if relation not in RELATIONS:
                raise DstackError(f"unsupported relationship type: {relation}")
            if target_id in internal:
                _validate_relation_compatibility(
                    source_id,
                    target_id,
                    relation,
                    all_issues,
                    legacy_root_id=legacy_root_id,
                )
                incoming.append({"source_id": source_id, "target_id": target_id, "relationship_type": relation})
    for collection in (internal_edges, outgoing, incoming):
        collection.sort(key=lambda item: (item["source_id"], item["target_id"], item["relationship_type"]))
    entry_by_id = {str(item["legacy_id"]): item for item in entries}
    replacements: list[dict[str, Any]] = []
    for item_id in executable:
        entry = entry_by_id[item_id]
        ref = _replacement_ref(entry)
        if ref is None:
            continue
        replacement = entry.get("replacement")
        if replacement is None:
            continue
        reject_documentation_work(replacement["title"], stage="implementation")
        parent_id = steps.get(FEATURE_STEPS["implementation"])
        approval_id = steps.get(FEATURE_STEPS["approval"])
        replacements.append(
            {
                "legacy_id": item_id,
                "source_type": issue_type(by_id[item_id]),
                "action": "create-or-reuse",
                "replacement": dict(replacement),
                "parent_id": parent_id,
                "parent_step": FEATURE_STEPS["implementation"],
                "labels": ["dstack:work:implementation"],
                "approval_blocker": approval_id,
                "approval_step": FEATURE_STEPS["approval"],
            }
        )
    replacements.sort(key=lambda item: item["legacy_id"])
    decision_staging: list[dict[str, Any]] = []
    for entry in entries:
        if entry["classification"] != "unresolved-decision":
            continue
        if entry["strategy"] == "incorporated":
            decision_staging.append(
                {
                    "legacy_id": entry["legacy_id"],
                    "action": "incorporate-after-approval",
                    "specification_section": entry["specification_section"],
                    "target_step": steps.get(FEATURE_STEPS["specification"]),
                    "preserve_legacy_root": True,
                }
            )
        else:
            decision_staging.append(
                {
                    "legacy_id": entry["legacy_id"],
                    "action": "preserve-blocker",
                    "blocking_target": entry["blocking_target"],
                    "target_step": steps.get(FEATURE_STEPS.get(entry["blocking_target"], entry["blocking_target"])),
                    "preserve_legacy_root": True,
                }
            )
    decision_staging.sort(key=lambda item: item["legacy_id"])
    supersedable = not any(
        entry["classification"] == "unresolved-decision"
        or (entry["classification"] == "preserved-unchanged" and entry["strategy"] == "keep-legacy-root")
        for entry in entries
    )
    operations: list[dict[str, Any]] = []
    for edge in internal_edges + outgoing + incoming:
        source_internal = edge["source_id"] in internal
        owner = edge["source_id"] if source_internal else edge["target_id"]
        entry = entry_by_id.get(owner)
        decision = "preserve"
        target_step = None
        if edge["relationship_type"] in {"superseded-by", "supersedes"}:
            decision = "preserve-native-supersession"
        elif owner == legacy_root_id and edge["relationship_type"] == "blocks":
            if edge["source_id"] == legacy_root_id:
                target_step = _compatible_root_step(
                    issue_type(all_issues[edge["source_id"]]),
                    issue_type(all_issues[edge["target_id"]]),
                    outgoing=True,
                )
            else:
                target_step = _compatible_root_step(
                    issue_type(all_issues[edge["source_id"]]),
                    issue_type(all_issues[edge["target_id"]]),
                    outgoing=False,
                )
            if target_step is not None:
                # Outgoing root blockers transfer during the initial pass; only
                # incoming dependents wait for root supersession authorization.
                decision = "redirect" if edge["source_id"] == legacy_root_id or supersedable else "deferred-redirect"
        elif entry and entry["classification"] in {
            "obsolete-specification-ceremony",
            "obsolete-implementation-ceremony",
            "obsolete-closeout-delivery-ceremony",
        }:
            decision = "lifecycle-only"
        elif entry and _replacement_ref(entry):
            decision = "redirect"
        source_ref = _replacement_ref(entry_by_id[edge["source_id"]]) if edge["source_id"] in entry_by_id else None
        target_ref = _replacement_ref(entry_by_id[edge["target_id"]]) if edge["target_id"] in entry_by_id else None
        if edge["target_id"] == legacy_root_id and decision == "redirect" and target_step is None:
            source_kind = issue_type(all_issues[edge["source_id"]])
            target_step = "closeout" if source_kind in {"task", "bug", "chore"} else "implementation"
        operations.append(
            {
                **edge,
                "decision": decision,
                "source_replacement_for": source_ref,
                "target_replacement_for": target_ref,
                "target_step": target_step,
                "ordering": "add-before-remove" if decision in {"redirect", "deferred-redirect"} else "none",
                "add_before_remove": decision in {"redirect", "deferred-redirect"},
            }
        )
    operations.sort(
        key=lambda item: (
            item["source_id"],
            item["target_id"],
            item["relationship_type"],
            item["decision"],
        )
    )
    return {
        "schema": PLAN_SCHEMA,
        "legacy_root_id": legacy_root_id,
        "entries": entries,
        "inventory": {
            "legacy_ids": sorted(issues),
            "open_executable_descendants": executable,
            "closed_history": sorted(item_id for item_id, item in by_id.items() if item.get("status") == "closed"),
            "internal": internal_edges,
            "outgoing_external": outgoing,
            "incoming_external": incoming,
        },
        "replacements": replacements,
        "decision_staging": decision_staging,
        "relationship_operations": operations,
        "supersession": {
            "eligible": bool(supersedable),
            "requires": ["replacements", "relationships", "readiness", "reachability"],
        },
        "postconditions": [
            "replacement content, parent, labels, and approval blockers converge",
            "replacement relationships are added before obsolete edges are removed",
            "all affected external issues are reread before supersession",
            "preserved executable work remains reachable and ready when appropriate",
        ],
    }


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DstackError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_classification_file(
    path: Path,
    *,
    root: Path,
    legacy_root_id: str,
    design_path: str | None = None,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_json_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DstackError(f"invalid adoption classification JSON: {path}") from exc
    return canonicalize_classification(value, root=root, legacy_root_id=legacy_root_id, design_path=design_path)
