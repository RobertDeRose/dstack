"""Native execution boundary for a previously validated adoption plan."""

from __future__ import annotations

from typing import Any, Mapping

from .adoption import (
    EXECUTABLE_REPLACEMENT_TYPES,
    PLAN_SCHEMA,
    RELATIONS,
    _section,
    adoption_native_inventory,
    reconcile_adoption_graph,
)
from .commands import descendants, reject_documentation_work, superseded_target
from .core import (
    BeadsClient,
    DstackError,
    FEATURE_STEPS,
    as_items,
    dependency_records,
    feature_authorization_state,
    feature_design_state,
    worktree_for_branch,
    has_label,
    human_gate_for_step,
    issue_parent,
    issue_type,
    step_by_label,
)

_CEREMONY_TARGETS = {
    "obsolete-specification-ceremony": "specification",
    "obsolete-implementation-ceremony": "implementation",
    "obsolete-closeout-delivery-ceremony": "closeout",
}


def _edge(issue: Mapping[str, Any], target: str, relation: str) -> bool:
    for record in dependency_records(issue):
        depends_on = record.get("depends_on_id") or record.get("id")
        current = str(record.get("type") or record.get("dependency_type") or "blocks")
        if str(depends_on) == target and current == relation:
            return True
    return False


def _require_endpoint(client: BeadsClient, issue_id: str) -> dict[str, Any]:
    issue = client.show(issue_id)
    if not issue.get("status") or issue.get("assignee") not in (None, "") or not issue_type(issue):
        raise DstackError(f"adoption relationship endpoint drifted: {issue_id}")
    return issue


def _ensure_edge(client: BeadsClient, source: str, target: str, relation: str) -> None:
    if relation not in RELATIONS:
        raise DstackError(f"unsupported relationship type: {relation}")
    source_issue = client.show(source)
    target_issue = client.show(target)
    if _edge(source_issue, target, relation):
        return
    if source_issue.get("status") in {"closed", "deferred"} or target_issue.get("status") in {
        "closed",
        "deferred",
    }:
        raise DstackError(f"cannot add relationship to terminal issue: {source} -> {target}")
    if source_issue.get("assignee") not in (None, "") or target_issue.get("assignee") not in (
        None,
        "",
    ):
        raise DstackError(f"cannot add relationship to assigned issue: {source} -> {target}")
    if not issue_type(source_issue) or not issue_type(target_issue):
        raise DstackError(f"relationship endpoint has no native type: {source} -> {target}")
    if not _edge(source_issue, target, relation):
        client.add_dependency(source, target, relation_type=relation)
    if not _edge(client.show(source), target, relation):
        raise DstackError(f"relationship did not converge: {source} -> {target} ({relation})")


def _remove_edge(client: BeadsClient, source: str, target: str) -> None:
    source_issue = _require_endpoint(client, source)
    if not _edge(source_issue, target, "blocks") and not any(
        str(record.get("depends_on_id") or record.get("id")) == target
        for record in dependency_records(client.show(source))
    ):
        return
    client.remove_dependency(source, target)
    if any(
        str(record.get("depends_on_id") or record.get("id")) == target
        for record in dependency_records(client.show(source))
    ):
        raise DstackError(f"relationship did not remove: {source} -> {target}")


def _ready_ids(client: BeadsClient) -> set[str] | None:
    query = getattr(client, "json", None)
    if query is None:
        return None
    payload = query(["bd", "ready", "--limit", "0", "--json"])
    return {str(item["id"]) for item in as_items(payload, context="bd ready during adoption")}


def _assert_not_ready(client: BeadsClient, issue_ids: set[str], *, phase: str) -> None:
    if not issue_ids:
        return
    ready = _ready_ids(client)
    if ready is None:
        return
    unexpected = sorted(issue_ids & ready)
    if unexpected:
        raise DstackError(f"external dependent became ready during adoption ({phase}): " + ", ".join(unexpected))


def _validate_legacy_parentage_before_destructive_actions(
    client: BeadsClient,
    plan: Mapping[str, Any],
    expected_graph: Mapping[str, Any],
) -> None:
    entries = {
        str(entry.get("legacy_id")): entry
        for entry in plan.get("entries", [])
        if isinstance(entry, Mapping) and entry.get("legacy_id")
    }
    for raw in expected_graph.get("legacy_records", []):
        if not isinstance(raw, Mapping) or not raw.get("id"):
            continue
        issue_id = str(raw["id"])
        actual = client.show(issue_id)
        if superseded_target(actual):
            # Prior partial supersession is validated separately against its
            # exact intended replacement/lifecycle target. Beads may detach its
            # parent projection as part of that native transition.
            continue
        entry = entries.get(issue_id)
        if entry and entry.get("classification") == "preserved-unchanged" and entry.get("strategy") == "reparent":
            expected_parent = str(entry.get("surviving_parent") or "") or None
        else:
            expected_parent = issue_parent(raw)
        if issue_parent(actual) != expected_parent:
            raise DstackError(f"adoption legacy parentage drifted before destructive mutation: {issue_id}")


def _assert_legacy_generation_boundary(
    client: BeadsClient,
    plan: Mapping[str, Any],
    expected_graph: Mapping[str, Any],
    *,
    legacy_root_id: str,
    replacement_ids: Mapping[str, str],
    view: Mapping[str, Any],
) -> None:
    """Fail closed if native topology appeared outside the planned generation."""

    legacy_ids = {str(item) for item in expected_graph.get("legacy_ids", [])}
    unexpected_descendants = sorted(
        str(item.get("id")) for item in descendants(client, legacy_root_id) if str(item.get("id")) not in legacy_ids
    )
    if unexpected_descendants:
        raise DstackError(
            "adoption graph generation drifted; unexpected legacy descendants: " + ", ".join(unexpected_descendants)
        )

    allowed_external: set[tuple[str, str, str]] = set()
    for key in ("outgoing_external", "incoming_external"):
        for edge in expected_graph.get(key, []):
            if not isinstance(edge, Mapping):
                continue
            relation = str(edge.get("relationship_type") or "")
            if relation in RELATIONS:
                allowed_external.add((str(edge.get("source_id")), str(edge.get("target_id")), relation))
    for legacy_id, replacement_id in replacement_ids.items():
        allowed_external.add((str(legacy_id), str(replacement_id), "relates-to"))
    for staged in plan.get("decision_staging", []):
        if not isinstance(staged, Mapping) or staged.get("action") != "preserve-blocker":
            continue
        legacy_id = str(staged.get("legacy_id") or "")
        name = str(staged.get("blocking_target") or "")
        if name in FEATURE_STEPS:
            source = _step_id(view, name)
        elif name in FEATURE_STEPS.values():
            source = _step_id(view, next(key for key, label in FEATURE_STEPS.items() if label == name))
        else:
            source = name
        allowed_external.add((source, legacy_id, "blocks"))

    inventory = adoption_native_inventory(client)
    observed_external: set[tuple[str, str, str]] = set()
    for source_id, issue in inventory.items():
        for record in dependency_records(issue):
            target = record.get("depends_on_id") or record.get("id")
            relation = str(record.get("type") or record.get("dependency_type") or "blocks")
            if not isinstance(target, str) or relation not in RELATIONS:
                continue
            if (source_id in legacy_ids) == (target in legacy_ids):
                continue
            observed_external.add((source_id, target, relation))
    unexpected_edges = sorted(observed_external - allowed_external)
    if unexpected_edges:
        rendered = ", ".join(f"{source}->{target}({relation})" for source, target, relation in unexpected_edges)
        raise DstackError("adoption graph generation drifted; unexpected external relationships: " + rendered)


