#!/usr/bin/env python3
# ruff: noqa: S105 - review pass names are state labels, not passwords.
"""Validate and transition finite direct-review state without side effects."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from typing import Any, NoReturn


SCHEMA = "dstack.review-state.v3"
ERROR_SCHEMA = "dstack.review-state-error.v1"
INITIAL_PASS = "initial"
VERIFICATION_PASS = "verification"
PASSES = (INITIAL_PASS, VERIFICATION_PASS)
ACTIVE_BY_PASS = {INITIAL_PASS: "initial_active", VERIFICATION_PASS: "verification_active"}
INCOMPLETE_BY_PASS = {INITIAL_PASS: "initial_incomplete", VERIFICATION_PASS: "verification_incomplete"}
PROTECTED_DOMAINS = frozenset({"security", "correctness", "validation", "accessibility", "data-loss-protection"})
DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IDENTITY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
BOUNDARY_FIELDS = ("review_boundary_id", "reviewed_commit", "reviewed_diff_base", "reviewed_diff_digest")
AGGREGATE_BOUNDARY_FIELDS = BOUNDARY_FIELDS
RETIRED_PACKET_FIELDS = frozenset({"packet_id", "packet_digest", "projection_id", "projection_digest"})
SEVERITIES = frozenset({"blocking", "high", "medium", "low"})
APPROVED_STATES = frozenset({"approved", "approved_with_waiver"})
TERMINAL_STATES = APPROVED_STATES | {"redesign_required"}
KNOWN_STATES = frozenset(
    {
        "initial_active",
        "changes_required",
        "decision_required",
        "initial_incomplete",
        "verification_active",
        "verification_incomplete",
        *TERMINAL_STATES,
        "waiver_required",
    }
)


class StateError(ValueError):
    """Raised when review state is invalid or a transition is illegal."""


def fail(message: str) -> NoReturn:
    print(json.dumps({"schema": ERROR_SCHEMA, "error": message}, separators=(",", ":")), file=sys.stderr)
    raise SystemExit(2)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StateError(message)


def is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def require_string_list(value: Any, name: str, *, allow_empty: bool = True) -> list[str]:
    require(isinstance(value, list), f"{name} must be a list")
    items = value if isinstance(value, list) else []
    require(all(isinstance(item, str) and item for item in items), f"{name} contains an invalid value")
    require(len(items) == len(set(items)), f"{name} contains duplicates")
    require(allow_empty or bool(items), f"{name} must not be empty")
    return items


def validate_telemetry(value: Any) -> None:
    require(isinstance(value, dict), "telemetry must be an object")
    telemetry = value if isinstance(value, dict) else {}
    required = {
        "assignment_path_count",
        "assignment_domain_count",
        "elapsed_ms",
        "context_used_percent",
        "terminal_status",
        "replacement_cause",
    }
    require(required <= telemetry.keys(), f"telemetry is missing fields: {sorted(required - telemetry.keys())}")
    for key in ("assignment_path_count", "assignment_domain_count"):
        count = telemetry[key]
        require(count is None or is_non_negative_int(count), f"telemetry.{key} is invalid")
    elapsed = telemetry["elapsed_ms"]
    require(elapsed is None or is_non_negative_int(elapsed), "telemetry.elapsed_ms is invalid")
    context = telemetry["context_used_percent"]
    require(
        context is None
        or (isinstance(context, (int, float)) and not isinstance(context, bool) and 0 <= context <= 100),
        "telemetry.context_used_percent must be between 0 and 100",
    )
    for key in ("terminal_status", "replacement_cause"):
        require(
            telemetry[key] is None or (isinstance(telemetry[key], str) and telemetry[key]),
            f"telemetry.{key} is invalid",
        )


def validate_finding(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "finding must be an object")
    finding = value if isinstance(value, dict) else {}
    for key in ("finding_id", "domain", "severity", "summary"):
        require(isinstance(finding.get(key), str) and finding[key], f"finding.{key} is required")
    require(DOMAIN_PATTERN.fullmatch(finding["domain"]) is not None, "finding.domain must be lowercase kebab-case")
    require(finding["severity"] in SEVERITIES, "finding.severity is unknown")
    require(isinstance(finding.get("material"), bool), "finding.material must be boolean")
    require(isinstance(finding.get("protected"), bool), "finding.protected must be boolean")
    expected_protection = finding["domain"] in PROTECTED_DOMAINS
    require(finding["protected"] is expected_protection, "finding.protected conflicts with its domain")
    return finding


def validate_findings(value: Any) -> list[dict[str, Any]]:
    require(isinstance(value, list), "current_findings must be a list")
    findings = [validate_finding(item) for item in value if isinstance(item, dict)]
    require(len(findings) == len(value), "current_findings contains a non-object")
    ids = [item["finding_id"] for item in findings]
    require(len(ids) == len(set(ids)), "current_findings repeats a finding_id")
    return findings


def validate_digest(value: Any, name: str) -> str:
    require(isinstance(value, str) and DIGEST_PATTERN.fullmatch(value) is not None, f"{name} is invalid")
    return value if isinstance(value, str) else ""


def validate_decision(
    value: Any, *, reviewed_diff_digest: str | None = None, require_answer: bool = False
) -> dict[str, Any]:
    require(isinstance(value, dict), "decision must be an object")
    decision = value if isinstance(value, dict) else {}
    require_string_list(
        decision.get("affected_requirement_ids"), "decision.affected_requirement_ids", allow_empty=False
    )
    require_string_list(decision.get("affected_task_ids"), "decision.affected_task_ids", allow_empty=False)
    for key in ("question", "recommendation"):
        require(isinstance(decision.get(key), str) and decision[key], f"decision.{key} is required")
    require_string_list(decision.get("alternatives"), "decision.alternatives", allow_empty=False)
    answer = decision.get("answer")
    if require_answer:
        require(answer is not None, "decision answer is required")
    if answer is not None:
        require(isinstance(answer, dict), "decision.answer must be an object")
        answer_dict = answer if isinstance(answer, dict) else {}
        for key in ("author", "value"):
            require(isinstance(answer_dict.get(key), str) and answer_dict[key], f"decision.answer.{key} is required")
        boundary_digest = validate_digest(answer_dict.get("boundary_digest"), "decision.answer.boundary_digest")
        if reviewed_diff_digest is not None:
            require(
                boundary_digest == reviewed_diff_digest,
                "decision.answer.boundary_digest does not match reviewed diff",
            )
    return decision


def validate_partial_evidence(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    require(isinstance(value, dict), "partial_evidence must be an object")
    evidence = value if isinstance(value, dict) else {}
    require(isinstance(evidence.get("summary"), str) and evidence["summary"], "partial_evidence.summary is required")
    return evidence


def validate_waiver(value: Any, findings: list[dict[str, Any]]) -> dict[str, Any]:
    require(isinstance(value, dict), "waiver must be an object")
    waiver = value if isinstance(value, dict) else {}
    for key in ("user", "rationale", "verification"):
        require(isinstance(waiver.get(key), str) and waiver[key], f"waiver.{key} is required")
    scope = require_string_list(waiver.get("scope"), "waiver.scope", allow_empty=False)
    require(
        bool(findings) and all(not item["protected"] and not item["material"] for item in findings),
        "waiver findings must all be eligible",
    )
    eligible = {item["finding_id"] for item in findings}
    require(set(scope) == eligible, "waiver.scope must equal all eligible findings")
    return waiver


def validate_review_boundary(state: dict[str, Any]) -> None:
    for key in BOUNDARY_FIELDS:
        require(isinstance(state.get(key), str) and state[key], f"review boundary {key} is required")
    require(
        IDENTITY_PATTERN.fullmatch(state["review_boundary_id"]) is not None,
        "review boundary review_boundary_id is invalid",
    )
    for key in ("reviewed_commit", "reviewed_diff_base"):
        require(COMMIT_PATTERN.fullmatch(state[key]) is not None, f"review boundary {key} is invalid")
    require(
        DIGEST_PATTERN.fullmatch(state["reviewed_diff_digest"]) is not None,
        "review boundary reviewed_diff_digest is invalid",
    )


def validate_state(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "state must be an object")
    state = value if isinstance(value, dict) else {}
    require(state.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    retired = RETIRED_PACKET_FIELDS & state.keys()
    require(not retired, f"packet fields are retired from executable state: {sorted(retired)}")
    require(isinstance(state.get("reviewer_id"), str) and state["reviewer_id"], "reviewer_id is required")
    require(isinstance(state.get("review_issue_id"), str) and state["review_issue_id"], "review_issue_id is required")
    require(IDENTITY_PATTERN.fullmatch(state["review_issue_id"]) is not None, "review_issue_id is invalid")
    require(state.get("state") in KNOWN_STATES, "state is unknown")
    require(state.get("pass") in PASSES, "pass must be initial or verification")
    validate_review_boundary(state)
    pending = require_string_list(state.get("pending_conditions"), "pending_conditions")
    require_string_list(state.get("declared_domains"), "declared_domains", allow_empty=False)
    require_string_list(state.get("declared_paths"), "declared_paths")
    require_string_list(state.get("declared_requirement_ids"), "declared_requirement_ids")
    findings = validate_findings(state.get("current_findings"))
    decision = state.get("decision")
    if decision is not None:
        validate_decision(decision, reviewed_diff_digest=state["reviewed_diff_digest"])
    resolved_decision = state.get("resolved_decision")
    if resolved_decision is not None:
        validate_decision(resolved_decision, reviewed_diff_digest=state["reviewed_diff_digest"], require_answer=True)
    waiver = state.get("waiver")
    validate_partial_evidence(state.get("partial_evidence"))
    redesign = state.get("redesign_replacement_count")
    require(redesign in (0, 1) and not isinstance(redesign, bool), "redesign_replacement_count must be zero or one")
    infrastructure = state.get("infrastructure_replacement_count")
    require(isinstance(infrastructure, dict), "infrastructure_replacement_count must be an object")
    counts = infrastructure if isinstance(infrastructure, dict) else {}
    require(set(counts) == set(PASSES), "infrastructure_replacement_count must contain both passes")
    require(
        all(counts[item] in (0, 1) and not isinstance(counts[item], bool) for item in PASSES),
        "infrastructure counters must be zero or one",
    )
    require(isinstance(state.get("provisional"), bool), "provisional must be boolean")
    require(
        isinstance(state.get("resolved_decision"), (dict, type(None))), "resolved_decision must be an object or null"
    )
    validate_telemetry(state.get("telemetry"))

    current = state["state"]
    current_pass = state["pass"]
    if current == "initial_active":
        require(
            current_pass == INITIAL_PASS
            and not pending
            and not state["provisional"]
            and not findings
            and decision is None
            and waiver is None,
            "initial_active is incoherent active state",
        )
    elif current == "verification_active":
        require(
            current_pass == VERIFICATION_PASS
            and not pending
            and not state["provisional"]
            and not findings
            and decision is None
            and waiver is None,
            "verification_active is incoherent active state",
        )
    elif current == "approved":
        expected_provisional = current_pass == INITIAL_PASS
        require(state["provisional"] is expected_provisional and not pending, "approved state is incoherent")
        require(not findings and decision is None and waiver is None, "approved state retains unresolved evidence")
    elif current == "approved_with_waiver":
        require(
            current_pass == VERIFICATION_PASS and not state["provisional"] and not pending,
            "waiver approval is incoherent",
        )
        require(decision is None, "waiver approval retains an unresolved decision")
        validate_waiver(waiver, findings)
    elif current in INCOMPLETE_BY_PASS.values():
        require(current == INCOMPLETE_BY_PASS[current_pass], "incomplete state is incoherent")
        require(pending in (["timeout"], ["unavailable"]), "incomplete pending condition is invalid")
        require(counts[current_pass] == 0, "incomplete state cannot retain a spent infrastructure counter")
        require(state["partial_evidence"] is not None, "incomplete state requires partial_evidence")
    elif current == "waiver_required":
        require(current_pass == VERIFICATION_PASS and pending == ["waiver_required"], "waiver_required is incoherent")
        require(
            bool(findings) and all(not item["material"] and not item["protected"] for item in findings),
            "waiver findings are ineligible",
        )
    elif current == "decision_required":
        require("decision_required" in pending and decision is not None, "decision_required state is incoherent")
        require(
            ("changes_required" in pending) if findings else ("changes_required" not in pending),
            "decision_required findings are incoherent",
        )
    elif current == "changes_required":
        require(
            pending == ["changes_required"] and bool(findings) and decision is None,
            "changes_required state is incoherent",
        )
    elif current == "redesign_required":
        require(pending == ["redesign_required"] and not state["provisional"], "redesign_required is incoherent")
    if current_pass == VERIFICATION_PASS:
        require(
            current not in {"initial_active", "initial_incomplete", "decision_required", "changes_required"},
            "verification pass state is incoherent",
        )
    return state


def finding_is_material(finding: dict[str, Any]) -> bool:
    return finding["protected"] or finding["material"]


def report(state: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    findings = validate_findings(data.get("findings", []))
    decision_value = data.get("decision")
    decision = (
        None
        if decision_value is None
        else validate_decision(decision_value, reviewed_diff_digest=state["reviewed_diff_digest"])
    )
    state["current_findings"] = copy.deepcopy(findings)
    state["decision"] = copy.deepcopy(decision)
    state["waiver"] = None
    if state["pass"] == VERIFICATION_PASS:
        require(decision is None, "verification report cannot introduce an unresolved decision")
        if not findings:
            state.update(state="approved", pending_conditions=[], provisional=False)
        elif any(finding_is_material(item) for item in findings):
            state.update(state="redesign_required", pending_conditions=["redesign_required"], provisional=False)
        else:
            state.update(state="waiver_required", pending_conditions=["waiver_required"], provisional=False)
        return validate_state(state)
    pending: list[str] = []
    if findings:
        pending.append("changes_required")
    if decision is not None:
        pending.append("decision_required")
    require(bool(pending), "initial report must contain findings or decision")
    state["pending_conditions"] = sorted(pending)
    state["state"] = "decision_required" if decision is not None else "changes_required"
    state["provisional"] = False
    return validate_state(state)


def transition(state_value: Any, event: Any, data_value: Any) -> dict[str, Any]:
    state = copy.deepcopy(validate_state(state_value))
    require(isinstance(event, str) and event, "event is required")
    require(isinstance(data_value, dict), "event data must be an object")
    data = data_value if isinstance(data_value, dict) else {}
    current = state["state"]
    current_pass = state["pass"]

    if event == "record_telemetry" and current not in TERMINAL_STATES:
        allowed = {
            "assignment_path_count",
            "assignment_domain_count",
            "elapsed_ms",
            "context_used_percent",
            "terminal_status",
            "replacement_cause",
        }
        unknown = set(data) - allowed
        require(not unknown, f"unknown telemetry fields: {sorted(unknown)}")
        state["telemetry"].update(data)
        return validate_state(state)
    if current == "redesign_required" and event == "redesign":
        require(state["redesign_replacement_count"] == 0, "redesign replacement count is already spent")
        provided = set(data) & set(BOUNDARY_FIELDS)
        require(provided == set(BOUNDARY_FIELDS), "redesign requires complete source boundary")
        replacement = {key: data[key] for key in BOUNDARY_FIELDS}
        require(
            replacement["review_boundary_id"] != state["review_boundary_id"], "redesign requires a new review boundary"
        )
        require(replacement["reviewed_commit"] != state["reviewed_commit"], "redesign requires a new reviewed commit")
        require(
            replacement["reviewed_diff_digest"] != state["reviewed_diff_digest"],
            "redesign requires a new reviewed diff",
        )
        for key, value in replacement.items():
            require(isinstance(value, str) and value, f"redesign requires {key}")
        if "review_issue_id" in data:
            require(data["review_issue_id"] == state["review_issue_id"], "redesign cannot change review issue")
        validate_review_boundary({**state, **replacement})
        state.update(replacement)
        for field, allow_empty in (
            ("declared_domains", False),
            ("declared_paths", True),
            ("declared_requirement_ids", True),
        ):
            if field in data:
                state[field] = require_string_list(data[field], field, allow_empty=allow_empty)
        replacement_telemetry = data.get("telemetry")
        if replacement_telemetry is not None:
            validate_telemetry(replacement_telemetry)
            state["telemetry"] = copy.deepcopy(replacement_telemetry)
        else:
            state["telemetry"].update(
                elapsed_ms=None, context_used_percent=None, terminal_status=None, replacement_cause=None
            )
        state.update(
            state="initial_active",
            pending_conditions=[],
            current_findings=[],
            decision=None,
            resolved_decision=None,
            waiver=None,
            partial_evidence=None,
            redesign_replacement_count=1,
            infrastructure_replacement_count={"initial": 0, "verification": 0},
            provisional=False,
        )
        state["pass"] = INITIAL_PASS
        state.pop("resolved_finding_ids", None)
        return validate_state(state)
    if current == ACTIVE_BY_PASS[current_pass] and event == "approve":
        require(
            not state["current_findings"] and state["decision"] is None and state["waiver"] is None,
            "cannot approve active state with unresolved evidence",
        )
        state.update(state="approved", pending_conditions=[], provisional=current_pass == INITIAL_PASS)
        return validate_state(state)
    if current == ACTIVE_BY_PASS[current_pass] and event == "report":
        return report(state, data)
    if current == ACTIVE_BY_PASS[current_pass] and event in {"timeout", "unavailable"}:
        partial = validate_partial_evidence(data.get("partial_evidence"))
        require(partial is not None, f"{event} requires partial_evidence")
        cause = data.get("cause")
        require(isinstance(cause, str) and cause, f"{event} requires a string cause")
        if state["infrastructure_replacement_count"][current_pass] == 1:
            state.update(state="redesign_required", pending_conditions=["redesign_required"], provisional=False)
        else:
            state.update(state=INCOMPLETE_BY_PASS[current_pass], pending_conditions=[event], provisional=False)
        state["partial_evidence"] = partial
        state["telemetry"].update(terminal_status=event, replacement_cause=cause)
        return validate_state(state)
    if current == INCOMPLETE_BY_PASS[current_pass] and event == "retry":
        state["infrastructure_replacement_count"][current_pass] = 1
        state.update(state=ACTIVE_BY_PASS[current_pass], pending_conditions=[], provisional=False)
        state["telemetry"].update(terminal_status=None, replacement_cause=None)
        return validate_state(state)
    if current == INCOMPLETE_BY_PASS[current_pass] and event in {"decline_retry", "retry_unavailable"}:
        state.update(state="redesign_required", pending_conditions=["redesign_required"], provisional=False)
        return validate_state(state)
    if current in {"decision_required", "changes_required"} and event == "reconcile":
        provided = set(data) & set(BOUNDARY_FIELDS)
        if provided:
            require(provided == set(BOUNDARY_FIELDS), "reconcile source boundary is incomplete")
            replacement = {key: data[key] for key in BOUNDARY_FIELDS}
            require(
                replacement["review_boundary_id"] == state["review_boundary_id"],
                "reconcile cannot change review_boundary_id",
            )
            validate_review_boundary({**state, **replacement})
            require(
                any(replacement[key] != state[key] for key in BOUNDARY_FIELDS),
                "reconcile requires a changed source boundary",
            )
            state.update(replacement)
        if "review_issue_id" in data:
            require(data["review_issue_id"] == state["review_issue_id"], "reconcile cannot change review issue")
        resolved_value = data.get("resolved_conditions")
        resolved = require_string_list(resolved_value, "resolved_conditions", allow_empty=False)
        missing = set(state["pending_conditions"]) - set(resolved)
        require(not missing, f"pending conditions remain unresolved: {sorted(missing)}")
        if "decision_required" in state["pending_conditions"]:
            answer_value = data.get("answer")
            require(isinstance(answer_value, dict), "decision answer is required")
            resolved_decision = copy.deepcopy(state["decision"])
            resolved_decision["answer"] = copy.deepcopy(answer_value)
            validate_decision(
                resolved_decision, reviewed_diff_digest=state["reviewed_diff_digest"], require_answer=True
            )
            state["resolved_decision"] = resolved_decision
            state["decision"]["answer"] = answer_value
        if "changes_required" in state["pending_conditions"]:
            resolved_ids = require_string_list(
                data.get("resolved_finding_ids"), "resolved_finding_ids", allow_empty=False
            )
            expected_ids = [item["finding_id"] for item in state["current_findings"]]
            require(set(resolved_ids) == set(expected_ids), "resolved_finding_ids must match current findings")
            state["resolved_finding_ids"] = resolved_ids
            state["current_findings"] = []
        require(not state["current_findings"], "verification cannot start with unresolved findings")
        if "decision_required" in state["pending_conditions"]:
            state["decision"] = None
        require(state["decision"] is None, "verification cannot start with an unresolved decision")
        state.update(state="verification_active", pending_conditions=[], provisional=False)
        state["pass"] = VERIFICATION_PASS
        return validate_state(state)
    if current == "waiver_required" and event == "accept_waiver":
        waiver = validate_waiver(data, state["current_findings"])
        state["waiver"] = copy.deepcopy(waiver)
        state.update(state="approved_with_waiver", pending_conditions=[], provisional=False)
        return validate_state(state)
    if current == "waiver_required" and event == "decline_waiver":
        state.update(state="redesign_required", pending_conditions=["redesign_required"], provisional=False)
        return validate_state(state)
    message = f"illegal transition: {current} --{event}-->"
    raise StateError(message)


def validate_aggregate_boundary(value: Any) -> dict[str, str]:
    require(isinstance(value, dict), "reconciliation_boundary must be an object")
    boundary = value if isinstance(value, dict) else {}
    require(
        set(boundary) == set(AGGREGATE_BOUNDARY_FIELDS), "reconciliation boundary is incomplete or has unknown fields"
    )
    result = {key: boundary[key] for key in AGGREGATE_BOUNDARY_FIELDS}
    validate_review_boundary(result)
    return result


def aggregate_boundary_tuple(value: dict[str, Any]) -> tuple[str, ...]:
    return tuple(value[key] for key in AGGREGATE_BOUNDARY_FIELDS)


def apply_aggregate_reconciliation(reviewers: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, str] | None:
    boundary_value = data.get("reconciliation_boundary")
    require(
        "reconciliation_assignment_updates" not in data, "assignment updates are transient and must not be persisted"
    )
    if boundary_value is None:
        return None
    boundary = validate_aggregate_boundary(boundary_value)
    target_tuple = aggregate_boundary_tuple(boundary)
    current_boundary_ids = {item["review_boundary_id"] for item in reviewers}
    require(
        len(current_boundary_ids) == 1 and current_boundary_ids == {boundary["review_boundary_id"]},
        "reconciliation boundary changes review_boundary_id",
    )
    current_tuples = {aggregate_boundary_tuple(item) for item in reviewers}
    require(len(current_tuples - {target_tuple}) <= 1, "aggregate reviewers have multiple stale review boundaries")
    require(
        any(aggregate_boundary_tuple(item) != target_tuple for item in reviewers),
        "reconciliation boundary is unchanged",
    )
    for reviewer in reviewers:
        reviewer.update(boundary)
        validate_state(reviewer)
    return boundary


def aggregate(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, dict), "aggregate payload must be an object")
    data = payload if isinstance(payload, dict) else {}
    reviewers_value = data.get("reviewers")
    require(isinstance(reviewers_value, list) and reviewers_value, "aggregate requires reviewers")
    reviewer_items = reviewers_value if isinstance(reviewers_value, list) else []
    reviewers = [copy.deepcopy(validate_state(item)) for item in reviewer_items]
    required_ids = require_string_list(data.get("required_reviewer_ids"), "required_reviewer_ids", allow_empty=False)
    actual_ids = [item["reviewer_id"] for item in reviewers]
    require(len(actual_ids) == len(set(actual_ids)), "aggregate reviewer IDs must be unique")
    require(set(actual_ids) == set(required_ids), "aggregate reviewers must exactly match required reviewer IDs")
    require(len(actual_ids) == len(required_ids), "aggregate contains duplicate or extra reviewers")
    reconciled_boundary = apply_aggregate_reconciliation(reviewers, data)
    boundaries = {aggregate_boundary_tuple(item) for item in reviewers}
    require(len(boundaries) == 1, "aggregate reviewers have mismatched review boundaries")
    changed_paths = require_string_list(data.get("reconciliation_changed_paths", []), "reconciliation_changed_paths")
    changed_domains = require_string_list(
        data.get("reconciliation_changed_domains", []), "reconciliation_changed_domains"
    )
    changed_requirements = require_string_list(
        data.get("reconciliation_changed_requirement_ids", []), "reconciliation_changed_requirement_ids"
    )
    require(
        not (changed_paths or changed_domains or changed_requirements) or reconciled_boundary is not None,
        "reconciliation changes require a complete changed source boundary",
    )
    invalidated: list[str] = []
    terminal_invalidated: list[str] = []
    for reviewer in reviewers:
        overlaps = (
            bool(set(reviewer["declared_paths"]) & set(changed_paths))
            or bool(set(reviewer["declared_domains"]) & set(changed_domains))
            or bool(set(reviewer["declared_requirement_ids"]) & set(changed_requirements))
        )
        if reviewer["state"] in APPROVED_STATES and overlaps:
            if reviewer["state"] == "approved" and reviewer["pass"] == INITIAL_PASS and reviewer["provisional"]:
                reviewer.update(state="verification_active", provisional=False)
                reviewer["pass"] = VERIFICATION_PASS
                invalidated.append(reviewer["reviewer_id"])
            else:
                reviewer.update(state="redesign_required", pending_conditions=["redesign_required"], provisional=False)
                terminal_invalidated.append(reviewer["reviewer_id"])
            validate_state(reviewer)
    can_close = all(item["state"] in APPROVED_STATES for item in reviewers)
    pending = sorted({condition for item in reviewers for condition in item["pending_conditions"]})
    return {
        "schema": "dstack.review-aggregate.v2",
        "state": "approved" if can_close else "blocked",
        "can_close": can_close,
        "required_reviewer_ids": sorted(required_ids),
        "reviewers": reviewers,
        "pending_conditions": pending,
        "invalidated_reviewers": sorted(invalidated),
        "terminal_invalidated_reviewers": sorted(terminal_invalidated),
        "reconciliation_boundary": reconciled_boundary,
        "reconciliation_assignment_updates": [],
        "reconciliation_change_set": {
            "paths": changed_paths,
            "domains": changed_domains,
            "requirement_ids": changed_requirements,
        },
    }


def migrate_v2(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "v2 state must be an object")
    legacy = value if isinstance(value, dict) else {}
    require(legacy.get("schema") == "dstack.review-state.v2", "input is not dstack.review-state.v2")
    for key in ("reviewer_id", *BOUNDARY_FIELDS, *RETIRED_PACKET_FIELDS):
        require(isinstance(legacy.get(key), str) and legacy[key], f"v2 {key} is required")
    validate_review_boundary(legacy)
    for key in RETIRED_PACKET_FIELDS:
        pattern = DIGEST_PATTERN if key.endswith("digest") else IDENTITY_PATTERN
        require(pattern.fullmatch(legacy[key]) is not None, f"v2 {key} is invalid")
    pass_value = legacy.get("pass")
    require(pass_value in PASSES, "v2 pass must be initial or verification")
    pass_name = pass_value if isinstance(pass_value, str) else INITIAL_PASS
    domains = require_string_list(legacy.get("declared_domains"), "v2 declared_domains", allow_empty=False)
    paths = require_string_list(legacy.get("declared_paths", []), "v2 declared_paths")
    requirements = require_string_list(legacy.get("declared_requirement_ids", []), "v2 declared_requirement_ids")
    redesign = legacy.get("redesign_replacement_count", 0)
    require(redesign in (0, 1) and not isinstance(redesign, bool), "v2 redesign count must be zero or one")
    migrated = {
        "schema": SCHEMA,
        "reviewer_id": legacy["reviewer_id"],
        "review_issue_id": f"legacy-{legacy['reviewer_id']}",
        **{key: legacy[key] for key in BOUNDARY_FIELDS},
        "state": ACTIVE_BY_PASS[pass_name],
        "pass": pass_name,
        "pending_conditions": [],
        "declared_domains": domains,
        "declared_paths": paths,
        "declared_requirement_ids": requirements,
        "current_findings": [],
        "decision": None,
        "resolved_decision": None,
        "waiver": None,
        "partial_evidence": None,
        "redesign_replacement_count": redesign,
        "infrastructure_replacement_count": {INITIAL_PASS: 0, VERIFICATION_PASS: 0},
        "provisional": False,
        "telemetry": {
            "assignment_path_count": None,
            "assignment_domain_count": None,
            "elapsed_ms": None,
            "context_used_percent": None,
            "terminal_status": None,
            "replacement_cause": None,
        },
        "legacy_state": legacy,
        "legacy_approval_imported": False,
    }
    return validate_state(migrated)


def migrate_v1(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "v1 state must be an object")
    legacy = value if isinstance(value, dict) else {}
    require(legacy.get("schema") == "dstack.review-state.v1", "input is not dstack.review-state.v1")
    require(isinstance(legacy.get("run_id"), str) and legacy["run_id"], "v1 run_id is required")
    redesign = legacy.get("replacement_count", 0)
    require(redesign in (0, 1) and not isinstance(redesign, bool), "v1 replacement_count must be zero or one")
    round_value = legacy.get("review_round", 1)
    require(
        isinstance(round_value, int) and not isinstance(round_value, bool) and round_value > 0,
        "v1 review_round is invalid",
    )
    domains = require_string_list(legacy.get("finding_domains", []), "v1 finding_domains")
    pass_name = VERIFICATION_PASS if round_value > 1 else INITIAL_PASS
    migrated = {
        "schema": SCHEMA,
        "reviewer_id": legacy["run_id"],
        "review_issue_id": f"legacy-{legacy['run_id']}",
        "review_boundary_id": f"legacy-{legacy['run_id']}",
        "reviewed_commit": "0" * 40,
        "reviewed_diff_base": "0" * 40,
        "reviewed_diff_digest": "sha256:" + "0" * 64,
        "state": ACTIVE_BY_PASS[pass_name],
        "pass": pass_name,
        "pending_conditions": [],
        "declared_domains": domains or ["task"],
        "declared_paths": [],
        "declared_requirement_ids": [],
        "current_findings": [],
        "decision": None,
        "resolved_decision": None,
        "waiver": None,
        "partial_evidence": None,
        "redesign_replacement_count": redesign,
        "infrastructure_replacement_count": {INITIAL_PASS: 0, VERIFICATION_PASS: 0},
        "provisional": False,
        "telemetry": {
            "assignment_path_count": None,
            "assignment_domain_count": None,
            "elapsed_ms": None,
            "context_used_percent": None,
            "terminal_status": None,
            "replacement_cause": None,
        },
        "legacy_state": legacy,
        "legacy_approval_imported": False,
    }
    return validate_state(migrated)


def read_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as error:
        message = f"invalid JSON input: {error.msg}"
        raise StateError(message) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "transition", "aggregate", "migrate-v1", "migrate-v2"))
    args = parser.parse_args()
    try:
        payload = read_json()
        if args.command == "validate":
            output: Any = validate_state(payload)
        elif args.command == "transition":
            require(isinstance(payload, dict), "transition payload must be an object")
            event_data = payload.get("data")
            require(isinstance(event_data, dict), "event data must be an object")
            output = {
                "schema": "dstack.review-transition.v2",
                "state": transition(payload.get("state"), payload.get("event"), event_data),
            }
        elif args.command == "aggregate":
            output = aggregate(payload)
        elif args.command == "migrate-v2":
            output = migrate_v2(payload)
        else:
            output = migrate_v1(payload)
    except (StateError, TypeError, ValueError) as error:
        fail(str(error))
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
