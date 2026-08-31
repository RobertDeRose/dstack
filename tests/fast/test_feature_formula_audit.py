from __future__ import annotations

import argparse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from dstack import feature as dstack_feature  # noqa: E402
from scripted import ScriptedClient, call  # noqa: E402


def feature_view(*, approved: bool = True, formula_version: int | None = None) -> dict:
    metadata = (
        {"dstack.approved_design_sha256": "digest", "dstack.created_formula_version": 8}
        if approved
        else {"dstack.created_formula_version": 8}
    )
    if formula_version is not None:
        metadata["dstack.formula_version"] = formula_version
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


def root_with_formula_version(version: int | None) -> dict:
    metadata: dict[str, object] = {
        "dstack.approved_design_sha256": "digest",
        "dstack.created_formula_version": 8,
    }
    if version is not None:
        metadata["dstack.formula_version"] = version
    return {"id": "feature-1", "status": "open", "metadata": metadata}


def test_formula_contract_state_is_version_facts_not_lifecycle_projection() -> None:
    view = feature_view(approved=False)

    facts = dstack_feature.feature_formula_contract_state(view)

    assert facts == {
        "formula": "dstack-feature",
        "current_version": 9,
        "created_version": 8,
        "audited_version": None,
    }


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


def test_audit_complete_only_stamps_root_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    view = feature_view(formula_version=8)
    beads = ScriptedClient(
        tmp_path,
        call(
            "update_many",
            ["feature-1"],
            "--set-metadata",
            "dstack.formula_version=9",
            result=[],
        ),
        call("show", "feature-1", result=root_with_formula_version(9)),
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
            },
        }
    ]
    assert [name for name, _, _ in beads.calls] == ["update_many", "show"]
    beads.assert_exhausted()