def _incoming_dependent_ids(plan: Mapping[str, Any]) -> set[str]:
    inventory = plan.get("inventory")
    operations = plan.get("relationship_operations")
    if not isinstance(inventory, Mapping) or not isinstance(operations, list):
        return set()
    incoming = {
        (str(edge["source_id"]), str(edge["target_id"]))
        for edge in inventory.get("incoming_external", [])
        if isinstance(edge, Mapping) and edge.get("relationship_type") == "blocks"
    }
    return {
        source
        for source, target in incoming
        if any(
            isinstance(operation, Mapping)
            and operation.get("decision") in {"redirect", "deferred-redirect", "lifecycle-only"}
            and operation.get("relationship_type") == "blocks"
            and str(operation.get("source_id")) == source
            and str(operation.get("target_id")) == target
            for operation in operations
        )
    }


_SUPERSESSION_RELATIONS = {"superseded-by", "supersedes", "superseded_by"}


def _relationship_destination(
    operation: Mapping[str, Any],
    replacement_ids: Mapping[str, str],
    view: Mapping[str, Any],
    *,
    legacy_root_id: str,
    new_root_id: str,
) -> tuple[str, str]:
    source_id = str(operation["source_id"])
    target_id = str(operation["target_id"])
    source = replacement_ids.get(source_id, new_root_id if source_id == legacy_root_id else source_id)
    target = replacement_ids.get(target_id, new_root_id if target_id == legacy_root_id else target_id)
    target_step = operation.get("target_step")
    step_endpoint = str(operation.get("target_step_endpoint") or legacy_root_id)
    if target_step and source_id == step_endpoint:
        source = _step_id(view, str(target_step))
    if target_step and target_id == step_endpoint:
        target = _step_id(view, str(target_step))
    return source, target


def _snapshot_edges(snapshot: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for name in ("internal", "outgoing_external", "incoming_external"):
        values = snapshot.get(name)
        if not isinstance(values, list):
            raise DstackError(f"adoption snapshot field {name} must be an array")
        for index, edge in enumerate(values):
            if not isinstance(edge, Mapping):
                raise DstackError(f"adoption snapshot field {name} item {index} is not an object")
            source = edge.get("source_id")
            target = edge.get("target_id")
            relation = edge.get("relationship_type")
            if not all(isinstance(value, str) and value for value in (source, target, relation)):
                raise DstackError(f"adoption snapshot field {name} item {index} is invalid")
            result.add((str(source), str(target), str(relation)))
    return result


def _adoption_postcondition(
    expected_graph: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    legacy_root_id: str,
    new_root_id: str,
    view: Mapping[str, Any],
    replacement_ids: Mapping[str, str],
    resolved_decisions: set[str],
    supersede_root: bool,
    client: BeadsClient | None = None,
) -> dict[str, Any]:
    """Derive the exact intended legacy-graph state from the reviewed plan."""

    raw_records = expected_graph.get("legacy_records")
    if not isinstance(raw_records, list):
        raise DstackError("adoption snapshot legacy_records must be an array")
    issue_states: dict[str, dict[str, Any]] = {}
    original_parents: dict[str, str | None] = {}
    superseded_ids: set[str] = set()
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, Mapping):
            raise DstackError(f"adoption snapshot legacy_records item {index} is not an object")
        issue_id = raw.get("id")
        native_type = issue_type(raw)
        status = raw.get("status")
        if (
            not isinstance(issue_id, str)
            or not issue_id
            or not native_type
            or not isinstance(status, str)
            or not status
        ):
            raise DstackError(f"adoption snapshot legacy_records item {index} is incomplete")
        parent = issue_parent(raw)
        original_parents[issue_id] = parent
        issue_states[issue_id] = {
            "status": status,
            "issue_type": native_type,
            "parents": [parent],
            "superseded_target": superseded_target(raw),
        }
    if legacy_root_id not in issue_states:
        raise DstackError("adoption snapshot does not contain the selected legacy root")

    def expect_superseded(issue_id: str, target_id: str) -> None:
        state = issue_states.get(issue_id)
        if state is None:
            raise DstackError(f"adoption postcondition references unknown legacy issue: {issue_id}")
        original_parent = state["parents"][0]
        state["status"] = "closed"
        state["superseded_target"] = target_id
        superseded_ids.add(issue_id)
        # Beads may clear the live parent projection when an issue is
        # superseded. Either the original parent or a detached projection is
        # expected; reparenting to any other container is drift.
        state["parents"] = list(dict.fromkeys([original_parent, None]))

    for entry in plan.get("entries", []):
        if not isinstance(entry, Mapping):
            raise DstackError("adoption plan contains an invalid entry")
        issue_id = str(entry.get("legacy_id") or "")
        classification = str(entry.get("classification") or "")
        if issue_id not in issue_states:
            raise DstackError(f"adoption plan references unknown legacy issue: {issue_id}")
        if classification == "completed-history":
            issue_states[issue_id]["status"] = "closed"
        elif classification in _CEREMONY_TARGETS:
            expect_superseded(issue_id, _step_id(view, _CEREMONY_TARGETS[classification]))
        elif classification == "remaining-implementation" or (
            classification == "preserved-unchanged" and entry.get("strategy") == "recreate"
        ):
            replacement = replacement_ids.get(issue_id)
            if not replacement:
                raise DstackError(f"adoption postcondition has no replacement for {issue_id}")
            expect_superseded(issue_id, replacement)
        elif classification == "preserved-unchanged" and entry.get("strategy") == "reparent":
            parent = entry.get("surviving_parent")
            if not isinstance(parent, str) or not parent:
                raise DstackError(f"adoption postcondition has no surviving parent for {issue_id}")
            issue_states[issue_id]["parents"] = [parent]
        elif classification == "unresolved-decision" and issue_id in resolved_decisions:
            expect_superseded(issue_id, _step_id(view, "specification"))

    if supersede_root:
        expect_superseded(legacy_root_id, new_root_id)

    legacy_ids = set(issue_states)
    expected_edges = {
        edge
        for edge in _snapshot_edges(expected_graph)
        if edge[2] not in _SUPERSESSION_RELATIONS and (edge[0] not in superseded_ids or edge[2] == "parent-child")
    }
    # Reparenting is performed through the native parent field. When the
    # snapshot exposes that relationship as a parent-child dependency too,
    # transform the expected edge alongside the expected parent value.
    for entry in plan.get("entries", []):
        if not isinstance(entry, Mapping):
            continue
        if entry.get("classification") != "preserved-unchanged" or entry.get("strategy") != "reparent":
            continue
        issue_id = str(entry.get("legacy_id") or "")
        parent = entry.get("surviving_parent")
        state = issue_states.get(issue_id)
        if state is None or not isinstance(parent, str) or not parent:
            continue
        original_parent = original_parents.get(issue_id)
        if original_parent is not None:
            original_edge = (issue_id, original_parent, "parent-child")
        else:
            original_edge = None
        if original_edge is not None and original_edge in expected_edges:
            expected_edges.remove(original_edge)
            expected_edges.add((issue_id, parent, "parent-child"))
    required_external_edges: set[tuple[str, str, str]] = set()
    for operation in plan.get("relationship_operations", []):
        if not isinstance(operation, Mapping):
            raise DstackError("adoption plan contains an invalid relationship operation")
        source_id = str(operation.get("source_id") or "")
        target_id = str(operation.get("target_id") or "")
        relation = str(operation.get("relationship_type") or "")
        original = (source_id, target_id, relation)
        decision = str(operation.get("decision") or "")
        if decision in {"preserve", "preserve-native-supersession"}:
            continue
        if decision == "deferred-redirect" and not supersede_root:
            continue
        if relation == "relates-to" and replacement_ids.get(source_id) == target_id:
            expected_edges.discard(original)
            continue
        if decision == "lifecycle-only":
            expected_edges.discard(original)
            continue
        if decision not in {"redirect", "deferred-redirect"}:
            raise DstackError(f"unknown relationship decision: {decision}")
        mapped = (
            *_relationship_destination(
                operation,
                replacement_ids,
                view,
                legacy_root_id=legacy_root_id,
                new_root_id=new_root_id,
            ),
            relation,
        )
        if mapped != original:
            expected_edges.discard(original)
            if mapped[0] in legacy_ids or mapped[1] in legacy_ids:
                expected_edges.add(mapped)
            else:
                required_external_edges.add(mapped)

    for staged in plan.get("decision_staging", []):
        if not isinstance(staged, Mapping) or staged.get("action") != "preserve-blocker":
            continue
        issue_id = str(staged.get("legacy_id") or "")
        if issue_id in resolved_decisions:
            continue
        name = str(staged.get("blocking_target") or "")
        if name in FEATURE_STEPS:
            target = _step_id(view, name)
        elif name in FEATURE_STEPS.values():
            target = _step_id(view, next(key for key, label in FEATURE_STEPS.items() if label == name))
        else:
            target = name
        expected_edges.add((target, issue_id, "blocks"))

    target_integrity: dict[str, dict[str, Any]] = {}
    replacement_integrity: list[dict[str, Any]] = []
    if client is not None:
        target_ids = {"root": new_root_id, **{name: _step_id(view, name) for name in FEATURE_STEPS}}
        for name, issue_id in target_ids.items():
            issue = client.show(issue_id)
            target_integrity[name] = {
                "id": issue_id,
                "type": issue_type(issue),
                "parent": issue_parent(issue),
                "labels": sorted(str(label) for label in issue.get("labels", [])),
                "title": str(issue.get("title") or ""),
                "status": str(issue.get("status") or ""),
                "assignee": issue.get("assignee"),
            }
        replacement_integrity = [
            {
                "target_id": replacement_ids[str(spec["legacy_id"])],
                "spec": dict(spec),
                "blocker_id": _replacement_blocker_id(client, view, spec, _step_id(view, "approval")),
            }
            for spec in plan.get("replacements", [])
            if str(spec.get("legacy_id") or "") in replacement_ids
        ]

    return {
        "legacy_root_id": legacy_root_id,
        "legacy_ids": sorted(legacy_ids),
        "issue_states": issue_states,
        "legacy_edges": sorted(expected_edges),
        "required_external_edges": sorted(required_external_edges),
        "target_integrity": target_integrity,
        "replacement_integrity": replacement_integrity,
    }


