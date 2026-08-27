from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_compat
import dstack_delivery
import dstacklib
import setup
from dstacklib import DstackError

from scripted import ScriptedClient, call


def feature(issue_id: str, *, parent: str | None = None, slug: str = "demo", labels: list[str] | None = None, **extra):
    return {
        "id": issue_id,
        "issue_type": extra.pop("issue_type", "epic"),
        "status": extra.pop("status", "open"),
        "labels": labels if labels is not None else ["workflow:feature", f"feature:{slug}"],
        **({"parent": parent} if parent else {}),
        **extra,
    }


def alignment(issue_id: str, *, parent: str | None = None, slug: str = "audit", **extra):
    return {
        "id": issue_id,
        "issue_type": extra.pop("issue_type", "molecule"),
        "status": extra.pop("status", "open"),
        "labels": ["workflow:project-alignment", f"audit:{slug}"],
        **({"parent": parent} if parent else {}),
        **extra,
    }


@pytest.mark.parametrize(
    ("resolver", "issue", "message"),
    [
        (dstacklib.resolve_feature, feature("nested", parent="root"), "not a feature workflow root"),
        (
            dstacklib.resolve_feature,
            feature("nested", labels=["workflow:feature", "feature:demo", "audit:other"]),
            "not a feature workflow root",
        ),
        (dstacklib.resolve_alignment, alignment("nested", parent="root"), "not a project-alignment workflow root"),
    ],
)
def test_exact_nested_workflow_ids_are_rejected(tmp_path: Path, resolver, issue: dict, message: str) -> None:
    beads = ScriptedClient(tmp_path, call("show_optional", "nested", result=issue))
    with pytest.raises(DstackError, match=message):
        resolver(beads, "nested")
    beads.assert_exhausted()


def test_root_lists_require_parentless_unambiguous_identity(tmp_path: Path) -> None:
    valid = feature("valid")
    planned = feature("planned", labels=["dstack:feature-idea", "feature:planned"])
    inventory = [
        valid,
        planned,
        feature("nested", parent="valid"),
        feature("missing-identity", labels=["workflow:feature"]),
        feature("competing", labels=["workflow:feature", "feature:a", "feature:b"]),
        feature("cross-kind", labels=["workflow:feature", "feature:demo", "audit:other"]),
    ]
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert [item["id"] for item in dstacklib.feature_roots(beads)] == ["valid", "planned"]
    beads.assert_exhausted()


def test_alignment_roots_ignore_nested_pollution(tmp_path: Path) -> None:
    root = alignment("root")
    nested = alignment("nested", parent="root")
    cross_kind = alignment(
        "cross-kind",
        labels=["workflow:project-alignment", "audit:audit", "dstack:feature-idea"],
    )
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=[root, nested, cross_kind]))
    assert dstacklib.alignment_roots(beads) == [root]
    beads.assert_exhausted()


def test_adoption_accepts_parentless_metadata_only_legacy_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {
        "id": "legacy",
        "issue_type": "epic",
        "status": "open",
        "metadata": {"feature_slug": "legacy"},
    }
    strict = ScriptedClient(tmp_path, call("show_optional", "legacy", result=legacy))
    with pytest.raises(DstackError, match="not a feature workflow root"):
        dstacklib.resolve_feature(strict, "legacy")
    strict.assert_exhausted()

    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "legacy", result=legacy),
        call("children", "legacy", result=[]),
    )
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "descendants", lambda *args: [])
    output = []
    monkeypatch.setattr(dstack_compat, "emit", output.append)

    args = type("Args", (), {"root": tmp_path, "selector": "legacy"})()
    assert dstack_compat.cmd_adopt_inspect(args) == 0
    assert output[0]["legacy_root"] == legacy
    beads.assert_exhausted()


def test_adoption_replacement_lookup_ignores_nested_pollution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = feature("root")
    nested = feature("nested", parent="root")
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=[root, nested]))
    monkeypatch.setattr(dstack_compat, "feature_context", lambda client, selector: {"current": True})
    assert dstack_compat.current_feature_for_slug(beads, "demo", exclude_id="legacy") == root
    beads.assert_exhausted()


