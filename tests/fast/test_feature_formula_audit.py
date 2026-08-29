from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))

import dstack_feature  # noqa: E402
from dstack_formula import FormulaAuditRequired  # noqa: E402

from scripted import ScriptedClient, call  # noqa: E402


def feature_view(*, approved: bool = True) -> dict:
    return {
        "root": {
            "id": "feature-1",
            "status": "open",
            "metadata": {"dstack.approved_design_sha256": "digest"} if approved else {},
        },
        "slug": "feature",
        "current": True,
        "closed": False,
        "design_path": "docs/src/features/feature/design.md",
        "steps": {
            "specification": {"id": "spec-1", "status": "closed"},
            "approval": {"id": "approval-1", "status": "closed"},
            "implementation": {"id": "implementation-1", "status": "open"},
            "closeout": {"id": "closeout-1", "status": "open"},
        },
    }


def test_approved_stale_contract_requests_internal_semantic_audit(tmp_path: Path) -> None:
    view = feature_view()
    root = {
        "id": "feature-1",
        "metadata": {
            "dstack.approved_design_sha256": "digest",
            "dstack.created_formula_version": 8,
            "dstack.formula_version": 8,
        },
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=root),
        call("children", "implementation-1", result=[]),
    )

    with pytest.raises(FormulaAuditRequired) as raised:
        dstack_feature.require_feature_formula_current(beads, view)

    payload = raised.value.payload
    assert payload["status"] == "audit_required"
    assert payload["from_version"] == 8
    assert payload["to_version"] == 9
    assert payload["skill"] == "dstack-beads-review-feature-spec"
    assert "semantically" in payload["user_input"]
    assert "Do not regenerate or normalize" in payload["user_input"]
    beads.assert_exhausted()


def test_unapproved_feature_does_not_require_compatibility_audit(tmp_path: Path) -> None:
    view = feature_view(approved=False)
    root = {"id": "feature-1", "metadata": {"dstack.created_formula_version": 8}}
    beads = ScriptedClient(tmp_path, call("show", "feature-1", result=root))

    state = dstack_feature.feature_formula_contract_state(beads, view)

    assert state["state"] == "pending-review"
    assert state["audit_required"] is False
    beads.assert_exhausted()


def test_formula_contract_stamp_updates_active_work_not_closed_history(tmp_path: Path) -> None:
    view = feature_view()
    active = {"id": "task-active", "status": "open"}
    closed = {"id": "task-closed", "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=view["root"]),
        call("children", "implementation-1", result=[closed, active]),
        call(
            "update_many",
            ["feature-1", "spec-1", "approval-1", "implementation-1", "closeout-1", "task-active"],
            "--set-metadata",
            "dstack.formula_version=9",
            result=[],
        ),
    )

    assert dstack_feature.stamp_feature_formula_contract(beads, view) == 9
    beads.assert_exhausted()


def test_current_root_with_stale_active_task_requests_audit(tmp_path: Path) -> None:
    view = feature_view()
    current_metadata = {
        "dstack.approved_design_sha256": "digest",
        "dstack.created_formula_version": 9,
        "dstack.formula_version": 9,
    }
    view["root"]["metadata"] = dict(current_metadata)
    for step in view["steps"].values():
        step["metadata"] = {"dstack.formula_version": 9}

    active = {"id": "task-active", "status": "open", "metadata": {}}
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=view["root"]),
        call("children", "implementation-1", result=[active]),
    )

    with pytest.raises(FormulaAuditRequired) as raised:
        dstack_feature.require_feature_formula_current(beads, view)

    payload = raised.value.payload
    assert payload["from_version"] == 9
    assert payload["to_version"] == 9
    assert payload["stale_issue_ids"] == ["task-active"]
    beads.assert_exhausted()


def test_audit_complete_is_internal_no_change_cache_transition(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    view = feature_view()
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_feature, "feature_context", lambda client, selector: dict(view))
    monkeypatch.setattr(
        dstack_feature,
        "feature_authorization_state",
        lambda client, current: {"native_approved": True, "authorization_states": {}},
    )
    monkeypatch.setattr(
        dstack_feature,
        "feature_design_state",
        lambda client, current: {"design_approved": True, "approved_design_sha256": "digest"},
    )
    monkeypatch.setattr(dstack_feature, "require_approved_design", lambda current: None)
    monkeypatch.setattr(dstack_feature, "stamp_feature_formula_contract", lambda client, current: 9)
    monkeypatch.setattr(
        dstack_feature,
        "feature_formula_contract_state",
        lambda client, current: {
            "formula": "dstack-feature",
            "current_version": 9,
            "created_version": 8,
            "audited_version": 9,
            "state": "current",
            "audit_required": False,
        },
    )
    output: list[dict] = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    assert dstack_feature.cmd_feature_audit_complete(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output == [
        {
            "status": "ok",
            "feature": "feature-1",
            "formula_contract": {
                "formula": "dstack-feature",
                "current_version": 9,
                "created_version": 8,
                "audited_version": 9,
                "state": "current",
                "audit_required": False,
            },
        }
    ]
