"""Native execution boundary for a previously validated adoption plan."""

from __future__ import annotations

from typing import Any, Mapping

from dstack_adoption import PLAN_SCHEMA, RELATIONS, _section
from dstack_commands import descendants, superseded_target
from dstacklib import (
    BeadsClient,
    DstackError,
    FEATURE_STEPS,
    dependency_records,
    feature_authorization_state,
    feature_design_state,
    worktree_for_branch,
    has_label,
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
    if not old_kind:
        raise DstackError(f"adoption issue has no native type: {old_id}")
    existing = _replacement_association(client, old, implementation_id=implementation_id)
    if existing:
        _validate_replacement(client, existing, spec, implementation_id=implementation_id, approval_id=approval_id)
        return existing
    replacement = spec["replacement"]
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
        if not source_type:
            raise DstackError(f"replacement has no native source type: {spec['legacy_id']}")
        if source_type in {"bug", "chore"}:
            raise DstackError(f"{source_type} replacement cannot use the task approval blocker: {spec['legacy_id']}")
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
                    transfer_source = (
                        step_id if operation["source_id"] == legacy_root_id else str(operation["source_id"])
                    )
                    transfer_target = (
                        step_id if operation["target_id"] == legacy_root_id else str(operation["target_id"])
                    )
                    if not _edge(client.show(transfer_source), transfer_target, "blocks"):
                        raise DstackError(f"approved lifecycle transfer is not converged: {step_name}")
        if not _native_block_compatible(source_kind, target_kind):
            raise DstackError(f"planned blocker remap is not native-compatible: {source_kind} -> {target_kind}")


def validate_target_topology(client: BeadsClient, root_id: str) -> dict[str, Any]:
    root = client.show(root_id)
    if root.get("status") not in {"open", "claimed", "in_progress"}:
        raise DstackError("new feature root has invalid status")
    if issue_type(root) not in {"epic", "molecule", "feature"} or root.get("assignee") not in (
        None,
        "",
    ):
        raise DstackError("new feature root has invalid native topology")
    children = client.children(root_id)
    expected = {
        "specification": "task",
        "approval": "task",
        "closeout": "task",
        "implementation": "epic",
    }
    steps = {name: step_by_label(children, label) for name, label in FEATURE_STEPS.items()}
    for name, expected_type in expected.items():
        step = steps[name]
        if issue_type(step) != expected_type:
            raise DstackError(f"target {name} step has incompatible native type")
        if step.get("status") not in {"open", "claimed", "in_progress"}:
            raise DstackError(f"target {name} step has invalid status")
        if step.get("assignee") not in (None, ""):
            raise DstackError(f"target {name} step is assigned")
    return {"root": root, "steps": steps}


def execute_adoption_plan(
    client: BeadsClient,
    plan: Mapping[str, Any],
    *,
    legacy_root_id: str,
    new_root_id: str,
    view: Mapping[str, Any],
) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA or plan.get("legacy_root_id") != legacy_root_id:
        raise DstackError("adoption plan identity does not match the selected root")
    implementation_id, approval_id, specification_id = (
        _step_id(view, n) for n in ("implementation", "approval", "specification")
    )
    entries = plan.get("entries")
    if not isinstance(entries, list):
        raise DstackError("adoption plan entries are invalid")
    replacement_ids: dict[str, str] = {}
    reserved: set[str] = set()
    approved_retry = _approved_incorporated_retry(client, plan, view)
    for op in plan.get("relationship_operations", []):
        if op.get("decision") in {"redirect", "deferred-redirect"} and op.get("target_step"):
            step_name = str(op["target_step"])
            step = client.show(_step_id(view, step_name))
            closed_transfer = approved_retry and step_name in {"specification", "approval"}
            if step.get("status") in {"closed", "deferred"}:
                if not closed_transfer:
                    raise DstackError(f"planned lifecycle target is not mutable: {op['target_step']}")
                if op["source_id"] == legacy_root_id:
                    transfer_source = _step_id(view, step_name)
                    transfer_target = str(op["target_id"])
                elif op["target_id"] == legacy_root_id:
                    transfer_source = str(op["source_id"])
                    transfer_target = _step_id(view, step_name)
                else:
                    raise DstackError(f"approved lifecycle transfer has no root endpoint: {step_name}")
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
        candidate = _find_existing_replacement(
            client,
            spec,
            implementation_id=implementation_id,
            approval_id=approval_id,
            expected_id=_replacement_association(
                client, old, implementation_id=implementation_id
            ),
            reserved=preflight_reserved,
        )
        if candidate:
            preflight_reserved.add(candidate)

    for spec in plan.get("replacements", []):
        old = client.show(str(spec["legacy_id"]))
        expected = _replacement_association(client, old, implementation_id=implementation_id)
        existing = _find_existing_replacement(
            client,
            spec,
            implementation_id=implementation_id,
            approval_id=approval_id,
            expected_id=expected,
            reserved=reserved,
        )
        target = existing or _replacement_for(
            client, old, spec, implementation_id=implementation_id, approval_id=approval_id
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
        if entry["classification"] == "preserved-unchanged" and entry["strategy"] == "reparent":
            old_id, parent = str(entry["legacy_id"]), str(entry["surviving_parent"])
            current = _require_open_unassigned(client, old_id)
            if issue_parent(current) != parent:
                client.update(old_id, "--parent", parent)
            if issue_parent(client.show(old_id)) != parent:
                raise DstackError(f"preserved work was not reparented: {old_id}")
    root_map = {legacy_root_id: new_root_id}
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
        source, repl_target = (
            replacement_ids.get(so, root_map.get(so, so)),
            replacement_ids.get(to, root_map.get(to, to)),
        )
        step = op.get("target_step")
        if step and so == legacy_root_id:
            source = _step_id(view, str(step))
        if step and to == legacy_root_id:
            repl_target = _step_id(view, str(step))
        if decision == "redirect":
            if source != so or repl_target != to:
                _ensure_edge(client, source, repl_target, str(op["relationship_type"]))
                _remove_edge(client, so, to)
        elif decision == "lifecycle-only":
            _remove_edge(client, so, to)
        else:
            raise DstackError(f"unknown relationship decision: {decision}")
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
                client.supersede(old_id, target)
            mapping[old_id] = target
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
        if client.show(legacy_root_id).get("status") != "closed":
            _require_open_unassigned(client, legacy_root_id)
            client.supersede(legacy_root_id, new_root_id)
        root_superseded = True
    return {
        "status": "ok",
        "legacy_root": legacy_root_id,
        "new_root": new_root_id,
        "mapping": mapping,
        "root_superseded": root_superseded,
        "decision_staging": plan.get("decision_staging", []),
    }
