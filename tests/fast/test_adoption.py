from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import adoption as dstack_adoption
from dstack import adoption_apply as dstack_adoption_apply
from dstack import commands as dstack_commands
from dstack import compat as dstack_compat
from dstack.commands import DstackError
from dstack.core import FEATURE_STEPS

from scripted import ScriptedClient, call


def adoption_snapshot(
    root: dict[str, Any],
    *descendants: dict[str, Any],
    native_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    records = [root, *descendants]
    return {
        "legacy_root_id": str(root["id"]),
        "legacy_ids": sorted(str(item["id"]) for item in records),
        "legacy_records": sorted(records, key=lambda item: str(item["id"])),
        "native_records": sorted(native_records or records, key=lambda item: str(item["id"])),
        "internal": [],
        "outgoing_external": [],
        "incoming_external": [],
    }


def test_compatibility_shims_have_reproducers_and_retirement_conditions() -> None:
    assert {shim["name"] for shim in dstack_compat.COMPATIBILITY_SHIMS} == {
        "like-kind-approval-milestone",
        "dynamic-child-fan-in-veto",
        "terminal-root-reopen",
    }
    for shim in dstack_compat.COMPATIBILITY_SHIMS:
        assert shim["pinned_version"] == "bd version 1.2.2 (6c124203e)"
        assert (ROOT / shim["reproducer"].split("::", 1)[0]).is_file()
        assert shim["reason"]
        assert shim["behavior"]
        assert shim["retirement"]


def test_adoption_graph_snapshot_uses_one_native_inventory_read() -> None:
    root = {"id": "legacy", "status": "open", "issue_type": "epic"}
    child = {"id": "child", "parent": "legacy", "status": "open", "issue_type": "task"}
    grandchild = {"id": "grandchild", "parent": "child", "status": "closed", "issue_type": "task"}
    superseded_child = {"id": "legacy.2", "status": "closed", "issue_type": "task"}
    dependent = {
        "id": "dependent",
        "status": "open",
        "issue_type": "task",
        "dependencies": [{"depends_on_id": "child", "type": "blocks"}],
    }

    class Client:
        def show(self, issue_id: str) -> dict[str, Any]:
            assert issue_id == "legacy"
            return root

        def list(self, *, all_statuses: bool) -> list[dict[str, Any]]:
            assert all_statuses is True
            return [root, child, grandchild, superseded_child, dependent]

        def gates(self, *, all_statuses: bool) -> list[dict[str, Any]]:
            assert all_statuses is True
            return []

        def children(self, parent: str) -> list[dict[str, Any]]:
            raise AssertionError(f"snapshot should not query children individually: {parent}")

    snapshot = dstack_adoption.adoption_graph_snapshot(Client(), "legacy")

    assert snapshot["legacy_ids"] == ["child", "grandchild", "legacy", "legacy.2"]
    assert snapshot["incoming_external"] == [
        {"source_id": "dependent", "target_id": "child", "relationship_type": "blocks"}
    ]


def test_adoption_classification_rejects_unknown_fields_and_normalizes_replacement(
    tmp_path: Path,
) -> None:
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "task-1",
                "classification": "remaining-implementation",
                "reason": "work remains",
                "replacement": {
                    "title": "Continue work",
                    "description": "description",
                    "acceptance": "acceptance",
                    "priority": 1,
                },
            }
        ],
    }
    assert (
        dstack_adoption.canonicalize_classification(classification, root=tmp_path, legacy_root_id="legacy-1")[
            "entries"
        ][0]["replacement"]["priority"]
        == 1
    )
    classification["unexpected"] = True
    with pytest.raises(DstackError, match="unknown unexpected"):
        dstack_adoption.canonicalize_classification(classification, root=tmp_path, legacy_root_id="legacy-1")


@pytest.mark.parametrize("kind", ["bug", "chore"])
def test_adoption_plan_includes_native_executable_kinds(tmp_path: Path, kind: str) -> None:
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "task-1",
                "classification": "remaining-implementation",
                "reason": "work remains",
                "replacement": {
                    "title": "Continue work",
                    "description": "description",
                    "acceptance": "acceptance",
                    "priority": 1,
                },
            }
        ],
    }
    root = {"id": "legacy-1", "status": "open", "issue_type": "epic"}
    task = {"id": "task-1", "status": "open", "issue_type": kind, "parent": "legacy-1"}
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root, task]),
        call("gates", all_statuses=True, result=[]),
    )
    plan = dstack_adoption.plan_adoption(beads, "legacy-1", classification)
    assert plan["inventory"]["open_executable_descendants"] == ["task-1"]
    beads.assert_exhausted()