def _validate_target_integrity(client: BeadsClient, postcondition: Mapping[str, Any]) -> None:
    raw_targets = postcondition.get("target_integrity")
    if not isinstance(raw_targets, Mapping) or not raw_targets:
        return
    for name, raw_state in raw_targets.items():
        if not isinstance(raw_state, Mapping):
            raise DstackError(f"adoption target integrity is invalid: {name}")
        issue_id = str(raw_state.get("id") or "")
        actual = client.show(issue_id)
        observed = {
            "id": issue_id,
            "type": issue_type(actual),
            "parent": issue_parent(actual),
            "labels": sorted(str(label) for label in actual.get("labels", [])),
            "title": str(actual.get("title") or ""),
            "status": str(actual.get("status") or ""),
            "assignee": actual.get("assignee"),
        }
        if observed != dict(raw_state):
            raise DstackError(f"adoption target topology/content drifted: {name}")
    approval_id = str(raw_targets.get("approval", {}).get("id") or "")
    implementation_id = str(raw_targets.get("implementation", {}).get("id") or "")
    for replacement in postcondition.get("replacement_integrity", []):
        if not isinstance(replacement, Mapping) or not isinstance(replacement.get("spec"), Mapping):
            raise DstackError("adoption replacement integrity snapshot is invalid")
        _validate_replacement(
            client,
            str(replacement.get("target_id") or ""),
            replacement["spec"],
            implementation_id=implementation_id,
            approval_id=str(replacement.get("blocker_id") or approval_id),
        )