def test_delivery_exact_nested_workflow_id_is_rejected(tmp_path: Path) -> None:
    nested = feature("nested", parent="root")
    beads = ScriptedClient(tmp_path, call("show_optional", "nested", result=nested))
    with pytest.raises(DstackError, match="not a workflow root"):
        dstack_delivery._delivery_root(beads, "nested")
    beads.assert_exhausted()


def polluted_feature_inventory() -> list[dict]:
    return [
        feature(
            "root",
            labels=["workflow:feature", "feature:demo", "dstack:delivery-ready", "keep:root"],
            metadata={"base_branch": "main"},
        ),
        feature(
            "implementation",
            parent="root",
            labels=["workflow:feature", "feature:demo", "dstack:step:implementation", "keep:child"],
            metadata={"base_branch": "main", "dstack.base_branch": "main"},
        ),
        feature(
            "task",
            parent="implementation",
            issue_type="task",
            labels=["workflow:feature", "feature:demo", "keep:task"],
            metadata={"design_path": "docs/src/features/demo/design.md"},
        ),
    ]


def test_setup_normalizes_polluted_descendants_from_one_inventory(tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=polluted_feature_inventory()))
    mutations = setup._setup_normalization_plan(beads)
    assert [item["issue_id"] for item in mutations] == ["implementation", "root", "task"]
    assert len({item["issue_id"] for item in mutations}) == len(mutations)
    by_id = {item["issue_id"]: item for item in mutations}
    assert by_id["implementation"]["remove_labels"] == ["feature:demo", "workflow:feature"]
    assert by_id["task"]["remove_labels"] == ["feature:demo", "workflow:feature"]
    assert set(by_id["implementation"]["unset_metadata"]) >= {"base_branch", "dstack.base_branch"}
    assert "keep:child" not in by_id["implementation"]["remove_labels"]
    assert "keep:task" not in by_id["task"]["remove_labels"]
    beads.assert_exhausted()


def test_setup_repairs_known_formula_placeholder_descendants(tmp_path: Path) -> None:
    inventory = [
        feature("feature-root"),
        feature(
            "feature-child",
            parent="feature-root",
            labels=["workflow:feature", "feature:{{feature_slug}}"],
        ),
        alignment("alignment-root"),
        alignment(
            "alignment-child",
            parent="alignment-root",
            labels=["workflow:project-alignment", "audit:{{audit_slug}}"],
        ),
    ]
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    mutations = {item["issue_id"]: item for item in setup._setup_normalization_plan(beads)}
    assert mutations["feature-child"]["remove_labels"] == [
        "feature:{{feature_slug}}",
        "workflow:feature",
    ]
    assert mutations["alignment-child"]["remove_labels"] == [
        "audit:{{audit_slug}}",
        "workflow:project-alignment",
    ]
    beads.assert_exhausted()


@pytest.mark.parametrize(
    "inventory",
    [
        [feature("orphan", parent="missing")],
        [feature("identity-orphan", parent="missing", labels=["feature:demo"])],
        [feature("idea-orphan", parent="missing", labels=["dstack:feature-idea"])],
        [feature("a", parent="b"), feature("b", parent="a")],
        [
            feature("identity-a", parent="identity-b", labels=["feature:demo"]),
            feature("identity-b", parent="identity-a", labels=["feature:demo"]),
        ],
        [
            feature("idea-a", parent="idea-b", labels=["dstack:feature-idea"]),
            feature("idea-b", parent="idea-a", labels=["dstack:feature-idea"]),
        ],
        [feature("root"), feature("nested", parent="root", slug="other")],
        [feature("root"), alignment("nested", parent="root")],
        [alignment("root"), feature("nested", parent="root", labels=["dstack:feature-idea"])],
        [
            feature("legacy", labels=[], metadata={"feature_slug": "legacy"}),
            alignment("nested", parent="legacy"),
        ],
        [
            feature("root"),
            feature("nested", parent="root", labels=["workflow:feature", "feature:demo", "feature:other"]),
        ],
    ],
    ids=[
        "orphan",
        "identity-only-orphan",
        "idea-marker-orphan",
        "cycle",
        "identity-only-cycle",
        "idea-marker-cycle",
        "mismatch",
        "cross-kind",
        "idea-marker-cross-kind",
        "legacy-cross-kind",
        "competing",
    ],
)
def test_setup_rejects_ambiguous_polluted_topology_before_mutation(tmp_path: Path, inventory: list[dict]) -> None:
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    with pytest.raises(setup.SetupError, match="ambiguous workflow topology"):
        setup._setup_normalization_plan(beads)
    beads.assert_exhausted()


