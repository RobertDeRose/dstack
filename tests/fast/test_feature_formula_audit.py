from __future__ import annotations

import argparse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from dstack import feature as dstack_feature  # noqa: E402
from dstack.core import DstackError  # noqa: E402

from scripted import ScriptedClient, call  # noqa: E402


def feature_view(*, approved: bool = True) -> dict:
    metadata = {"dstack.approved_design_sha256": "digest"} if approved else {}
    return {
        "root": {"id": "feature-1", "status": "open", "metadata": metadata},
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


def test_formula_contract_state_is_version_facts_not_lifecycle_projection(tmp_path: Path) -> None:
    view = feature_view(approved=False)
    root = {"id": "feature-1", "metadata": {"dstack.created_formula_version": 8}}
    beads = ScriptedClient(tmp_path, call("show", "feature-1", result=root))

    facts = dstack_feature.feature_formula_contract_state(beads, view)

    assert facts == {
        "formula": "dstack-feature",
        "current_version": 9,
        "created_version": 8,
        "audited_version": None,
    }
    beads.assert_exhausted()


def test_stale_contract_materializes_native_blocking_audit_bead(tmp_path: Path) -> None:
    view = feature_view()
    root = {
        "id": "feature-1",
        "metadata": {
            "dstack.approved_design_sha256": "digest",
            "dstack.created_formula_version": 8,
            "dstack.formula_version": 8,
        },
    }
    audit = {
        "id": "audit-1",
        "status": "open",
        "labels": [dstack_feature.FORMULA_AUDIT_LABEL],
        "dependencies": [{"depends_on_id": "approval-1", "type": "blocks"}],
    }
    blocked_closeout = {
        "id": "closeout-1",
        "status": "open",
        "dependencies": [{"depends_on_id": "audit-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result=root),
        call("children", "feature-1", result=[]),
        call(
            "create",
            dstack_feature.FORMULA_AUDIT_TITLE,
            parent="feature-1",
            labels=[dstack_feature.FORMULA_AUDIT_LABEL],
            dependencies=["approval-1"],
            description="Review the approved feature against the current dStack feature formula contract.",
            acceptance="Close this Bead only after the semantic compatibility review is complete.",
            priority=1,
            result=audit,
        ),
        call("children", "implementation-1", result=[]),
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open", "dependencies": []}),
        call("add_dependency", "closeout-1", "audit-1"),
        call("show", "closeout-1", result=blocked_closeout),
        call("show", "audit-1", result=audit),
    )

    with pytest.raises(DstackError, match="native Bead audit-1"):
        dstack_feature.require_feature_formula_current(beads, view)

    beads.assert_exhausted()


def test_formula_audit_blocks_existing_open_implementation_work(tmp_path: Path) -> None:
    view = feature_view()
    audit = {
        "id": "audit-1",
        "status": "open",
        "labels": [dstack_feature.FORMULA_AUDIT_LABEL],
        "dependencies": [{"depends_on_id": "approval-1", "type": "blocks"}],
    }
    task = {"id": "task-1", "status": "open", "labels": ["dstack:work:implementation"], "dependencies": []}
    blocked_task = {
        **task,
        "dependencies": [{"depends_on_id": "audit-1", "type": "blocks"}],
    }
    closeout = {
        "id": "closeout-1",
        "status": "open",
        "dependencies": [{"depends_on_id": "audit-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("children", "feature-1", result=[audit]),
        call("children", "implementation-1", result=[task]),
        call("show", "closeout-1", result=closeout),
        call("add_dependency", "task-1", "audit-1"),
        call("show", "task-1", result=blocked_task),
        call("show", "audit-1", result=audit),
    )

    assert dstack_feature.ensure_feature_formula_audit(beads, view) == audit
    beads.assert_exhausted()


def test_formula_contract_stamp_updates_only_feature_root(tmp_path: Path) -> None:
    view = feature_view()
    beads = ScriptedClient(
        tmp_path,
        call(
            "update_many",
            ["feature-1"],
            "--set-metadata",
            "dstack.formula_version=9",
            result=[],
        ),
    )

    assert dstack_feature.stamp_feature_formula_contract(beads, view) == 9
    beads.assert_exhausted()


def test_audit_complete_closes_native_bead_then_stamps_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    view = feature_view()
    audit = {"id": "audit-1", "status": "open", "labels": [dstack_feature.FORMULA_AUDIT_LABEL]}
    closed_audit = {**audit, "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("close", "audit-1", "Formula compatibility review completed", result=closed_audit),
    )
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
    states = iter(
        [
            {
                "formula": "dstack-feature",
                "current_version": 9,
                "created_version": 8,
                "audited_version": 8,
            },
            {
                "formula": "dstack-feature",
                "current_version": 9,
                "created_version": 8,
                "audited_version": 9,
            },
        ]
    )
    monkeypatch.setattr(dstack_feature, "feature_formula_contract_state", lambda client, current: next(states))
    monkeypatch.setattr(dstack_feature, "feature_formula_audit_bead", lambda client, current: audit)
    monkeypatch.setattr(
        dstack_feature,
        "claim_ready_work",
        lambda client, *, parent_id, label, requested_id=None: audit,
    )
    monkeypatch.setattr(dstack_feature, "stamp_feature_formula_contract", lambda client, current: 9)
    output: list[dict] = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    assert dstack_feature.cmd_feature_audit_complete(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output == [
        {
            "status": "ok",
            "feature": "feature-1",
            "audit": closed_audit,
            "formula_contract": {
                "formula": "dstack-feature",
                "current_version": 9,
                "created_version": 8,
                "audited_version": 9,
            },
        }
    ]
    beads.assert_exhausted()
