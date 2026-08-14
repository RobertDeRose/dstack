"""Behavioral tests for the direct, finite review-state authority."""

# ruff: noqa: S603 - state labels are not passwords; tests invoke the fixed helper.

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest


ROOT = __import__("pathlib").Path(__file__).parents[1]
SCRIPT = ROOT / "skills/dstack-core/scripts/review-state.py"
PROTECTED_DOMAINS = ["security", "correctness", "validation", "accessibility", "data-loss-protection"]
REQUIRED_REVIEWERS = ["specification-clarity", "execution-readiness"]


def run(command: str, payload: Any, *, success: bool = True) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if success:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    error = json.loads(result.stderr)
    assert error["schema"] == "dstack.review-state-error.v1"
    return error


def telemetry(**changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "assignment_path_count": 2,
        "assignment_domain_count": 1,
        "elapsed_ms": None,
        "context_used_percent": None,
        "terminal_status": None,
        "replacement_cause": None,
    }
    value.update(changes)
    return value


def initial(**changes: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema": "dstack.review-state.v3",
        "reviewer_id": "specification-clarity",
        "review_issue_id": "dstack-mol-2s9-clarity-v3",
        "review_boundary_id": "feature-review-boundary",
        "reviewed_commit": "c" * 40,
        "reviewed_diff_base": "d" * 40,
        "reviewed_diff_digest": "sha256:" + "e" * 64,
        "state": "initial_active",
        "pass": "initial",
        "pending_conditions": [],
        "declared_domains": ["architecture"],
        "declared_paths": ["docs/src/architecture/index.md"],
        "declared_requirement_ids": ["FR-1"],
        "current_findings": [],
        "decision": None,
        "resolved_decision": None,
        "waiver": None,
        "partial_evidence": None,
        "redesign_replacement_count": 0,
        "infrastructure_replacement_count": {"initial": 0, "verification": 0},
        "provisional": False,
        "telemetry": telemetry(),
    }
    state.update(changes)
    return state


def finding(
    finding_id: str = "F-001",
    *,
    domain: str = "documentation",
    severity: str = "medium",
    material: bool = True,
    protected: bool | None = None,
) -> dict[str, Any]:
    if protected is None:
        protected = domain in PROTECTED_DOMAINS
    return {
        "finding_id": finding_id,
        "domain": domain,
        "severity": severity,
        "material": material,
        "protected": protected,
        "summary": f"Finding {finding_id}",
    }


def decision() -> dict[str, Any]:
    return {
        "affected_requirement_ids": ["FR-1"],
        "affected_task_ids": ["task-1"],
        "question": "Should the safe default be used?",
        "recommendation": "Use the safe default.",
        "alternatives": ["Defer the capability."],
    }


def transition(state: dict[str, Any], event: str, **data: Any) -> dict[str, Any]:
    return run("transition", {"state": state, "event": event, "data": data})["state"]


def aggregate(reviewers: list[dict[str, Any]], **changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"reviewers": reviewers, "required_reviewer_ids": REQUIRED_REVIEWERS}
    payload.update(changes)
    return run("aggregate", payload)


def approved_pair() -> list[dict[str, Any]]:
    clarity = transition(initial(), "approve")
    execution = transition(
        initial(
            reviewer_id="execution-readiness",
            review_issue_id="dstack-mol-2s9-readiness-v3",
            declared_domains=["execution"],
            declared_paths=["skills/implement-feature/SKILL.md"],
            declared_requirement_ids=["FR-2"],
        ),
        "approve",
    )
    return [clarity, execution]


def test_aggregate_accepts_exact_direct_reviewer_states() -> None:
    result = aggregate(approved_pair())
    assert result["can_close"] is True
    assert result["required_reviewer_ids"] == sorted(REQUIRED_REVIEWERS)
    assert result["reconciliation_assignment_updates"] == []


def test_aggregate_rejects_missing_duplicate_or_extra_reviewers() -> None:
    for payload in (
        {"reviewers": [approved_pair()[0]], "required_reviewer_ids": REQUIRED_REVIEWERS},
        {"reviewers": approved_pair()[:1] * 2, "required_reviewer_ids": REQUIRED_REVIEWERS},
        {"reviewers": approved_pair(), "required_reviewer_ids": ["specification-clarity"]},
    ):
        assert "reviewer" in run("aggregate", payload, success=False)["error"]