def test_adoption_plan_rejects_documentation_replacements_before_mutation(tmp_path: Path) -> None:
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "task-1",
                "classification": "remaining-implementation",
                "reason": "work remains",
                "replacement": {
                    "title": "Reconcile documentation",
                    "description": "description",
                    "acceptance": "acceptance",
                    "priority": 1,
                },
            }
        ],
    }
    root = {"id": "legacy-1", "status": "open", "issue_type": "epic"}
    task = {"id": "task-1", "status": "open", "issue_type": "task", "parent": "legacy-1"}
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root, task]),
        call("gates", all_statuses=True, result=[]),
    )
    with pytest.raises(DstackError, match="sole final reconciliation"):
        dstack_adoption.plan_adoption(beads, "legacy-1", classification)
    beads.assert_exhausted()


def test_adoption_plan_fails_closed_missing_native_status_or_type(tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    snapshot = adoption_snapshot(
        {"id": "legacy-1", "status": "open", "issue_type": "epic"},
        {"id": "task-1", "issue_type": "task"},
    )
    with pytest.raises(DstackError, match="lacks native status/type"):
        dstack_adoption.plan_adoption(
            beads,
            "legacy-1",
            {"schema": dstack_adoption.SCHEMA, "legacy_root_id": "legacy-1", "entries": []},
            snapshot=snapshot,
        )
    beads.assert_exhausted()


def test_adoption_plan_translates_root_blocker_to_approval_step(tmp_path: Path) -> None:
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "task-1",
                "classification": "remaining-implementation",
                "reason": "work remains",
                "replacement": {
                    "title": "Continue work",
                    "description": "description",
                    "acceptance": "acceptance",
                    "priority": 1,
                },
            }
        ],
    }
    root = {
        "id": "legacy-1",
        "status": "open",
        "issue_type": "epic",
        "dependencies": [{"depends_on_id": "blocker", "type": "blocks"}],
    }
    task = {"id": "task-1", "status": "open", "issue_type": "task", "parent": "legacy-1"}
    blocker = {"id": "blocker", "status": "open", "issue_type": "task"}
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root, task, blocker]),
        call("gates", all_statuses=True, result=[]),
    )
    plan = dstack_adoption.plan_adoption(beads, "legacy-1", classification)
    op = next(item for item in plan["relationship_operations"] if item["target_id"] == "blocker")
    assert op["decision"] == "redirect"
    assert op["target_step"] == "approval"
    assert op["add_before_remove"] is True
    beads.assert_exhausted()


def test_adoption_plan_includes_gate_and_native_supersession_edges(tmp_path: Path) -> None:
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "task-1",
                "classification": "remaining-implementation",
                "reason": "work remains",
                "replacement": {
                    "title": "Continue work",
                    "description": "description",
                    "acceptance": "acceptance",
                    "priority": 1,
                },
            }
        ],
    }
    root = {
        "id": "legacy-1",
        "status": "open",
        "issue_type": "epic",
        "dependencies": [{"depends_on_id": "gate-1", "type": "supersedes"}],
    }
    task = {"id": "task-1", "status": "open", "issue_type": "task", "parent": "legacy-1"}
    gate = {"id": "gate-1", "status": "open", "issue_type": "gate"}
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root, task]),
        call("gates", all_statuses=True, result=[gate]),
    )
    plan = dstack_adoption.plan_adoption(beads, "legacy-1", classification)
    assert plan["inventory"]["outgoing_external"] == [
        {"source_id": "legacy-1", "target_id": "gate-1", "relationship_type": "supersedes"}
    ]
    operation = plan["relationship_operations"][0]
    assert operation["decision"] == "preserve-native-supersession"
    assert operation["add_before_remove"] is False
    beads.assert_exhausted()


def test_adoption_plan_requires_canonical_design_path_for_incorporated_decision(
    tmp_path: Path,
) -> None:
    design = tmp_path / "docs/src/features/new-feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("# Requirements\n\nResolve this decision.\n")
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "decision-1",
                "classification": "unresolved-decision",
                "reason": "decision needs incorporation",
                "strategy": "incorporated",
                "specification_section": "docs/src/features/other/design.md#Requirements",
                "blocking_target": None,
            }
        ],
    }
    with pytest.raises(DstackError, match="specification_section path"):
        dstack_adoption.canonicalize_classification(
            classification,
            root=tmp_path,
            legacy_root_id="legacy-1",
            design_path="docs/src/features/new-feature/design.md",
        )


