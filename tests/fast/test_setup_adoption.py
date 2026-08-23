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


def test_install_initializes_and_reports_canonical_documentation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Client:
        def check_version(self):
            return "bd 1.2.2"

    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "ensure_beads", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "validate_bundle", lambda source: None)
    monkeypatch.setattr(setup, "ensure_interaction_log_policy", lambda root: {})
    monkeypatch.setattr(setup, "copy_formula", lambda *args, **kwargs: "installed")
    monkeypatch.setattr(setup, "validate_formula", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        setup,
        "initialize_docs",
        lambda root: {
            "created_documentation": ["docs/book.toml"],
            "documentation": {"status": "ok"},
        },
    )

    result = setup.install(tmp_path, initialize=True, force=False)

    assert result["created_documentation"] == ["docs/book.toml"]
    assert result["documentation"] == {"status": "ok"}


def test_forced_install_repairs_legacy_before_strict_documentation_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class Client:
        def check_version(self):
            return "bd 1.2.2"

    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "ensure_beads", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "validate_bundle", lambda source: None)
    monkeypatch.setattr(
        setup,
        "require_mdbook",
        lambda: events.append("require-mdbook") or "/usr/bin/mdbook",
    )
    monkeypatch.setattr(
        setup,
        "initialize_docs",
        lambda root: pytest.fail("forced install validated documentation before repair"),
    )
    monkeypatch.setattr(
        setup,
        "copy_formula",
        lambda *args, **kwargs: events.append("formula") or "installed",
    )
    monkeypatch.setattr(setup, "validate_formula", lambda *args, **kwargs: None)

    def repair(root: Path, *, force: bool):
        assert force is True
        events.append("repair")
        return {
            "status": "ok",
            "template_artifacts_removed": ["legacy-template"],
            "molecule_items_normalized": ["feature-1"],
            "missing_feature_reconciliations": ["docs/src/features/old/index.md"],
            "created_documentation": ["docs/src/index.md"],
            "documentation_migration": {
                "configured_source_moves": [],
                "referenced_content_moves": [],
                "unresolved_outside_markdown": [],
            },
            "documentation": {"status": "ok"},
            "interaction_log_untracked": True,
            "beads_gitignore_changed": False,
        }

    monkeypatch.setattr(setup, "repair_legacy", repair)

    result = setup.install(tmp_path, initialize=True, force=True)

    assert events[0] == "require-mdbook"
    assert events[-1] == "repair"
    assert events.index("repair") > events.index("formula")
    assert result["created_documentation"] == ["docs/src/index.md"]
    assert result["documentation"] == {"status": "ok"}
    assert result["template_artifacts_removed"] == ["legacy-template"]
    assert result["molecule_items_normalized"] == ["feature-1"]
    assert result["missing_feature_reconciliations"] == [
        "docs/src/features/old/index.md"
    ]
    assert result["interaction_log_untracked"] is True


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
    monkeypatch.setattr(
        setup,
        "missing_feature_reconciliations",
        lambda client: ["docs/src/features/old/index.md"],
    )
    monkeypatch.setattr(setup, "tracked", lambda root, path: True)
    result = setup.repair_legacy(tmp_path, force=False)
    assert result == {
        "status": "repair-required",
        "template_artifacts": ["dstack-feature.template"],
        "molecule_items_to_normalize": ["feature-1"],
        "interaction_log_tracked": True,
        "interaction_log_ignore_missing": True,
        "missing_feature_reconciliations": ["docs/src/features/old/index.md"],
        "documentation_migration": {
            "configured_source_moves": [],
            "referenced_content_moves": [],
            "unresolved_outside_markdown": [],
        },
    }
    beads.assert_exhausted()