def validate_adoption_postcondition(client: BeadsClient, postcondition: Mapping[str, Any]) -> None:
    """Validate the explicitly derived state after all adoption mutations."""

    _validate_target_integrity(client, postcondition)
    inventory = adoption_native_inventory(client)
    raw_states = postcondition.get("issue_states")
    if not isinstance(raw_states, Mapping):
        raise DstackError("adoption postcondition has no issue states")
    legacy_ids = {str(item) for item in postcondition.get("legacy_ids", [])}
    if legacy_ids != {str(item) for item in raw_states}:
        raise DstackError("adoption postcondition legacy issue set is inconsistent")

    # A new descendant can otherwise disappear from the planned topology when
    # supersession clears parentage. Detect it from the fresh native inventory
    # before accepting the final state, including descendants nested below an
    # unexpectedly inserted child.
    parent_by_id = {issue_id: issue_parent(issue) for issue_id, issue in inventory.items()}
    for issue_id in inventory:
        if issue_id in legacy_ids:
            continue
        seen: set[str] = set()
        parent = parent_by_id.get(issue_id)
        while parent is not None and parent not in seen:
            if parent in legacy_ids:
                raise DstackError(f"adoption graph generation drifted; unexpected legacy descendant: {issue_id}")
            seen.add(parent)
            parent = parent_by_id.get(parent)

    for issue_id, raw_state in raw_states.items():
        if not isinstance(raw_state, Mapping):
            raise DstackError(f"adoption postcondition is invalid for {issue_id}")
        actual = inventory.get(str(issue_id))
        if actual is None:
            raise DstackError(f"adoption postcondition is missing legacy issue: {issue_id}")
        if issue_type(actual) != raw_state.get("issue_type"):
            raise DstackError(f"adoption changed the native issue type unexpectedly: {issue_id}")
        if actual.get("status") != raw_state.get("status"):
            raise DstackError(f"adoption status postcondition failed: {issue_id}")
        parents = raw_state.get("parents")
        if not isinstance(parents, list) or issue_parent(actual) not in parents:
            raise DstackError(f"adoption parent postcondition failed: {issue_id}")
        if superseded_target(actual) != raw_state.get("superseded_target"):
            raise DstackError(f"adoption supersession postcondition failed: {issue_id}")

    actual_legacy_edges: set[tuple[str, str, str]] = set()
    for source_id, issue in inventory.items():
        for record in dependency_records(issue):
            target = record.get("depends_on_id") or record.get("id")
            relation = str(record.get("type") or record.get("dependency_type") or "blocks")
            if not isinstance(target, str) or not target:
                raise DstackError(f"native adoption postcondition has an invalid edge: {source_id}")
            if relation in _SUPERSESSION_RELATIONS or relation not in RELATIONS:
                continue
            if source_id in legacy_ids or target in legacy_ids:
                actual_legacy_edges.add((source_id, target, relation))
    expected_legacy_edges = {
        tuple(str(value) for value in edge)
        for edge in postcondition.get("legacy_edges", [])
        if isinstance(edge, (list, tuple)) and len(edge) == 3
    }
    if actual_legacy_edges != expected_legacy_edges:
        raise DstackError("adoption relationship postcondition failed for the legacy graph")

    for raw_edge in postcondition.get("required_external_edges", []):
        if not isinstance(raw_edge, (list, tuple)) or len(raw_edge) != 3:
            raise DstackError("adoption postcondition contains an invalid external edge")
        source, target, relation = (str(value) for value in raw_edge)
        issue = inventory.get(source)
        if issue is None or not _edge(issue, target, relation):
            raise DstackError(f"adoption external relationship postcondition failed: {source} -> {target}")


def _remove_planned_edge(client: BeadsClient, source: str, target: str, relation: str) -> None:
    if not _edge(client.show(source), target, relation):
        raise DstackError(f"planned relationship drifted before removal: {source} -> {target} ({relation})")
    _remove_edge(client, source, target)


def _step_id(view: Mapping[str, Any], name: str) -> str:
    steps = view.get("steps")
    if not isinstance(steps, Mapping) or not isinstance(steps.get(name), Mapping):
        raise DstackError(f"current feature has no {name} lifecycle step")
    value = steps[name].get("id")
    if not value:
        raise DstackError(f"current feature {name} step has no ID")
    return str(value)


def _require_open_unassigned(client: BeadsClient, issue_id: str) -> dict[str, Any]:
    issue = client.show(issue_id)
    if issue.get("status") != "open" or issue.get("assignee") not in (None, ""):
        raise DstackError(f"adoption requires open and unassigned issue before mutation: {issue_id}")
    if not issue_type(issue):
        raise DstackError(f"adoption issue has no native type: {issue_id}")
    return issue


def _incorporated_decision_authorized(
    client: BeadsClient,
    view: Mapping[str, Any],
    section: str,
) -> bool:
    design_state = feature_design_state(client, view)
    authorization = feature_authorization_state(client, view)
    if not design_state.get("design_approved") or not authorization.get("native_approved"):
        return False
    design_path = str(view.get("design_path") or "")
    worktree = worktree_for_branch(client.root, f"feat/{view.get('slug')}")
    if worktree is None:
        return False
    try:
        _section(worktree, section, design_path)
    except DstackError:
        return False
    return True


def _replacement_blocker_id(
    client: BeadsClient,
    view: Mapping[str, Any],
    spec: Mapping[str, Any],
    approval_id: str,
) -> str:
    source_type = str(spec.get("source_type") or "")
    if source_type not in {"bug", "chore"}:
        return approval_id
    approval = client.show(approval_id)
    gate = human_gate_for_step(client, root_id=str(view["root"]["id"]), step=approval)
    if not isinstance(gate, Mapping) or not gate.get("id"):
        raise DstackError(f"{source_type} replacement requires the feature human approval gate")
    return str(gate["id"])


def _validate_replacement(
    client: BeadsClient,
    target_id: str,
    spec: Mapping[str, Any],
    *,
    implementation_id: str,
    approval_id: str,
) -> None:
    target = client.show(target_id)
    replacement = spec["replacement"]
    if issue_type(target) != str(spec.get("source_type") or issue_type(target)):
        raise DstackError(f"replacement type drifted for {spec['legacy_id']}")
    if target.get("status") in {"closed", "deferred"}:
        raise DstackError(f"replacement is not active for {spec['legacy_id']}")
    if target.get("assignee") not in (None, ""):
        raise DstackError(f"replacement is assigned for {spec['legacy_id']}")
    if str(target.get("title") or "") != replacement["title"]:
        raise DstackError(f"replacement title drifted for {spec['legacy_id']}")
    description = str(target.get("description") or "")
    acceptance = str(target.get("acceptance_criteria") or target.get("acceptance") or "")
    if description != replacement["description"] or acceptance != replacement["acceptance"]:
        raise DstackError(f"replacement content drifted for {spec['legacy_id']}")
    if int(target.get("priority") or 0) != replacement["priority"]:
        raise DstackError(f"replacement priority drifted for {spec['legacy_id']}")
    if issue_parent(target) != implementation_id or not has_label(target, "dstack:work:implementation"):
        raise DstackError(f"replacement topology drifted for {spec['legacy_id']}")
    if not _edge(target, approval_id, "blocks"):
        raise DstackError(f"replacement approval blocker missing for {spec['legacy_id']}")


def _replacement_association(
    client: BeadsClient,
    old: Mapping[str, Any],
    *,
    implementation_id: str,
) -> str | None:
    superseded = superseded_target(old)
    if superseded:
        return superseded
    implementation_children = {str(item.get("id")) for item in descendants(client, implementation_id)}
    related = []
    for record in dependency_records(old):
        relation = str(record.get("type") or record.get("dependency_type") or "blocks")
        target = record.get("depends_on_id") or record.get("id")
        if relation == "relates-to" and isinstance(target, str) and target in implementation_children:
            related.append(target)
    if len(related) > 1:
        raise DstackError(f"ambiguous replacement association for {old.get('id')}")
    return related[0] if related else None