def test_replacement_reuse_requires_native_supersession_proof(tmp_path: Path) -> None:
    class Client:
        root = tmp_path

        def children(self, parent: str) -> list[dict[str, Any]]:
            return [{"id": "unrelated", "title": "same title", "status": "open", "issue_type": "task"}]

    with pytest.raises(DstackError, match="supersession proof"):
        dstack_adoption_apply._find_existing_replacement(
            Client(),
            {
                "legacy_id": "legacy-task",
                "replacement": {"title": "same title"},
            },
            implementation_id="implementation",
            approval_id="approval",
            expected_id=None,
            reserved=set(),
        )


def test_preflight_rejects_bug_replacement_before_mutation(tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy", result={"id": "legacy", "status": "open", "issue_type": "epic"}),
        call("show", "bug-1", result={"id": "bug-1", "status": "open", "issue_type": "bug"}),
        call("show", "bug-1", result={"id": "bug-1", "status": "open", "issue_type": "bug"}),
    )
    plan = {
        "entries": [{"legacy_id": "bug-1", "classification": "remaining-implementation"}],
        "replacements": [{"legacy_id": "bug-1", "source_type": "bug"}],
        "inventory": {"internal": [], "outgoing_external": [], "incoming_external": []},
        "relationship_operations": [],
    }
    with pytest.raises(DstackError, match="cannot use the task approval blocker"):
        dstack_adoption_apply.validate_adoption_preflight(beads, plan, legacy_root_id="legacy")
    beads.assert_exhausted()


def test_preflight_rejects_claimed_legacy_root_before_pour(tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "legacy",
            result={
                "id": "legacy",
                "status": "claimed",
                "issue_type": "epic",
                "assignee": "worker",
            },
        ),
    )
    with pytest.raises(DstackError, match="open and unassigned"):
        dstack_adoption_apply.validate_adoption_preflight(
            beads,
            {
                "entries": [],
                "replacements": [],
                "inventory": {"internal": [], "outgoing_external": [], "incoming_external": []},
            },
            legacy_root_id="legacy",
        )
    beads.assert_exhausted()


def test_incorporated_decision_retry_requires_approved_committed_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    design = tmp_path / "docs/src/features/new-feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("# Requirements\n\nResolved decision text.\n")
    view = {"slug": "new-feature", "design_path": "docs/src/features/new-feature/design.md"}
    monkeypatch.setattr(dstack_adoption_apply, "feature_design_state", lambda *args: {"design_approved": True})
    monkeypatch.setattr(
        dstack_adoption_apply,
        "feature_authorization_state",
        lambda *args: {"native_approved": True},
    )
    monkeypatch.setattr(dstack_adoption_apply, "worktree_for_branch", lambda *args: tmp_path)
    assert dstack_adoption_apply._incorporated_decision_authorized(
        type("Client", (), {"root": tmp_path})(),
        view,
        "docs/src/features/new-feature/design.md#Requirements",
    )
    monkeypatch.setattr(
        dstack_adoption_apply,
        "feature_authorization_state",
        lambda *args: {"native_approved": False},
    )
    assert not dstack_adoption_apply._incorporated_decision_authorized(
        type("Client", (), {"root": tmp_path})(),
        view,
        "docs/src/features/new-feature/design.md#Requirements",
    )


def test_retry_association_ignores_ordinary_external_context() -> None:
    class Client:
        def children(self, parent: str) -> list[dict[str, Any]]:
            return [{"id": "replacement", "parent": "implementation"}] if parent == "implementation" else []

    client = Client()
    ordinary = {
        "id": "legacy",
        "dependencies": [{"depends_on_id": "context", "type": "relates-to"}],
    }
    retry = {
        "id": "legacy",
        "dependencies": [{"depends_on_id": "replacement", "type": "relates-to"}],
    }
    assert dstack_adoption_apply._replacement_association(client, ordinary, implementation_id="implementation") is None
    assert (
        dstack_adoption_apply._replacement_association(client, retry, implementation_id="implementation")
        == "replacement"
    )