def test_setup_preserves_active_metadata_only_legacy_feature(tmp_path: Path) -> None:
    legacy = feature(
        "legacy",
        labels=[],
        metadata={"feature_slug": "legacy"},
    )
    child = feature(
        "legacy-task",
        parent="legacy",
        slug="legacy",
        issue_type="task",
        labels=["feature:legacy", "keep:legacy"],
        metadata={"feature_slug": "legacy", "keep": "value"},
    )
    inventory = [legacy, child]
    plan_client = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert setup._setup_normalization_plan(plan_client) == []
    plan_client.assert_exhausted()

    doctor_client = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert setup.workflow_topology_diagnostics(doctor_client) == ["active legacy feature: run /adopt-feature legacy"]
    doctor_client.assert_exhausted()


def test_separate_roots_may_share_historical_identity(tmp_path: Path) -> None:
    inventory = [feature("old", status="closed"), feature("current")]
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert [mutation["issue_id"] for mutation in setup._setup_normalization_plan(beads)] == ["current", "old"]
    beads.assert_exhausted()


def test_setup_large_polluted_graph_uses_one_inventory_call(tmp_path: Path) -> None:
    inventory = [feature("root")]
    inventory.append(
        feature(
            "implementation",
            parent="root",
            labels=["workflow:feature", "feature:demo", "dstack:step:implementation"],
        )
    )
    inventory.extend(feature(f"task-{index}", parent="implementation", issue_type="task") for index in range(20))
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    mutations = setup._setup_normalization_plan(beads)
    assert len(mutations) == 22
    assert len({mutation["issue_id"] for mutation in mutations}) == 22
    beads.assert_exhausted()


def test_doctor_topology_diagnostic_is_single_and_actionable(tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=polluted_feature_inventory()))
    with pytest.raises(setup.SetupError, match="legacy workflow root identity on descendants: implementation, task"):
        setup.workflow_topology_diagnostics(beads)
    beads.assert_exhausted()


def test_setup_duplicate_mutation_guard_remains_strict() -> None:
    mutation = {
        "issue_id": "duplicate",
        "set_metadata": {},
        "unset_metadata": [],
        "add_labels": [],
        "remove_labels": ["workflow:feature"],
    }
    with pytest.raises(setup.SetupError, match="duplicate setup issue mutation"):
        setup._setup_beads_issues([mutation, mutation])


def test_reconciliation_deduplicates_separate_historical_roots(tmp_path: Path) -> None:
    design = tmp_path / "docs/src/features/demo/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("design\n")
    inventory = [feature("old", status="closed"), feature("new", status="closed")]
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert setup.missing_feature_reconciliations(beads) == ["docs/src/features/demo/index.md"]
    beads.assert_exhausted()


def test_reconciliation_reports_each_logical_feature_once(tmp_path: Path) -> None:
    design = tmp_path / "docs/src/features/demo/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("design\n")
    inventory = polluted_feature_inventory()
    for item in inventory:
        item["status"] = "closed"
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert setup.missing_feature_reconciliations(beads) == ["docs/src/features/demo/index.md"]
    beads.assert_exhausted()