def test_aggregate_rejects_mismatched_source_boundaries() -> None:
    second = transition(
        initial(
            reviewer_id="execution-readiness",
            review_issue_id="dstack-mol-2s9-readiness-v3",
            reviewed_diff_digest="sha256:" + "f" * 64,
        ),
        "approve",
    )
    error = run(
        "aggregate",
        {"reviewers": [approved_pair()[0], second], "required_reviewer_ids": REQUIRED_REVIEWERS},
        success=False,
    )
    assert "mismatched review boundaries" in error["error"]


def test_initial_approval_is_provisional_until_complete_aggregate_closes() -> None:
    approved = approved_pair()
    assert all(item["provisional"] for item in approved)
    assert aggregate(approved)["state"] == "approved"


def test_compound_report_requires_all_findings_and_decision_resolution() -> None:
    state = transition(initial(), "report", decision=decision(), findings=[finding()])
    assert state["state"] == "decision_required"
    assert state["pending_conditions"] == ["changes_required", "decision_required"]
    error = run(
        "transition",
        {"state": state, "event": "reconcile", "data": {"resolved_conditions": ["decision_required"]}},
        success=False,
    )
    assert "pending conditions" in error["error"]

    verified = transition(
        state,
        "reconcile",
        resolved_conditions=["changes_required", "decision_required"],
        answer={
            "author": "maintainer",
            "value": "Use the recommendation",
            "boundary_digest": state["reviewed_diff_digest"],
        },
        resolved_finding_ids=["F-001"],
    )
    assert verified["state"] == "verification_active"
    assert verified["resolved_decision"]["answer"]["boundary_digest"] == verified["reviewed_diff_digest"]


def test_reconcile_binds_complete_changed_source_boundary() -> None:
    state = transition(initial(), "report", decision=decision(), findings=[finding()])
    changed = {
        "review_boundary_id": state["review_boundary_id"],
        "review_issue_id": state["review_issue_id"],
        "reviewed_commit": "1" * 40,
        "reviewed_diff_base": "2" * 40,
        "reviewed_diff_digest": "sha256:" + "3" * 64,
    }
    verified = transition(
        state,
        "reconcile",
        resolved_conditions=["changes_required", "decision_required"],
        **changed,
        answer={"author": "maintainer", "value": "Use it", "boundary_digest": changed["reviewed_diff_digest"]},
        resolved_finding_ids=["F-001"],
    )
    assert verified["review_issue_id"] == state["review_issue_id"]
    assert verified["reviewed_commit"] == changed["reviewed_commit"]
    assert verified["resolved_decision"]["answer"]["boundary_digest"] == changed["reviewed_diff_digest"]


def test_reconcile_rejects_partial_or_changed_issue_boundary() -> None:
    state = transition(initial(), "report", decision=decision(), findings=[finding()])
    error = run(
        "transition",
        {
            "state": state,
            "event": "reconcile",
            "data": {"resolved_conditions": ["changes_required", "decision_required"], "reviewed_commit": "1" * 40},
        },
        success=False,
    )
    assert "boundary is incomplete" in error["error"]

    error = run(
        "transition",
        {
            "state": state,
            "event": "reconcile",
            "data": {
                "resolved_conditions": ["changes_required", "decision_required"],
                "review_boundary_id": state["review_boundary_id"],
                "review_issue_id": "other-review",
                "reviewed_commit": "1" * 40,
                "reviewed_diff_base": "2" * 40,
                "reviewed_diff_digest": "sha256:" + "3" * 64,
            },
        },
        success=False,
    )
    assert "review issue" in error["error"]