def test_closed_retry_target_requires_converged_existing_edge() -> None:
    class Client:
        root = Path(".")

        def show(self, issue_id: str) -> dict[str, Any]:
            if issue_id == "closed-step":
                return {
                    "id": issue_id,
                    "status": "closed",
                    "issue_type": "task",
                    "dependencies": [{"depends_on_id": "blocker", "type": "blocks"}],
                }
            return {"id": issue_id, "status": "open", "issue_type": "task"}

        def add_dependency(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("closed retry target required no new mutation")

    dstack_adoption_apply._ensure_edge(Client(), "closed-step", "blocker", "blocks")


def test_adoption_rereads_native_readiness_for_incoming_dependents() -> None:
    class Client:
        def json(self, command: list[str]) -> list[dict[str, str]]:
            assert command == ["bd", "ready", "--limit", "0", "--json"]
            return [{"id": "dependent"}]

    plan = {
        "inventory": {
            "incoming_external": [
                {
                    "source_id": "dependent",
                    "target_id": "legacy",
                    "relationship_type": "blocks",
                }
            ]
        },
        "relationship_operations": [
            {
                "source_id": "dependent",
                "target_id": "legacy",
                "relationship_type": "blocks",
                "decision": "deferred-redirect",
            }
        ],
    }
    dependents = dstack_adoption_apply._incoming_dependent_ids(plan)
    with pytest.raises(DstackError, match="became ready"):
        dstack_adoption_apply._assert_not_ready(Client(), dependents, phase="test")


def test_raw_poured_topology_rejects_invalid_root_before_identity_update() -> None:
    class Client:
        def show(self, issue_id: str) -> dict[str, Any]:
            return {"id": issue_id, "status": "closed", "issue_type": "epic"}

        def children(self, parent: str) -> list[dict[str, Any]]:
            return []

    with pytest.raises(DstackError, match="invalid status"):
        dstack_adoption_apply.validate_target_topology(Client(), "new-root")


def test_execute_adoption_rejects_post_plan_incoming_graph_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def reconcile(*args: Any, **kwargs: Any) -> None:
        calls.append(len(calls) + 1)
        if len(calls) == 2:
            raise DstackError("legacy adoption graph drifted; incoming blocker added")

    monkeypatch.setattr(dstack_adoption_apply, "reconcile_adoption_graph", reconcile)

    class Native:
        root = Path(".")

        def show(self, issue_id: str) -> dict[str, Any]:
            return {"id": issue_id, "status": "open", "issue_type": "task"}

        def supersede(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("graph drift must block root supersession")

    plan = {
        "schema": dstack_adoption.PLAN_SCHEMA,
        "legacy_root_id": "legacy",
        "entries": [],
        "replacements": [],
        "decision_staging": [],
        "relationship_operations": [
            {
                "source_id": "dependent",
                "target_id": "legacy",
                "relationship_type": "blocks",
                "decision": "deferred-redirect",
            }
        ],
        "inventory": {
            "internal": [],
            "outgoing_external": [],
            "incoming_external": [
                {
                    "source_id": "dependent",
                    "target_id": "legacy",
                    "relationship_type": "blocks",
                }
            ],
        },
        "supersession": {"eligible": True},
    }
    with pytest.raises(DstackError, match="incoming blocker added"):
        dstack_adoption_apply.execute_adoption_plan(
            Native(),
            plan,
            legacy_root_id="legacy",
            new_root_id="new-root",
            view={
                "steps": {name: {"id": name} for name in ("specification", "approval", "implementation", "closeout")}
            },
            expected_graph={"legacy_root_id": "legacy"},
        )
    assert calls == [1, 2]


def test_execute_adoption_adds_replacement_edge_before_removing_legacy_edge() -> None:
    class Native:
        root = Path(".")

        def __init__(self) -> None:
            self.events: list[tuple[str, str, str]] = []
            self.issues = {
                "legacy": {
                    "id": "legacy",
                    "status": "open",
                    "issue_type": "epic",
                    "dependencies": [{"depends_on_id": "blocker", "type": "blocks"}],
                },
                "task": {
                    "id": "task",
                    "status": "open",
                    "issue_type": "task",
                    "parent": "legacy",
                    "description": "desc",
                    "acceptance_criteria": "accept",
                    "priority": 1,
                    "dependencies": [{"depends_on_id": "blocker", "type": "blocks"}],
                },
                "blocker": {"id": "blocker", "status": "open", "issue_type": "task"},
                "approval": {"id": "approval", "status": "open", "issue_type": "task"},
                "implementation": {"id": "implementation", "status": "open", "issue_type": "epic"},
                "specification": {"id": "specification", "status": "open", "issue_type": "task"},
                "closeout": {"id": "closeout", "status": "open", "issue_type": "task"},
            }

        def show(self, issue_id: str) -> dict[str, Any]:
            return dict(self.issues[issue_id])

        def create(self, title: str, **kwargs: Any) -> dict[str, Any]:
            self.issues["replacement"] = {
                "id": "replacement",
                "title": title,
                "description": kwargs["description"],
                "acceptance_criteria": kwargs["acceptance"],
                "priority": kwargs["priority"],
                "parent": kwargs["parent"],
                "labels": kwargs["labels"],
                "dependencies": [{"depends_on_id": "approval", "type": "blocks"}],
                "status": "open",
                "issue_type": "task",
            }
            return {"id": "replacement"}

        def add_dependency(self, source: str, target: str, *, relation_type: str = "blocks") -> None:
            self.events.append(("add", source, target))
            self.issues[source].setdefault("dependencies", []).append({"depends_on_id": target, "type": relation_type})

        def remove_dependency(self, source: str, target: str) -> None:
            self.events.append(("remove", source, target))
            self.issues[source]["dependencies"] = [
                item for item in self.issues[source].get("dependencies", []) if item.get("depends_on_id") != target
            ]

        def supersede(self, old: str, new: str) -> None:
            self.events.append(("supersede", old, new))
            self.issues[old]["status"] = "closed"
            self.issues[old]["dependencies"] = [{"depends_on_id": new, "type": "superseded-by"}]

        def children(self, parent: str) -> list[dict[str, Any]]:
            return []

    native = Native()
    plan = {
        "schema": dstack_adoption.PLAN_SCHEMA,
        "legacy_root_id": "legacy",
        "entries": [
            {
                "legacy_id": "task",
                "classification": "remaining-implementation",
                "reason": "remaining",
                "replacement": {
                    "title": "replacement",
                    "description": "desc",
                    "acceptance": "accept",
                    "priority": 1,
                },
            }
        ],
        "replacements": [
            {
                "legacy_id": "task",
                "replacement": {
                    "title": "replacement",
                    "description": "desc",
                    "acceptance": "accept",
                    "priority": 1,
                },
            }
        ],
        "decision_staging": [],
        "relationship_operations": [
            {
                "source_id": "task",
                "target_id": "blocker",
                "relationship_type": "blocks",
                "decision": "redirect",
            }
        ],
        "supersession": {"eligible": True},
    }
    result = dstack_adoption_apply.execute_adoption_plan(
        native,
        plan,
        legacy_root_id="legacy",
        new_root_id="new-root",
        view={"steps": {name: {"id": name} for name in ("specification", "approval", "implementation", "closeout")}},
    )
    assert native.events.index(("add", "replacement", "blocker")) < native.events.index(("remove", "task", "blocker"))
    assert result["root_superseded"] is True


def test_adopt_apply_validates_plan_before_pouring_or_other_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = {
        "id": "legacy-1",
        "status": "open",
        "issue_type": "epic",
        "title": "Feature: Old",
    }
    task = {"id": "task-1", "status": "open", "issue_type": "task", "title": "Work"}
    snapshot = adoption_snapshot(legacy, task)
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_compat, "resolve_legacy_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "is_current_feature", lambda *args: False)
    monkeypatch.setattr(dstack_compat, "adoption_graph_snapshot", lambda *args: snapshot)
    poured: list[bool] = []
    monkeypatch.setattr(dstack_compat, "pour_current_formula", lambda *args, **kwargs: poured.append(True))
    args = type(
        "Args",
        (),
        {
            "root": tmp_path,
            "selector": "legacy-1",
            "title": None,
            "slug": "old",
            "base_branch": "main",
            "design_path": None,
            "remaining": ["foreign-task"],
            "spec_ceremony": [],
            "implementation_coordinator": [],
            "closeout_ceremony": [],
            "preserve": [],
            "reparent": [],
            "recreate": [],
            "incorporated_decision": [],
            "decision_blocker": [],
            "completed": [],
        },
    )()
    with pytest.raises(DstackError, match="not a descendant"):
        dstack_compat.cmd_adopt_apply(args)
    assert poured == []
    beads.assert_exhausted()


def test_adoption_classification_rejects_foreign_and_omitted_open_work(
    tmp_path: Path,
) -> None:
    base = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [],
    }
    beads = ScriptedClient(tmp_path)
    snapshot = adoption_snapshot(
        {"id": "legacy-1", "status": "open", "issue_type": "epic"},
        {"id": "task-1", "status": "open", "issue_type": "task"},
    )
    with pytest.raises(DstackError, match="omits open executable"):
        dstack_adoption.plan_adoption(beads, "legacy-1", base, snapshot=snapshot)
    beads.assert_exhausted()


def test_adoption_plan_inventories_both_external_relationship_directions(
    tmp_path: Path,
) -> None:
    classification = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [
            {
                "legacy_id": "task-1",
                "classification": "remaining-implementation",
                "reason": "work remains",
                "replacement": {
                    "title": "Continue work",
                    "description": "description",
                    "acceptance": "acceptance",
                    "priority": 1,
                },
            }
        ],
    }
    legacy = {
        "id": "legacy-1",
        "status": "open",
        "issue_type": "epic",
        "dependencies": [{"depends_on_id": "outside-blocker", "type": "blocks"}],
    }
    task = {"id": "task-1", "status": "open", "issue_type": "task", "parent": "legacy-1"}
    outside = {
        "id": "outside-dependent",
        "status": "open",
        "issue_type": "task",
        "dependencies": [{"depends_on_id": "task-1", "type": "blocks"}],
    }
    blocker = {"id": "outside-blocker", "status": "open", "issue_type": "task"}
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[legacy, task, outside, blocker]),
        call("gates", all_statuses=True, result=[]),
    )
    plan = dstack_adoption.plan_adoption(beads, "legacy-1", classification)
    inventory = plan["inventory"]
    assert inventory["outgoing_external"] == [
        {"source_id": "legacy-1", "target_id": "outside-blocker", "relationship_type": "blocks"}
    ]
    assert inventory["incoming_external"] == [
        {"source_id": "outside-dependent", "target_id": "task-1", "relationship_type": "blocks"}
    ]
    beads.assert_exhausted()


