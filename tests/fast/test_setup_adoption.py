from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_commands
import dstack_compat
import setup
from dstack_commands import DstackError
from dstacklib import FEATURE_STEPS

from scripted import ScriptedClient, call


def feature_formula() -> dict:
    return {
        "steps": [
            {"id": "specification", "type": "task", "labels": [FEATURE_STEPS["specification"]]},
            {"id": "approval", "type": "task", "labels": [FEATURE_STEPS["approval"]], "needs": ["specification"], "gate": {"type": "human"}},
            {"id": "implementation", "type": "epic", "labels": [FEATURE_STEPS["implementation"]]},
            {"id": "closeout", "type": "task", "labels": [FEATURE_STEPS["closeout"]], "needs": ["approval"], "waits_for": "children-of(implementation)"},
        ]
    }


def test_formula_contract_rejects_extra_workflow_step() -> None:
    formula = feature_formula()
    formula["steps"].append({"id": "review", "type": "task", "labels": []})
    with pytest.raises(setup.SetupError, match="exactly"):
        setup.validate_formula_contract("dstack-feature", formula)


def test_formula_contract_accepts_minimal_native_skeleton() -> None:
    setup.validate_formula_contract("dstack-feature", feature_formula())


def test_copy_formula_is_idempotent_and_requires_force(tmp_path: Path) -> None:
    source = tmp_path / "source.toml"
    destination = tmp_path / "nested/formula.toml"
    source.write_text("formula")
    assert setup.copy_formula(source, destination, force=False) == "installed"
    assert setup.copy_formula(source, destination, force=False) == "unchanged"
    destination.write_text("drift")
    with pytest.raises(setup.SetupError, match="differs"):
        setup.copy_formula(source, destination, force=False)
    assert setup.copy_formula(source, destination, force=True) == "updated"


def test_classify_legacy_item_is_explicit_about_ambiguity() -> None:
    assert dstack_compat.classify_legacy_item({"title": "Implement: code"}) == "implementation-coordinator"
    assert dstack_compat.classify_legacy_item({"title": "unrelated"}) == "ambiguous"


def test_adoption_rejects_multiple_current_slug_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, labels=["workflow:feature"], result=[
            {"id": "feature-1", "issue_type": "epic", "status": "open", "labels": ["workflow:feature", "feature:slug"]},
            {"id": "feature-2", "issue_type": "epic", "status": "open", "labels": ["workflow:feature", "feature:slug"]},
        ]),
    )
    monkeypatch.setattr(dstack_compat, "feature_context", lambda client, issue_id: {"current": True})
    with pytest.raises(DstackError, match="multiple current"):
        dstack_compat.current_feature_for_slug(beads, "slug", exclude_id="legacy")
    beads.assert_exhausted()


def test_setup_without_authorization_refuses_to_initialize(tmp_path: Path) -> None:
    with pytest.raises(setup.SetupError, match="not initialized"):
        setup.ensure_beads(tmp_path, initialize=False)


def test_legacy_repair_reports_required_changes_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beads = ScriptedClient(tmp_path, call("check_version", result="bd 1.2.2"))
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: beads)
    monkeypatch.setattr(
        setup,
        "legacy_template_artifacts",
        lambda client: [{"id": "dstack-feature.template"}],
    )
    monkeypatch.setattr(
        setup, "normalize_current_features", lambda client, force: ["feature-1"]
    )
    monkeypatch.setattr(
        setup, "normalize_current_alignments", lambda client, force: []
    )
    monkeypatch.setattr(setup, "tracked", lambda root, path: True)
    result = setup.repair_legacy(tmp_path, force=False)
    assert result == {
        "status": "repair-required",
        "template_artifacts": ["dstack-feature.template"],
        "molecule_items_to_normalize": ["feature-1"],
        "interaction_log_tracked": True,
        "interaction_log_ignore_missing": True,
    }
    beads.assert_exhausted()