def test_aggregate_reconciles_source_boundary_before_sibling_invalidation() -> None:
    approved = approved_pair()
    changed_boundary = {
        "review_boundary_id": "feature-review-boundary",
        "reviewed_commit": "1" * 40,
        "reviewed_diff_base": "2" * 40,
        "reviewed_diff_digest": "sha256:" + "3" * 64,
    }
    execution_with_findings = transition(
        initial(
            reviewer_id="execution-readiness",
            review_issue_id="dstack-mol-2s9-readiness-v3",
            declared_domains=["execution"],
            declared_paths=["skills/implement-feature/SKILL.md"],
            declared_requirement_ids=["FR-2"],
        ),
        "report",
        decision=None,
        findings=[finding(domain="execution")],
    )
    reconciled_execution = transition(
        execution_with_findings,
        "reconcile",
        resolved_conditions=["changes_required"],
        resolved_finding_ids=["F-001"],
        **changed_boundary,
    )
    result = aggregate(
        [approved[0], reconciled_execution],
        reconciliation_boundary=changed_boundary,
        reconciliation_changed_domains=["architecture"],
    )
    assert result["can_close"] is False
    assert result["invalidated_reviewers"] == ["specification-clarity"]
    assert result["reviewers"][0]["state"] == "verification_active"
    assert result["reviewers"][1]["reviewed_diff_digest"] == changed_boundary["reviewed_diff_digest"]
    assert result["reconciliation_boundary"] == changed_boundary
    assert result["reconciliation_assignment_updates"] == []


def test_aggregate_rejects_partial_reconciliation_boundary() -> None:
    error = run(
        "aggregate",
        {
            "reviewers": approved_pair(),
            "required_reviewer_ids": REQUIRED_REVIEWERS,
            "reconciliation_boundary": {"reviewed_commit": "1" * 40},
        },
        success=False,
    )
    assert "reconciliation boundary" in error["error"]


def test_reconciliation_changes_require_and_apply_a_changed_source_boundary() -> None:
    boundary = {
        "review_boundary_id": "feature-review-boundary",
        "reviewed_commit": "1" * 40,
        "reviewed_diff_base": "2" * 40,
        "reviewed_diff_digest": "sha256:" + "3" * 64,
    }
    for changed in (
        {"reconciliation_changed_paths": ["docs/src/architecture/index.md"]},
        {"reconciliation_changed_domains": ["architecture"]},
        {"reconciliation_changed_requirement_ids": ["FR-1"]},
    ):
        assert (
            "complete changed source boundary"
            in run(
                "aggregate",
                {"reviewers": approved_pair(), "required_reviewer_ids": REQUIRED_REVIEWERS, **changed},
                success=False,
            )["error"]
        )
        result = aggregate(approved_pair(), reconciliation_boundary=boundary, **changed)
        assert result["can_close"] is False
        assert result["invalidated_reviewers"] == ["specification-clarity"]
        assert all(item["reviewed_commit"] == boundary["reviewed_commit"] for item in result["reviewers"])

    disjoint = aggregate(
        approved_pair(),
        reconciliation_boundary=boundary,
        reconciliation_changed_paths=["docs/src/reference/index.md"],
    )
    assert disjoint["can_close"] is True


def test_post_verification_overlap_is_terminal_not_a_third_pass() -> None:
    verified = initial(state="approved", **{"pass": "verification"}, provisional=False)
    boundary = {
        "review_boundary_id": "feature-review-boundary",
        "reviewed_commit": "1" * 40,
        "reviewed_diff_base": "2" * 40,
        "reviewed_diff_digest": "sha256:" + "3" * 64,
    }
    result = aggregate(
        [verified, approved_pair()[1]],
        reconciliation_boundary=boundary,
        reconciliation_changed_domains=["architecture"],
    )
    assert result["can_close"] is False
    assert result["terminal_invalidated_reviewers"] == ["specification-clarity"]
    assert result["reviewers"][0]["state"] == "redesign_required"