def test_classify_legacy_item_is_explicit_about_ambiguity() -> None:
    assert dstack_compat.classify_legacy_item({"title": "Implement: code"}) == "implementation-coordinator"
    assert dstack_compat.classify_legacy_item({"title": "unrelated"}) == "ambiguous"


def test_adoption_rejects_multiple_current_slug_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "list",
            all_statuses=True,
            result=[
                {
                    "id": "feature-1",
                    "issue_type": "epic",
                    "status": "open",
                    "labels": ["workflow:feature", "feature:slug"],
                },
                {
                    "id": "feature-2",
                    "issue_type": "epic",
                    "status": "open",
                    "labels": ["workflow:feature", "feature:slug"],
                },
            ],
        ),
    )
    monkeypatch.setattr(dstack_compat, "feature_context", lambda client, issue_id: {"current": True})
    with pytest.raises(DstackError, match="multiple current"):
        dstack_compat.current_feature_for_slug(beads, "slug", exclude_id="legacy")
    beads.assert_exhausted()


def test_adopt_inspect_classifies_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {
        "id": "legacy-1",
        "status": "open",
        "issue_type": "epic",
        "title": "Feature: Old",
    }
    old_task = {
        "id": "old-task",
        "status": "open",
        "issue_type": "task",
        "title": "Implement: old",
    }
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root, **kwargs: beads)
    monkeypatch.setattr(dstack_compat, "resolve_legacy_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "is_current_feature", lambda *args: False)
    monkeypatch.setattr(dstack_compat, "adoption_graph_snapshot", lambda *args: adoption_snapshot(legacy, old_task))
    output = []
    monkeypatch.setattr(dstack_compat, "emit", output.append)
    args = type("Args", (), {"root": tmp_path, "selector": "legacy-1"})()
    assert dstack_compat.cmd_adopt_inspect(args) == 0
    assert output[0]["classified"]["implementation-coordinator"][0]["id"] == "old-task"


def test_adopt_apply_rejects_noncanonical_design_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {"id": "legacy-1", "status": "open", "title": "Feature: Old"}
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "resolve_legacy_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "is_current_feature", lambda *args: False)
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
    monkeypatch.setattr(dstack_compat, "resolve_legacy_feature", lambda *args: legacy)
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
    assert dstack_commands.preserve_external_blockers(beads, source, "feature-1") == ["blocker-1"]
    beads.assert_exhausted()