def _find_existing_replacement(
    client: BeadsClient,
    spec: Mapping[str, Any],
    *,
    implementation_id: str,
    approval_id: str,
    expected_id: str | None,
    reserved: set[str],
) -> str | None:
    candidates = []
    for item in descendants(client, implementation_id):
        if str(item.get("id")) == str(spec["legacy_id"]):
            continue
        if str(item.get("title") or "") == str(spec["replacement"]["title"]):
            candidates.append(item)
    if len(candidates) > 1:
        raise DstackError(f"ambiguous existing replacements for {spec['legacy_id']}")
    if not candidates:
        return None
    candidate_id = str(candidates[0]["id"])
    if candidate_id in reserved:
        raise DstackError(f"replacement candidate is already reserved: {candidate_id}")
    candidate_target = _replacement_association(client, candidates[0], implementation_id=implementation_id)
    if expected_id is None or expected_id not in {candidate_id, candidate_target}:
        raise DstackError(f"unrelated replacement candidate lacks native supersession proof: {candidate_id}")
    target_id = expected_id or candidate_id
    if not target_id:
        raise DstackError(f"replacement proof missing for {spec['legacy_id']}")
    _validate_replacement(client, target_id, spec, implementation_id=implementation_id, approval_id=approval_id)
    return target_id


def _replacement_for(
    client: BeadsClient,
    old: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    implementation_id: str,
    approval_id: str,
) -> str:
    old_id = str(old["id"])
    old_kind = issue_type(old)
    if old_kind not in EXECUTABLE_REPLACEMENT_TYPES:
        raise DstackError(
            f"replacement source must be executable task, bug, or chore: {old_id} ({old_kind or 'unknown'})"
        )
    replacement = spec["replacement"]
    reject_documentation_work(replacement["title"], stage="implementation")
    existing = _replacement_association(client, old, implementation_id=implementation_id)
    if existing:
        _validate_replacement(client, existing, spec, implementation_id=implementation_id, approval_id=approval_id)
        return existing
    created = client.create(
        replacement["title"],
        issue_type_name=old_kind,
        parent=implementation_id,
        labels=["dstack:work:implementation"],
        dependencies=[approval_id],
        description=replacement["description"],
        acceptance=replacement["acceptance"],
        priority=replacement["priority"],
    )
    target_id = str(created.get("id") or "")
    if not target_id:
        raise DstackError(f"replacement creation returned no ID for {old_id}")
    client.add_dependency(old_id, target_id, relation_type="relates-to")
    if not _edge(client.show(old_id), target_id, "relates-to"):
        raise DstackError(f"replacement association did not converge for {old_id}")
    _validate_replacement(client, target_id, spec, implementation_id=implementation_id, approval_id=approval_id)
    return target_id


def _native_block_compatible(source_kind: str, target_kind: str) -> bool:
    executable = {"task", "bug", "chore"}
    return source_kind == target_kind or (source_kind in executable and target_kind == "gate")


def _approved_incorporated_retry(client: BeadsClient, plan: Mapping[str, Any], view: Mapping[str, Any]) -> bool:
    sections = [
        str(item.get("specification_section"))
        for item in plan.get("decision_staging", [])
        if item.get("action") == "incorporate-after-approval"
    ]
    return bool(sections) and all(_incorporated_decision_authorized(client, view, section) for section in sections)


def validate_adoption_preflight(
    client: BeadsClient,
    plan: Mapping[str, Any],
    *,
    legacy_root_id: str,
    target_view: Mapping[str, Any] | None = None,
) -> None:
    root = _require_open_unassigned(client, legacy_root_id)
    if issue_type(root) not in {"epic", "molecule", "feature"}:
        raise DstackError(f"legacy root has unsupported native type: {legacy_root_id}")
    entries = plan.get("entries")
    if not isinstance(entries, list):
        raise DstackError("adoption plan entries are invalid")
    for entry in entries:
        issue = client.show(str(entry["legacy_id"]))
        if issue.get("status") == "closed":
            if entry["classification"] == "completed-history" or superseded_target(issue):
                continue
            raise DstackError(f"planned legacy endpoint is unexpectedly closed: {entry['legacy_id']}")
        _require_open_unassigned(client, str(entry["legacy_id"]))
    expected_steps = {
        "specification": "task",
        "approval": "task",
        "closeout": "task",
        "implementation": "epic",
    }
    approved_retry = bool(target_view is not None and _approved_incorporated_retry(client, plan, target_view))
    if target_view is not None:
        target_root = target_view.get("root")
        if not isinstance(target_root, Mapping) or str(target_root.get("status")) not in {
            "open",
            "claimed",
            "in_progress",
        }:
            raise DstackError("new feature root has invalid status")
        if issue_type(target_root) not in {"molecule", "epic", "feature"} or target_root.get("assignee") not in (
            None,
            "",
        ):
            raise DstackError("new feature root has invalid native topology")
        for name, expected in expected_steps.items():
            actual = client.show(_step_id(target_view, name))
            if issue_type(actual) != expected:
                raise DstackError(f"target {name} step has incompatible native type")
            allowed_statuses = {"open", "claimed", "in_progress"}
            if approved_retry and name in {"specification", "approval"}:
                allowed_statuses.add("closed")
            if actual.get("status") not in allowed_statuses:
                raise DstackError(f"target {name} step has invalid status")
            if actual.get("assignee") not in (None, ""):
                raise DstackError(f"target {name} step is assigned")
    for spec in plan.get("replacements", []):
        source_type = str(spec.get("source_type") or "")
        if source_type not in EXECUTABLE_REPLACEMENT_TYPES:
            raise DstackError(
                "replacement source must be executable task, bug, or chore: "
                f"{spec['legacy_id']} ({source_type or 'unknown'})"
            )
        if target_view is not None:
            _replacement_blocker_id(client, target_view, spec, _step_id(target_view, "approval"))
    inventory = plan.get("inventory")
    if not isinstance(inventory, Mapping):
        raise DstackError("adoption plan graph inventory is missing")
    endpoint_ids: set[str] = set()
    for key in ("internal", "outgoing_external", "incoming_external"):
        edges = inventory.get(key, [])
        if not isinstance(edges, list):
            raise DstackError(f"adoption plan inventory section is invalid: {key}")
        for edge in edges:
            endpoint_ids.update((str(edge["source_id"]), str(edge["target_id"])))
    for endpoint_id in sorted(endpoint_ids):
        issue = client.show(endpoint_id)
        _require_endpoint(client, endpoint_id)
        if endpoint_id != legacy_root_id and (
            issue.get("status") in {"claimed", "in_progress"} or issue.get("assignee") not in (None, "")
        ):
            raise DstackError(f"planned graph endpoint is claimed or assigned: {endpoint_id}")
    for operation in plan.get("relationship_operations", []):
        if (
            operation.get("decision") not in {"redirect", "deferred-redirect"}
            or operation.get("relationship_type") != "blocks"
        ):
            continue
        source_issue = client.show(str(operation["source_id"]))
        target_issue = client.show(str(operation["target_id"]))
        if (source_issue.get("status") in {"closed", "deferred"} and not superseded_target(source_issue)) or (
            target_issue.get("status") in {"closed", "deferred"} and not superseded_target(target_issue)
        ):
            raise DstackError("planned blocker remap endpoint is not open")
        source_kind, target_kind = issue_type(source_issue), issue_type(target_issue)
        target_step = operation.get("target_step")
        if target_step:
            step_name = str(target_step)
            destination_kind = expected_steps[step_name]
            if operation["source_id"] == legacy_root_id:
                source_kind = destination_kind
            elif operation["target_id"] == legacy_root_id:
                target_kind = destination_kind
            if target_view is not None:
                step_id = _step_id(target_view, step_name)
                step = client.show(step_id)
                closed_transfer = approved_retry and step_name in {"specification", "approval"}
                if step.get("status") in {"closed", "deferred"}:
                    if not closed_transfer:
                        raise DstackError(f"planned lifecycle target is not mutable: {step_name}")
                    step_endpoint = str(operation.get("target_step_endpoint") or legacy_root_id)
                    transfer_source = (
                        step_id if str(operation["source_id"]) == step_endpoint else str(operation["source_id"])
                    )
                    transfer_target = (
                        step_id if str(operation["target_id"]) == step_endpoint else str(operation["target_id"])
                    )
                    if not _edge(client.show(transfer_source), transfer_target, "blocks"):
                        raise DstackError(f"approved lifecycle transfer is not converged: {step_name}")
        if not _native_block_compatible(source_kind, target_kind):
            raise DstackError(f"planned blocker remap is not native-compatible: {source_kind} -> {target_kind}")