def test_explicit_repair_migrates_feature_design_to_mdbook_path(tmp_path: Path) -> None:
    root = {
        "id": "feature-1",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/features/feature/design.md",
        },
    }
    beads = ScriptedClient(
        tmp_path,
        call(
            "list",
            all_statuses=True,
            labels=["workflow:feature"],
            result=[root],
        ),
        call(
            "update",
            "feature-1",
            "--set-metadata",
            "dstack.design_path=docs/src/features/feature/design.md",
            result={**root, "metadata": {**root["metadata"], "dstack.design_path": "docs/src/features/feature/design.md"}},
        ),
        call("children", "feature-1", result=[]),
    )
    assert setup.normalize_current_features(beads, force=True) == ["feature-1"]
    beads.assert_exhausted()


def test_adopt_inspect_classifies_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {"id": "legacy-1", "status": "open", "title": "Feature: Old"}
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "resolve_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "feature_context", lambda *args: {"current": False})
    monkeypatch.setattr(
        dstack_compat,
        "descendants",
        lambda *args: [{"id": "old-task", "status": "open", "title": "Implement: old"}],
    )
    output = []
    monkeypatch.setattr(dstack_compat, "emit", output.append)
    args = type("Args", (), {"root": tmp_path, "selector": "legacy-1"})()
    assert dstack_compat.cmd_adopt_inspect(args) == 0
    assert output[0]["classified"]["implementation-coordinator"][0]["id"] == "old-task"


def test_adopt_apply_rejects_noncanonical_design_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {"id": "legacy-1", "status": "open", "title": "Feature: Old"}
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "resolve_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "feature_context", lambda *args: {"current": False})
    args = type(
        "Args",
        (),
        {
            "root": tmp_path,
            "selector": "legacy-1",
            "title": None,
            "slug": "old",
            "base_branch": "main",
            "design_path": "docs/features/old/design.md",
            "remaining": [],
        },
    )()
    with pytest.raises(DstackError, match="docs/src/features/old/design.md"):
        dstack_compat.cmd_adopt_apply(args)
    beads.assert_exhausted()


def test_adopt_apply_is_idempotent_for_native_supersession(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {
        "id": "legacy-1",
        "status": "closed",
        "dependencies": [{"depends_on_id": "feature-1", "type": "superseded-by"}],
    }
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "resolve_feature", lambda *args: legacy)
    monkeypatch.setattr(
        dstack_compat,
        "feature_context",
        lambda *args: {"root": {"id": "feature-1"}, "current": True},
    )
    output = []
    monkeypatch.setattr(dstack_compat, "emit", output.append)
    args = type("Args", (), {"root": tmp_path, "selector": "legacy-1"})()
    assert dstack_compat.cmd_adopt_apply(args) == 0
    assert output[0]["already_adopted"] is True
    assert output[0]["new_root"] == "feature-1"


@pytest.mark.parametrize(
    ("blocker_kind", "destination"),
    [("task", "approval-1"), ("epic", "implementation-1")],
)
def test_external_blocker_is_preserved_on_compatible_native_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocker_kind: str,
    destination: str,
) -> None:
    source = {
        "id": "legacy-1",
        "issue_type": "epic",
        "dependencies": [{"depends_on_id": "blocker-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "feature-1", result={"id": "feature-1", "issue_type": "molecule"}),
        call(
            "children",
            "feature-1",
            result=[
                {
                    "id": "implementation-1",
                    "issue_type": "epic",
                    "labels": [FEATURE_STEPS["implementation"]],
                },
                {
                    "id": "approval-1",
                    "issue_type": "task",
                    "labels": [FEATURE_STEPS["approval"]],
                },
            ],
        ),
        call(
            "show_optional",
            "blocker-1",
            result={"id": "blocker-1", "issue_type": blocker_kind, "status": "open"},
        ),
        call("add_dependency", destination, "blocker-1", result=None),
    )
    monkeypatch.setattr(dstack_commands, "descendants", lambda *args: [])
    assert dstack_commands.preserve_external_blockers(
        beads, source, "feature-1"
    ) == ["blocker-1"]
    beads.assert_exhausted()