def test_explicit_repair_migrates_feature_design_to_mdbook_path(tmp_path: Path) -> None:
    source = tmp_path / "docs/features/feature/design.md"
    source.parent.mkdir(parents=True)
    source.write_text("legacy design\n")
    summary = tmp_path / "docs/src/SUMMARY.md"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        "# Summary\n\n- [Operations](operations/index.md)\n"
        "- [Feature Records](features/index.md)\n"
        "  - [Feature](../features/feature/design.md)\n"
    )
    feature_index = tmp_path / "docs/src/features/index.md"
    feature_index.parent.mkdir(parents=True)
    feature_index.write_text(
        "# Feature Records\n\n- [Feature](../../features/feature/design.md)\n"
    )
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
    destination = tmp_path / "docs/src/features/feature/design.md"
    assert not source.exists()
    assert destination.read_text() == "legacy design\n"
    assert "features/feature/design.md" in summary.read_text()
    assert "../features/feature/design.md" not in summary.read_text()
    assert "[Operations](operations/index.md)" in summary.read_text()
    assert "feature/design.md" in feature_index.read_text()
    assert "../../features/feature/design.md" not in feature_index.read_text()
    beads.assert_exhausted()


def test_explicit_repair_recovers_move_completed_before_metadata_update(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "docs/src/features/feature/design.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("moved design\n")
    root = {
        "id": "feature-1",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.design_path": "docs/features/feature/design.md"},
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
            result=root,
        ),
        call("children", "feature-1", result=[]),
    )

    assert setup.normalize_current_features(beads, force=True) == ["feature-1"]
    assert destination.read_text() == "moved design\n"
    assert "features/feature/design.md" in (
        tmp_path / "docs/src/SUMMARY.md"
    ).read_text()
    beads.assert_exhausted()


def test_explicit_repair_refuses_missing_legacy_design_before_metadata_update(
    tmp_path: Path,
) -> None:
    root = {
        "id": "feature-1",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.design_path": "docs/features/feature/design.md"},
    }
    beads = ScriptedClient(
        tmp_path,
        call(
            "list",
            all_statuses=True,
            labels=["workflow:feature"],
            result=[root],
        ),
    )

    with pytest.raises(setup.SetupError, match="legacy feature design is missing"):
        setup.normalize_current_features(beads, force=True)

    beads.assert_exhausted()


@pytest.mark.parametrize("failure", ["conflict", "symlink", "unknown"])
def test_explicit_repair_refuses_unsafe_or_ambiguous_design_migration(tmp_path: Path, failure: str) -> None:
    legacy = tmp_path / "docs/features/feature/design.md"
    canonical = tmp_path / "docs/src/features/feature/design.md"
    legacy.parent.mkdir(parents=True)
    if failure == "symlink":
        outside = tmp_path / "outside.md"
        outside.write_text("outside\n")
        legacy.symlink_to(outside)
    else:
        legacy.write_text("legacy\n")
    if failure == "conflict":
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical\n")
    design_path = "docs/other/feature/design.md" if failure == "unknown" else "docs/features/feature/design.md"
    root = {
        "id": "feature-1",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.design_path": design_path},
    }
    beads = ScriptedClient(
        tmp_path,
        call(
            "list",
            all_statuses=True,
            labels=["workflow:feature"],
            result=[root],
        ),
    )

    with pytest.raises(setup.SetupError):
        setup.normalize_current_features(beads, force=True)

    assert legacy.exists()
    beads.assert_exhausted()


def test_missing_historical_reconciliation_is_reported(tmp_path: Path) -> None:
    design = tmp_path / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("design\n")
    beads = ScriptedClient(
        tmp_path,
        call(
            "list",
            all_statuses=True,
            labels=["workflow:feature"],
            result=[
                {
                    "id": "feature-1",
                    "status": "closed",
                    "labels": ["workflow:feature", "feature:feature"],
                }
            ],
        ),
    )

    assert setup.missing_feature_reconciliations(beads) == [
        "docs/src/features/feature/index.md"
    ]
    beads.assert_exhausted()


def test_forced_repair_validates_resulting_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beads = ScriptedClient(tmp_path, call("check_version", result="bd 1.2.2"))
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: beads)
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client: [])
    monkeypatch.setattr(setup, "normalize_current_features", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "normalize_current_alignments", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "missing_feature_reconciliations", lambda client: [])
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "ensure_interaction_log_policy", lambda root: {})
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})

    result = setup.repair_legacy(tmp_path, force=True)

    assert result["documentation"] == {"status": "ok"}
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