def _validate_target_root(client: BeadsClient, root_id: str) -> dict[str, Any]:
    root = client.show(root_id)
    if root.get("status") not in {"open", "claimed", "in_progress"}:
        raise DstackError("new feature root has invalid status")
    if issue_type(root) not in {"epic", "molecule", "feature"} or root.get("assignee") not in (None, ""):
        raise DstackError("new feature root has invalid native topology")
    return root


def _validate_target_step_ids(
    client: BeadsClient,
    root_id: str,
    step_ids: Mapping[str, str],
    *,
    allow_closed_steps: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    root = _validate_target_root(client, root_id)
    expected_types = {
        "specification": "task",
        "approval": "task",
        "implementation": "epic",
        "closeout": "task",
    }
    steps: dict[str, dict[str, Any]] = {}
    for name, expected_type in expected_types.items():
        step = client.show(step_ids[name])
        if issue_type(step) != expected_type:
            raise DstackError(f"target {name} step has incompatible native type")
        if issue_parent(step) != root_id or not has_label(step, FEATURE_STEPS[name]):
            raise DstackError(f"target {name} step drifted outside the current feature topology")
        allowed = {"open", "claimed", "in_progress"}
        if name in allow_closed_steps:
            allowed.add("closed")
        if step.get("status") not in allowed:
            raise DstackError(f"target {name} step has invalid status")
        if step.get("assignee") not in (None, ""):
            raise DstackError(f"target {name} step is assigned")
        steps[name] = step
    return {"root": root, "steps": steps}


def validate_target_topology(
    client: BeadsClient,
    root_id: str,
    *,
    allow_closed_steps: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    # Validate the container before deriving lifecycle identity from its children.
    # Otherwise a malformed/closed root can be masked by a secondary missing-step error.
    _validate_target_root(client, root_id)
    children = client.children(root_id)
    step_ids = {name: str(step_by_label(children, label)["id"]) for name, label in FEATURE_STEPS.items()}
    return _validate_target_step_ids(
        client,
        root_id,
        step_ids,
        allow_closed_steps=allow_closed_steps,
    )


def _validate_surviving_parent(
    client: BeadsClient,
    parent_id: str,
    *,
    legacy_ids: set[str],
) -> None:
    if not parent_id:
        raise DstackError("reparent target is missing")
    if parent_id in legacy_ids:
        raise DstackError(f"surviving_parent drifted inside the legacy root: {parent_id}")
    parent = client.show(parent_id)
    if parent.get("status") not in {"open", "claimed", "in_progress"}:
        raise DstackError(f"surviving_parent is not open: {parent_id}")
    if issue_type(parent) not in {"epic", "molecule"}:
        raise DstackError(f"surviving_parent is not an open container: {parent_id}")

    # A concurrent native reparent can move the nominated container under the
    # legacy graph without changing the container itself. Follow the live
    # ancestry so containment drift is rejected immediately before use.
    seen = {parent_id}
    ancestor_id = issue_parent(parent)
    while ancestor_id:
        if ancestor_id in legacy_ids:
            raise DstackError(f"surviving_parent drifted inside the legacy root: {parent_id}")
        if ancestor_id in seen:
            raise DstackError(f"surviving_parent has cyclic native parentage: {parent_id}")
        seen.add(ancestor_id)
        ancestor = client.show(ancestor_id)
        ancestor_id = issue_parent(ancestor)


def _validate_surviving_parents(
    client: BeadsClient,
    entries: list[Mapping[str, Any]],
    *,
    legacy_root_id: str,
) -> set[str]:
    reparent_entries = [
        entry
        for entry in entries
        if entry.get("classification") == "preserved-unchanged" and entry.get("strategy") == "reparent"
    ]
    legacy_ids = {legacy_root_id, *(str(entry["legacy_id"]) for entry in entries)}
    if not reparent_entries:
        return legacy_ids
    legacy_ids.update(str(item["id"]) for item in descendants(client, legacy_root_id))
    for entry in reparent_entries:
        parent_id = str(entry.get("surviving_parent") or "")
        if not parent_id:
            raise DstackError(f"reparent target is missing for {entry['legacy_id']}")
        _validate_surviving_parent(client, parent_id, legacy_ids=legacy_ids)
    return legacy_ids


def _validate_prior_supersessions(
    client: BeadsClient,
    entries: list[Mapping[str, Any]],
    replacements: list[Mapping[str, Any]],
    *,
    implementation_id: str,
    approval_id: str,
    view: Mapping[str, Any],
    specification_id: str,
    legacy_root_id: str,
    new_root_id: str,
) -> None:
    replacement_specs = {str(spec["legacy_id"]): spec for spec in replacements}
    for entry in entries:
        old_id = str(entry["legacy_id"])
        prior = superseded_target(client.show(old_id))
        if not prior:
            continue
        cls = str(entry["classification"])
        expected = None
        if cls in _CEREMONY_TARGETS:
            expected = _step_id(view, _CEREMONY_TARGETS[cls])
        elif cls == "remaining-implementation" or (
            cls == "preserved-unchanged" and entry.get("strategy") == "recreate"
        ):
            spec = replacement_specs.get(old_id)
            if spec is None:
                raise DstackError(f"replacement plan missing for superseded item: {old_id}")
            _validate_replacement(
                client,
                prior,
                spec,
                implementation_id=implementation_id,
                approval_id=_replacement_blocker_id(client, view, spec, approval_id),
            )
            expected = prior
        elif cls == "unresolved-decision" and entry.get("strategy") == "incorporated":
            expected = specification_id
        if expected != prior:
            raise DstackError(f"unexpected supersession target for {old_id}")
    prior_root = superseded_target(client.show(legacy_root_id))
    if prior_root and prior_root != new_root_id:
        raise DstackError("unexpected legacy root supersession target")


def execute_adoption_plan(
    client: BeadsClient,
    plan: Mapping[str, Any],
    *,
    legacy_root_id: str,
    new_root_id: str,
    view: Mapping[str, Any],
    expected_graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA or plan.get("legacy_root_id") != legacy_root_id:
        raise DstackError("adoption plan identity does not match the selected root")
    entries = plan.get("entries")
    if not isinstance(entries, list):
        raise DstackError("adoption plan entries are invalid")
    replacements = plan.get("replacements", [])
    if not isinstance(replacements, list):
        raise DstackError("adoption plan replacements are invalid")
    for spec in replacements:
        old_id = str(spec["legacy_id"])
        live_type = issue_type(client.show(old_id))
        planned_type = str(spec.get("source_type") or live_type or "")
        if live_type not in EXECUTABLE_REPLACEMENT_TYPES or planned_type not in EXECUTABLE_REPLACEMENT_TYPES:
            raise DstackError(
                f"replacement source must be executable task, bug, or chore: {old_id} ({live_type or planned_type or 'unknown'})"
            )
        if spec.get("source_type") and planned_type != live_type:
            raise DstackError(f"replacement source type drifted before adoption mutation: {old_id}")
    implementation_id, approval_id, specification_id = (
        _step_id(view, n) for n in ("implementation", "approval", "specification")
    )
    _validate_prior_supersessions(
        client,
        entries,
        replacements,
        implementation_id=implementation_id,
        approval_id=approval_id,
        view=view,
        specification_id=specification_id,
        legacy_root_id=legacy_root_id,
        new_root_id=new_root_id,
    )
    if expected_graph is not None:
        reconcile_adoption_graph(client, expected_graph, legacy_root_id)
    incoming_dependents = _incoming_dependent_ids(plan)
    _assert_not_ready(client, incoming_dependents, phase="before-adoption")
    replacement_ids: dict[str, str] = {}
    reserved: set[str] = set()
    approved_retry = _approved_incorporated_retry(client, plan, view)
    _validate_target_step_ids(
        client,
        new_root_id,
        {name: _step_id(view, name) for name in FEATURE_STEPS},
        allow_closed_steps=frozenset({"specification", "approval"}) if approved_retry else frozenset(),
    )
    legacy_topology_ids = _validate_surviving_parents(client, entries, legacy_root_id=legacy_root_id)
    for op in plan.get("relationship_operations", []):
        if op.get("decision") in {"redirect", "deferred-redirect"} and op.get("target_step"):
            step_name = str(op["target_step"])
            step = client.show(_step_id(view, step_name))
            closed_transfer = approved_retry and step_name in {"specification", "approval"}
            if step.get("status") in {"closed", "deferred"}:
                if not closed_transfer:
                    raise DstackError(f"planned lifecycle target is not mutable: {op['target_step']}")
                step_endpoint = str(op.get("target_step_endpoint") or legacy_root_id)
                if str(op["source_id"]) == step_endpoint:
                    transfer_source = _step_id(view, step_name)
                    transfer_target = str(op["target_id"])
                elif str(op["target_id"]) == step_endpoint:
                    transfer_source = str(op["source_id"])
                    transfer_target = _step_id(view, step_name)
                else:
                    raise DstackError(f"approved lifecycle transfer has no lifecycle endpoint: {step_name}")
                if not _edge(client.show(transfer_source), transfer_target, "blocks"):
                    raise DstackError(f"approved lifecycle transfer is not converged: {step_name}")
            if step.get("assignee") not in (None, ""):
                raise DstackError(f"planned lifecycle target is assigned: {op['target_step']}")
    for entry in entries:
        old = client.show(str(entry["legacy_id"]))
        if old.get("status") == "closed":
            if entry["classification"] == "completed-history" or superseded_target(old):
                continue
            raise DstackError(f"unexpected closed adoption item: {entry['legacy_id']}")
        _require_open_unassigned(client, str(entry["legacy_id"]))
    titles: dict[str, str] = {}
    for spec in plan.get("replacements", []):
        title = str(spec["replacement"]["title"])
        if title in titles and titles[title] != str(spec["legacy_id"]):
            raise DstackError(f"replacement title collides across legacy IDs: {title}")
        titles[title] = str(spec["legacy_id"])
    preflight_reserved: set[str] = set()
    for spec in plan.get("replacements", []):
        old = client.show(str(spec["legacy_id"]))
        replacement_blocker = _replacement_blocker_id(client, view, spec, approval_id)
        candidate = _find_existing_replacement(
            client,
            spec,
            implementation_id=implementation_id,
            approval_id=replacement_blocker,
            expected_id=_replacement_association(client, old, implementation_id=implementation_id),
            reserved=preflight_reserved,
        )
        if candidate:
            preflight_reserved.add(candidate)
    _validate_prior_supersessions(
        client,
        entries,
        replacements,
        implementation_id=implementation_id,
        approval_id=approval_id,
        view=view,
        specification_id=specification_id,
        legacy_root_id=legacy_root_id,
        new_root_id=new_root_id,
    )

    for spec in plan.get("replacements", []):
        old = client.show(str(spec["legacy_id"]))
        expected = _replacement_association(client, old, implementation_id=implementation_id)
        replacement_blocker = _replacement_blocker_id(client, view, spec, approval_id)
        existing = _find_existing_replacement(
            client,
            spec,
            implementation_id=implementation_id,
            approval_id=replacement_blocker,
            expected_id=expected,
            reserved=reserved,
        )
        target = existing or _replacement_for(
            client, old, spec, implementation_id=implementation_id, approval_id=replacement_blocker
        )
        replacement_ids[str(spec["legacy_id"])] = target
        if target in reserved:
            raise DstackError(f"replacement candidate is already reserved: {target}")
        reserved.add(target)
    resolved: set[str] = set()
    blocked = False
    for staged in plan.get("decision_staging", []):
        old_id = str(staged["legacy_id"])
        if staged["action"] == "incorporate-after-approval":
            target = specification_id
            if _incorporated_decision_authorized(client, view, str(staged["specification_section"])):
                old = client.show(old_id)
                previous = superseded_target(old)
                if old.get("status") == "closed":
                    if previous != target:
                        raise DstackError(f"incorporated decision supersession drifted: {old_id}")
                else:
                    _require_open_unassigned(client, old_id)
                    _require_endpoint(client, target)
                    _remove_edge(client, target, old_id)
                    client.supersede(old_id, target)
                resolved.add(old_id)
                continue
        elif staged["action"] == "preserve-blocker":
            name = str(staged["blocking_target"])
            if name in FEATURE_STEPS:
                target = _step_id(view, name)
            elif name in FEATURE_STEPS.values():
                target = _step_id(view, next(k for k, v in FEATURE_STEPS.items() if v == name))
            else:
                target = name
            blocked = True
        else:
            raise DstackError(f"unknown decision staging action: {staged['action']}")
        _ensure_edge(client, target, old_id, "blocks")
        blocked = True
    keep = any(
        e.get("classification") == "preserved-unchanged" and e.get("strategy") == "keep-legacy-root" for e in entries
    )
    effective = bool(
        plan.get("supersession", {}).get("eligible")
        or (
            not blocked
            and not keep
            and all(
                s["action"] == "incorporate-after-approval" and str(s["legacy_id"]) in resolved
                for s in plan.get("decision_staging", [])
            )
        )
    )
    for entry in entries:
        old_id = str(entry["legacy_id"])
        prior_target = superseded_target(client.show(old_id))
        cls = str(entry["classification"])
        planned_target = None
        if cls in _CEREMONY_TARGETS:
            planned_target = _step_id(view, _CEREMONY_TARGETS[cls])
        elif cls == "remaining-implementation" or (
            cls == "preserved-unchanged" and entry.get("strategy") == "recreate"
        ):
            planned_target = replacement_ids.get(old_id)
        elif cls == "unresolved-decision" and old_id in resolved:
            planned_target = specification_id
        if prior_target and prior_target != planned_target:
            raise DstackError(f"unexpected supersession target for {old_id}")
    prior_root_target = superseded_target(client.show(legacy_root_id))
    if prior_root_target and prior_root_target != new_root_id:
        raise DstackError("unexpected legacy root supersession target")
    # Replacement creation and decision staging are Beads mutations. Reread
    # the target lifecycle immediately before relationship rewrites so native
    # parent/label/status drift cannot redirect edges to stale step IDs.
    _validate_target_step_ids(
        client,
        new_root_id,
        {name: _step_id(view, name) for name in FEATURE_STEPS},
        allow_closed_steps=frozenset({"specification", "approval"}) if approved_retry else frozenset(),
    )
    postcondition = (
        _adoption_postcondition(
            expected_graph,
            plan,
            legacy_root_id=legacy_root_id,
            new_root_id=new_root_id,
            view=view,
            replacement_ids=replacement_ids,
            resolved_decisions=resolved,
            supersede_root=effective,
            client=client,
        )
        if expected_graph is not None
        else None
    )
    for op in plan.get("relationship_operations", []):
        decision = op.get("decision")
        if decision in {"preserve", "preserve-native-supersession"}:
            continue
        if decision == "deferred-redirect":
            if not effective:
                continue
            decision = "redirect"
        so, to = str(op["source_id"]), str(op["target_id"])
        if str(op.get("relationship_type")) == "relates-to" and replacement_ids.get(so) == to:
            # This native edge is the retry association created immediately
            # after replacement creation, not a product dependency to redirect.
            continue
        source, repl_target = _relationship_destination(
            op,
            replacement_ids,
            view,
            legacy_root_id=legacy_root_id,
            new_root_id=new_root_id,
        )
        if decision == "redirect":
            if source != so or repl_target != to:
                relation = str(op["relationship_type"])
                _ensure_edge(client, source, repl_target, relation)
                _assert_not_ready(client, incoming_dependents, phase="after-add-before-remove")
                _remove_planned_edge(client, so, to, relation)
                _assert_not_ready(client, incoming_dependents, phase="after-remove")
        elif decision == "lifecycle-only":
            relation = str(op["relationship_type"])
            _remove_planned_edge(client, so, to, relation)
        else:
            raise DstackError(f"unknown relationship decision: {decision}")
    for entry in entries:
        if entry["classification"] == "preserved-unchanged" and entry["strategy"] == "reparent":
            old_id, parent = str(entry["legacy_id"]), str(entry["surviving_parent"])
            _validate_surviving_parent(
                client,
                parent,
                legacy_ids=legacy_topology_ids,
            )
            current = _require_open_unassigned(client, old_id)
            if issue_parent(current) != parent:
                client.update(old_id, "--parent", parent)
            if issue_parent(client.show(old_id)) != parent:
                raise DstackError(f"preserved work was not reparented: {old_id}")
    if postcondition is not None:
        _validate_target_integrity(client, postcondition)
    if expected_graph is not None:
        _validate_legacy_parentage_before_destructive_actions(client, plan, expected_graph)
        _assert_legacy_generation_boundary(
            client,
            plan,
            expected_graph,
            legacy_root_id=legacy_root_id,
            replacement_ids=replacement_ids,
            view=view,
        )
    mapping = dict(replacement_ids)
    for entry in entries:
        old_id, cls = str(entry["legacy_id"]), entry["classification"]
        old = client.show(old_id)
        if cls == "completed-history":
            if old.get("status") != "closed":
                _require_open_unassigned(client, old_id)
                if entry["evidence_assessment"] == "accepted-risk":
                    client.add_comment(old_id, "Adoption accepted risk: " + str(entry["accepted_risk_reason"]))
                client.close(old_id, str(entry["reason"]))
        elif cls in _CEREMONY_TARGETS:
            target = _step_id(view, _CEREMONY_TARGETS[cls])
            if superseded_target(old) not in {None, target}:
                raise DstackError(f"supersession drifted for {old_id}")
            if old.get("status") != "closed":
                _require_open_unassigned(client, old_id)
                client.supersede(old_id, target)
            mapping[old_id] = target
        elif cls == "remaining-implementation" or (cls == "preserved-unchanged" and entry["strategy"] == "recreate"):
            target = replacement_ids.get(old_id)
            if not target:
                raise DstackError(f"replacement missing for {old_id}")
            if old.get("status") != "closed":
                _require_open_unassigned(client, old_id)
                if _edge(old, target, "relates-to"):
                    _remove_edge(client, old_id, target)
                client.supersede(old_id, target)
            mapping[old_id] = target
    _assert_not_ready(client, incoming_dependents, phase="before-supersession")
    root_superseded = False
    if effective:
        remaining = [
            i
            for i in descendants(client, legacy_root_id)
            if i.get("status") not in {"closed", "deferred"} and str(i.get("id")) not in replacement_ids
        ]
        if remaining:
            raise DstackError(
                "legacy root supersession would strand executable work: " + ", ".join(str(i["id"]) for i in remaining)
            )
        root_state = client.show(legacy_root_id)
        if root_state.get("status") == "closed":
            if superseded_target(root_state) != new_root_id:
                raise DstackError("legacy root was superseded by an unexpected target")
        else:
            _require_open_unassigned(client, legacy_root_id)
            client.supersede(legacy_root_id, new_root_id)
        _assert_not_ready(client, incoming_dependents, phase="after-supersession")
        root_superseded = True
    if postcondition is not None:
        validate_adoption_postcondition(client, postcondition)
    return {
        "status": "ok",
        "legacy_root": legacy_root_id,
        "new_root": new_root_id,
        "mapping": mapping,
        "root_superseded": root_superseded,
        "decision_staging": plan.get("decision_staging", []),
    }