@pytest.mark.parametrize("event", ["timeout", "unavailable"])
@pytest.mark.parametrize(
    ("active", "incomplete", "pass_name"),
    [
        ("initial_active", "initial_incomplete", "initial"),
        ("verification_active", "verification_incomplete", "verification"),
    ],
)
def test_infrastructure_failure_preserves_partial_evidence_and_allows_one_retry(
    event: str, active: str, incomplete: str, pass_name: str
) -> None:
    partial = {"summary": "Partial reviewer report", "artifact": "/tmp/partial.md"}
    failed = transition(
        initial(state=active, **{"pass": pass_name}), event, cause="surface polling failure", partial_evidence=partial
    )
    assert failed["state"] == incomplete
    assert failed["partial_evidence"] == partial
    retried = transition(failed, "retry")
    assert retried["state"] == active
    assert retried["infrastructure_replacement_count"][pass_name] == 1
    other_pass = ({"initial", "verification"} - {pass_name}).pop()
    assert retried["infrastructure_replacement_count"][other_pass] == 0
    assert transition(retried, event, cause="second failure", partial_evidence=partial)["state"] == "redesign_required"


@pytest.mark.parametrize("event", ["decline_retry", "retry_unavailable"])
def test_incomplete_retry_decline_or_unavailability_is_terminal(event: str) -> None:
    incomplete = transition(
        initial(), "unavailable", cause="provider", partial_evidence={"summary": "No final verdict"}
    )
    assert transition(incomplete, event)["state"] == "redesign_required"


def test_verification_findings_follow_protection_and_waiver_rules() -> None:
    verification = initial(state="verification_active", **{"pass": "verification"})
    waiver = transition(verification, "report", decision=None, findings=[finding(material=False)])
    accepted = transition(
        waiver,
        "accept_waiver",
        user="maintainer",
        rationale="Accepted limitation",
        verification="check passed",
        scope=["F-001"],
    )
    assert accepted["state"] == "approved_with_waiver"
    for domain in PROTECTED_DOMAINS:
        assert (
            transition(verification, "report", decision=None, findings=[finding(domain=domain, material=False)])[
                "state"
            ]
            == "redesign_required"
        )
    assert (
        transition(verification, "report", decision=None, findings=[finding(domain="maintainability", material=True)])[
            "state"
        ]
        == "redesign_required"
    )


def test_waiver_rejects_tampered_scope_and_refusal_is_terminal() -> None:
    waiver = transition(
        initial(state="verification_active", **{"pass": "verification"}),
        "report",
        decision=None,
        findings=[finding(material=False)],
    )
    for scope in ([], ["OTHER"]):
        error = run(
            "transition",
            {
                "state": waiver,
                "event": "accept_waiver",
                "data": {"user": "u", "rationale": "r", "verification": "v", "scope": scope},
            },
            success=False,
        )
        assert "scope" in error["error"]
    assert transition(waiver, "decline_waiver")["state"] == "redesign_required"


def test_redesign_starts_one_new_source_boundary() -> None:
    partial = {"summary": "No final report"}
    terminal = transition(
        transition(transition(initial(), "unavailable", cause="provider", partial_evidence=partial), "retry"),
        "unavailable",
        cause="replacement provider",
        partial_evidence=partial,
    )
    redesigned = transition(
        terminal,
        "redesign",
        review_boundary_id="boundary-redesigned",
        reviewed_commit="1" * 40,
        reviewed_diff_base="2" * 40,
        reviewed_diff_digest="sha256:" + "3" * 64,
        declared_domains=["architecture", "correctness"],
        declared_paths=["docs/src/architecture/index.md", "skills/dstack-core/SKILL.md"],
        declared_requirement_ids=["FR-1", "FR-2"],
    )
    assert redesigned["state"] == "initial_active"
    assert redesigned["redesign_replacement_count"] == 1
    assert redesigned["review_boundary_id"] == "boundary-redesigned"
    assert redesigned["reviewed_diff_digest"] == "sha256:" + "3" * 64
    assert redesigned["infrastructure_replacement_count"] == {"initial": 0, "verification": 0}
    assert redesigned["current_findings"] == []


def test_redesign_rejects_stale_boundary() -> None:
    terminal = initial(state="redesign_required", pending_conditions=["redesign_required"])
    replacement = {
        "review_boundary_id": "boundary-redesigned",
        "reviewed_commit": "1" * 40,
        "reviewed_diff_base": "2" * 40,
        "reviewed_diff_digest": "sha256:" + "3" * 64,
    }
    error = run(
        "transition",
        {"state": terminal, "event": "redesign", "data": {**replacement, "reviewed_commit": "c" * 40}},
        success=False,
    )
    assert "new reviewed commit" in error["error"]


def test_v1_migration_preserves_approval_as_non_approving_history() -> None:
    v1 = {
        "schema": "dstack.review-state.v1",
        "run_id": "old-run",
        "finding_domains": ["architecture"],
        "replacement_count": 1,
        "review_round": 2,
        "status": "verified",
        "disposition": "approved",
    }
    migrated = run("migrate-v1", v1)
    assert migrated["schema"] == "dstack.review-state.v3"
    assert migrated["state"] == "verification_active"
    assert migrated["redesign_replacement_count"] == 1
    assert migrated["legacy_state"] == v1
    migrated["reviewer_id"] = "specification-clarity"
    execution = transition(
        initial(
            reviewer_id="execution-readiness",
            review_issue_id="dstack-mol-2s9-readiness-v3",
            review_boundary_id=migrated["review_boundary_id"],
            reviewed_commit=migrated["reviewed_commit"],
            reviewed_diff_base=migrated["reviewed_diff_base"],
            reviewed_diff_digest=migrated["reviewed_diff_digest"],
        ),
        "approve",
    )
    assert aggregate([migrated, execution])["can_close"] is False


def test_v2_packet_state_migrates_to_non_approving_history() -> None:
    legacy = initial()
    legacy.update(
        schema="dstack.review-state.v2",
        packet_id="old-packet",
        packet_digest="sha256:" + "a" * 64,
        projection_id="old-packet:role:specification-clarity",
        projection_digest="sha256:" + "b" * 64,
        state="approved",
        provisional=True,
    )
    legacy.pop("review_issue_id")
    migrated = run("migrate-v2", legacy)
    assert migrated["schema"] == "dstack.review-state.v3"
    assert migrated["state"] == "initial_active"
    assert migrated["legacy_state"] == legacy
    assert migrated["legacy_approval_imported"] is False
    execution = transition(
        initial(
            reviewer_id="execution-readiness",
            review_issue_id="current-readiness",
            review_boundary_id=migrated["review_boundary_id"],
            reviewed_commit=migrated["reviewed_commit"],
            reviewed_diff_base=migrated["reviewed_diff_base"],
            reviewed_diff_digest=migrated["reviewed_diff_digest"],
        ),
        "approve",
    )
    assert aggregate([migrated, execution])["can_close"] is False


def test_packet_binding_is_not_part_of_new_executable_state() -> None:
    invalid = initial(packet_id="old-packet", packet_digest="sha256:" + "a" * 64)
    error = run("validate", invalid, success=False)
    assert "packet" in error["error"]


def test_active_state_rejects_evidence_before_approval() -> None:
    for evidence in ({"current_findings": [finding()]}, {"decision": decision()}):
        state = initial(**evidence)
        error = run("validate", state, success=False)
        assert "active state" in error["error"]
        assert (
            "active state"
            in run("transition", {"state": state, "event": "approve", "data": {}}, success=False)["error"]
        )


def test_telemetry_validation_rejects_invalid_values() -> None:
    state = transition(
        initial(), "record_telemetry", elapsed_ms=12_000, context_used_percent=42.5, terminal_status="completed"
    )
    assert state["telemetry"]["elapsed_ms"] == 12_000
    for key, value in (("elapsed_ms", True), ("context_used_percent", True), ("context_used_percent", 101)):
        invalid = initial()
        invalid["telemetry"][key] = value
        assert key in run("validate", invalid, success=False)["error"]


def test_third_pass_and_other_illegal_edges_fail() -> None:
    for state, event in (
        (initial(), "accept_waiver"),
        (initial(state="approved", provisional=True), "approve"),
        (initial(state="redesign_required", pending_conditions=["redesign_required"]), "retry"),
        (initial(state="verification_active", **{"pass": "verification"}), "reconcile"),
    ):
        assert (
            "illegal transition"
            in run("transition", {"state": state, "event": event, "data": {}}, success=False)["error"]
        )
