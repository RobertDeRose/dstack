from __future__ import annotations

import copy
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_adoption
import dstack_adoption_apply
import dstack_commands
import dstack_compat
import setup
from dstack_commands import DstackError
from dstacklib import CommandResult, FEATURE_STEPS

from scripted import ScriptedClient, call


def feature_formula() -> dict:
    return {
        "steps": [
            {"id": "specification", "type": "task", "labels": [FEATURE_STEPS["specification"]]},
            {
                "id": "approval",
                "type": "task",
                "labels": [FEATURE_STEPS["approval"]],
                "needs": ["specification"],
                "gate": {"type": "human"},
            },
            {"id": "implementation", "type": "epic", "labels": [FEATURE_STEPS["implementation"]]},
            {
                "id": "closeout",
                "type": "task",
                "labels": [FEATURE_STEPS["closeout"]],
                "needs": ["approval"],
                "waits_for": "children-of(implementation)",
            },
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
    task = {"id": "task-1", "status": "open", "issue_type": kind}
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy-1", result={"id": "legacy-1", "status": "open"}),
        call("children", "legacy-1", result=[task]),
        call("children", "task-1", result=[]),
        call("list", all_statuses=True, result=[]),
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
    task = {"id": "task-1", "status": "open", "issue_type": "task"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy-1", result={"id": "legacy-1", "status": "open"}),
        call("children", "legacy-1", result=[task]),
        call("children", "task-1", result=[]),
        call("list", all_statuses=True, result=[]),
        call("gates", all_statuses=True, result=[]),
    )
    with pytest.raises(DstackError, match="sole final reconciliation"):
        dstack_adoption.plan_adoption(beads, "legacy-1", classification)
    beads.assert_exhausted()


def test_adoption_plan_fails_closed_missing_native_status_or_type(tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy-1", result={"id": "legacy-1", "status": "open"}),
        call("children", "legacy-1", result=[{"id": "task-1", "issue_type": "task"}]),
        call("children", "task-1", result=[]),
    )
    with pytest.raises(DstackError, match="lacks native status/type"):
        dstack_adoption.plan_adoption(
            beads,
            "legacy-1",
            {"schema": dstack_adoption.SCHEMA, "legacy_root_id": "legacy-1", "entries": []},
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
    task = {"id": "task-1", "status": "open", "issue_type": "task"}
    blocker = {"id": "blocker", "status": "open", "issue_type": "task"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy-1", result=root),
        call("children", "legacy-1", result=[task]),
        call("children", "task-1", result=[]),
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
    task = {"id": "task-1", "status": "open", "issue_type": "task"}
    gate = {"id": "gate-1", "status": "open", "issue_type": "gate"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy-1", result=root),
        call("children", "legacy-1", result=[task]),
        call("children", "task-1", result=[]),
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
    legacy = {"id": "legacy-1", "status": "open", "title": "Feature: Old"}
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "resolve_legacy_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "is_current_feature", lambda *args: False)
    invalid = tmp_path / "classification.json"
    invalid.write_text(
        '{"schema":"dstack.adoption-classification/v1","legacy_root_id":"legacy-1","entries":[],"unknown":true}'
    )
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
            "classification_file": invalid,
            "remaining": [],
            "spec_ceremony": [],
            "implementation_coordinator": [],
            "closeout_ceremony": [],
        },
    )()
    with pytest.raises(DstackError, match="unknown"):
        dstack_compat.cmd_adopt_apply(args)
    beads.assert_exhausted()


def test_adoption_classification_rejects_foreign_and_omitted_open_work(
    tmp_path: Path,
) -> None:
    base = {
        "schema": dstack_adoption.SCHEMA,
        "legacy_root_id": "legacy-1",
        "entries": [],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "legacy-1", result={"id": "legacy-1", "status": "open"}),
        call(
            "children",
            "legacy-1",
            result=[{"id": "task-1", "status": "open", "issue_type": "task"}],
        ),
        call("children", "task-1", result=[]),
    )
    with pytest.raises(DstackError, match="omits open executable"):
        dstack_adoption.plan_adoption(beads, "legacy-1", base)
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
        call("show", "legacy-1", result=legacy),
        call("children", "legacy-1", result=[task]),
        call("children", "task-1", result=[]),
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


def setup_authority(**changes: str) -> dict[str, str]:
    value = {
        "controller_sha256": "f" * 64,
        "controller_state": "clean",
        "python_version": "Python 3.14.7",
        "beads_version": "bd version 1.2.2 (6c124203e)",
        "mdbook_version": "mdbook v0.5.3",
    }
    value.update(changes)
    return value


def test_controller_authority_reports_clean_and_dirty_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "package"
    scripts = package / "skills/dstack-beads-core/scripts"
    scripts.mkdir(parents=True)
    (scripts / "setup.py").write_text("print('clean')\n")
    (package / "bin").mkdir()
    (package / "bin/dstack").write_text("#!/bin/sh\n")
    (package / "formulas").mkdir()
    formula = package / "formulas/dstack-feature.formula.toml"
    formula.write_text("clean formula\n")
    for name in ("mise.toml", "mise.lock", "pyproject.toml"):
        (package / name).write_text(f"{name}\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=package, check=True)
    subprocess.run(["git", "add", "."], cwd=package, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=package,
        check=True,
    )
    monkeypatch.setattr(setup, "package_root", lambda: package)

    clean = setup._controller_authority()
    assert clean["controller_state"] == "clean"

    (scripts / "setup.py").write_text("print('dirty')\n")
    dirty = setup._controller_authority()
    assert dirty["controller_state"] == "dirty"
    assert dirty["controller_sha256"] != clean["controller_sha256"]

    formula.write_text("changed formula\n")
    formula_drift = setup._controller_authority()
    assert formula_drift["controller_sha256"] != dirty["controller_sha256"]


def test_controller_authority_rejects_unmerged_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "package"
    scripts = package / "skills/dstack-beads-core/scripts"
    scripts.mkdir(parents=True)
    source = scripts / "setup.py"
    source.write_text("base\n")
    (package / "bin").mkdir()
    (package / "bin/dstack").write_text("#!/bin/sh\n")
    (package / "formulas").mkdir()
    (package / "formulas/dstack-feature.formula.toml").write_text("formula\n")
    for name in ("mise.toml", "mise.lock", "pyproject.toml"):
        (package / name).write_text(f"{name}\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=package, check=True)
    subprocess.run(["git", "add", "."], cwd=package, check=True)
    commit = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm"]
    subprocess.run([*commit, "base"], cwd=package, check=True)
    subprocess.run(["git", "checkout", "-qb", "other"], cwd=package, check=True)
    source.write_text("other\n")
    subprocess.run(["git", "add", str(source.relative_to(package))], cwd=package, check=True)
    subprocess.run([*commit, "other"], cwd=package, check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=package, check=True)
    source.write_text("main\n")
    subprocess.run(["git", "add", str(source.relative_to(package))], cwd=package, check=True)
    subprocess.run([*commit, "main"], cwd=package, check=True)
    merge = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "merge", "other"],
        cwd=package,
        text=True,
        capture_output=True,
        check=False,
    )
    assert merge.returncode != 0
    monkeypatch.setattr(setup, "package_root", lambda: package)

    with pytest.raises(setup.SetupError, match="unmerged controller authority"):
        setup._controller_authority()


def test_runtime_authority_requires_exact_supported_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def check_version(self) -> str:
            return "bd version 1.2.2 (6c124203e)"

    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "require_mdbook", lambda: "mdbook")
    monkeypatch.setattr(
        setup,
        "run",
        lambda command, **kwargs: CommandResult(0, "mdbook v0.5.3\n", ""),
    )

    assert setup._runtime_authority(tmp_path) == {
        "python_version": "Python 3.14.7",
        "beads_version": "bd version 1.2.2 (6c124203e)",
        "mdbook_version": "mdbook v0.5.3",
    }

    monkeypatch.setattr(
        setup,
        "run",
        lambda command, **kwargs: CommandResult(0, "mdbook v0.5.4\n", ""),
    )
    with pytest.raises(setup.SetupError, match="unsupported mdBook version"):
        setup._runtime_authority(tmp_path)
    assert not (tmp_path / ".beads").exists()

    monkeypatch.setattr(setup.platform, "python_version", lambda: "3.13.13")
    with pytest.raises(setup.SetupError, match="unsupported Python version"):
        setup._runtime_authority(tmp_path)
    assert not (tmp_path / ".beads").exists()

    monkeypatch.setattr(setup.platform, "python_version", lambda: "3.14.7")

    class WrongClient:
        def check_version(self) -> str:
            raise DstackError("wrong Beads build")

    monkeypatch.setattr(setup, "BeadsClient", lambda root: WrongClient())
    with pytest.raises(DstackError, match="wrong Beads build"):
        setup._runtime_authority(tmp_path)
    assert not (tmp_path / ".beads").exists()


def _setup_mutation_fixture() -> dict[str, Any]:
    return {
        "schema": setup.SETUP_PLAN_SCHEMA,
        "authority": setup_authority(),
        "initialization": [
            {
                "action": "initialize-beads",
                "target": ".beads",
                "precondition": "absent",
                "options": {
                    "skip_agents": True,
                    "skip_hooks": True,
                    "non_interactive": True,
                },
            }
        ],
        "beads_issues": [
            {
                "issue_id": "feature-1",
                "set_metadata": {"dstack.scope": "café\r\n"},
                "unset_metadata": ["legacy_key"],
                "add_labels": ["dstack:work:implementation"],
                "remove_labels": ["legacy:feature"],
            }
        ],
        "dependencies": [
            {
                "action": "add",
                "source_id": "task-2",
                "destination_id": "task-1",
                "relationship_type": "blocks",
            }
        ],
        "supersessions": [{"source_id": "legacy-1", "destination_id": "feature-1"}],
        "template_deletions": [],
        "filesystem": [
            {
                "action": "create",
                "source": None,
                "destination": "docs/src/new.md",
                "expected_source_sha256": None,
                "expected_destination_sha256": None,
                "content_source": "generated",
                "generated_content": "naïve\r\n",
                "content_preservation": "generated",
                "conflict_policy": "fail-if-exists",
            }
        ],
        "git_index": [{"path": ".beads/interactions.jsonl", "action": "remove-cached"}],
        "formulas": [
            {
                "name": "dstack-feature",
                "action": "update",
                "source": "formulas/dstack-feature.formula.toml",
                "destination": ".beads/formulas/dstack-feature.formula.toml",
                "source_sha256": "a" * 64,
                "expected_destination_sha256": "d" * 64,
                "conflict_policy": "replace-reviewed",
            }
        ],
        "navigation_references": [
            {
                "action": "rewrite-link",
                "affected_path": "docs/src/SUMMARY.md",
                "old_target": "old.md#x",
                "new_target": "new.md#x",
                "expected_before_sha256": "b" * 64,
                "expected_after_sha256": "c" * 64,
            }
        ],
    }


def test_setup_plan_v4_canonical_bytes_are_order_and_unicode_stable() -> None:
    value = _setup_mutation_fixture()
    canonical = setup.canonicalize_setup_plan(value)
    reordered = {key: value[key] for key in reversed(list(value))}
    reordered["beads_issues"] = list(reversed(reordered["beads_issues"]))
    reordered["filesystem"] = list(reversed(reordered["filesystem"]))
    assert setup.canonical_setup_plan_bytes(value) == setup.canonical_setup_plan_bytes(reordered)
    assert b"caf\xc3\xa9\\n" in setup.canonical_setup_plan_bytes(value)
    assert b"\\r" not in setup.canonical_setup_plan_bytes(value)
    assert canonical["schema"] == "dstack.setup-plan/v4"
    assert setup.setup_plan_digest(value) == setup.setup_plan_digest(reordered)

    changed = copy.deepcopy(value)
    changed["authority"]["controller_sha256"] = "e" * 64
    assert setup.setup_plan_digest(value) != setup.setup_plan_digest(changed)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unexpected": True}),
        lambda value: value.update({"schema": "dstack.setup-plan/v1"}),
        lambda value: value["dependencies"].append(
            {
                "action": "remove",
                "source_id": "task-2",
                "destination_id": "task-1",
                "relationship_type": "blocks",
            }
        ),
        lambda value: value["filesystem"][0].update({"generated_content": 1.5}),
    ],
)
def test_setup_plan_v4_rejects_invalid_or_contradictory_operations(mutate) -> None:
    value = _setup_mutation_fixture()
    mutate(value)
    with pytest.raises(DstackError):
        setup.canonicalize_setup_plan(value)


class SetupPostconditionClient:
    def __init__(self, root: Path, issues: Mapping[str, dict[str, Any]], mode: str = "normal") -> None:
        self.root = root
        self.issues = copy.deepcopy(dict(issues))
        self.mode = mode

    def check_version(self) -> str:
        return "bd version 1.2.2 (6c124203e)"

    def show(self, issue_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.issues[issue_id])

    def update(self, issue_id: str, *arguments: str) -> dict[str, Any]:
        issue = self.issues[issue_id]
        if self.mode == "no-op":
            return copy.deepcopy(issue)
        iterator = iter(arguments)
        for argument in iterator:
            value = next(iterator)
            if argument == "--set-metadata":
                key, content = value.split("=", 1)
                issue.setdefault("metadata", {})[key] = content
            elif argument == "--unset-metadata":
                issue.setdefault("metadata", {}).pop(value, None)
            elif argument == "--add-label":
                issue.setdefault("labels", []).append(value)
            elif argument == "--remove-label":
                issue["labels"] = [label for label in issue.get("labels", []) if label != value]
        if self.mode == "concurrent-extra":
            issue.setdefault("dependencies", []).append({"depends_on_id": "concurrent-1", "type": "blocks"})
        return copy.deepcopy(issue)

    def add_dependency(self, source: str, destination: str, *, relation_type: str = "blocks") -> None:
        if self.mode == "wrong-direction":
            self.issues[destination].setdefault("dependencies", []).append(
                {"depends_on_id": source, "type": relation_type}
            )
            return
        relation = "tracks" if self.mode == "wrong-relation" else relation_type
        self.issues[source].setdefault("dependencies", []).append({"depends_on_id": destination, "type": relation})

    def remove_dependency(self, source: str, destination: str) -> None:
        if self.mode == "retained-relation":
            return
        self.issues[source]["dependencies"] = [
            item for item in self.issues[source].get("dependencies", []) if item.get("depends_on_id") != destination
        ]

    def supersede(self, source: str, destination: str) -> None:
        self.issues[source]["status"] = "closed"
        if self.mode != "partial-supersession":
            self.issues[source].setdefault("dependencies", []).append(
                {"depends_on_id": destination, "type": "superseded-by"}
            )


def minimal_setup_mutation(**changes: Any) -> dict[str, Any]:
    value = {
        "schema": setup.SETUP_PLAN_SCHEMA,
        "authority": setup_authority(),
        "initialization": [],
        "beads_issues": [],
        "dependencies": [],
        "supersessions": [],
        "template_deletions": [],
        "filesystem": [],
        "git_index": [],
        "formulas": [],
        "navigation_references": [],
    }
    value.update(changes)
    return setup.canonicalize_setup_plan(value)


def execute_setup_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Mapping[str, Any],
    issues: Mapping[str, dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    (tmp_path / ".beads").mkdir(exist_ok=True)
    client = SetupPostconditionClient(tmp_path, issues, mode)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: client)
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: mutation["authority"])
    monkeypatch.setattr(setup, "validate_bundle", lambda root: None)
    monkeypatch.setattr(setup, "validate_formula", lambda root, name: None)
    return setup._execute_setup_plan(tmp_path, mutation)


def issue_mutation() -> dict[str, Any]:
    return {
        "issue_id": "issue-1",
        "set_metadata": {"current": "yes"},
        "unset_metadata": ["legacy"],
        "add_labels": ["current"],
        "remove_labels": ["legacy"],
    }


def initial_issue() -> dict[str, Any]:
    return {
        "id": "issue-1",
        "status": "open",
        "metadata": {"legacy": "yes", "preserved": "yes"},
        "labels": ["legacy", "preserved"],
        "dependencies": [],
    }


def test_setup_apply_rejects_authority_drift_before_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutation = minimal_setup_mutation(
        initialization=[
            {
                "action": "initialize-beads",
                "target": ".beads",
                "precondition": "absent",
                "options": {"skip_agents": True, "skip_hooks": True, "non_interactive": True},
            }
        ]
    )
    monkeypatch.setattr(
        setup,
        "_current_setup_authority",
        lambda root: setup_authority(controller_sha256="e" * 64),
    )
    monkeypatch.setattr(setup, "ensure_beads", lambda *args, **kwargs: pytest.fail("authority drift reached mutation"))

    with pytest.raises(setup.SetupError, match="controller/runtime authority changed"):
        setup._execute_setup_plan(tmp_path, mutation)

    assert not (tmp_path / ".beads").exists()


def test_setup_apply_validates_formula_bundle_before_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutation = minimal_setup_mutation(
        initialization=[
            {
                "action": "initialize-beads",
                "target": ".beads",
                "precondition": "absent",
                "options": {"skip_agents": True, "skip_hooks": True, "non_interactive": True},
            }
        ]
    )
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: mutation["authority"])
    monkeypatch.setattr(
        setup,
        "validate_bundle",
        lambda root: (_ for _ in ()).throw(setup.SetupError("invalid formula bundle")),
    )
    monkeypatch.setattr(setup, "ensure_beads", lambda *args, **kwargs: pytest.fail("invalid bundle reached mutation"))

    with pytest.raises(setup.SetupError, match="invalid formula bundle"):
        setup._execute_setup_plan(tmp_path, mutation)

    assert not (tmp_path / ".beads").exists()


def test_setup_apply_rereads_exact_issue_postconditions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = execute_setup_mutation(
        tmp_path,
        monkeypatch,
        minimal_setup_mutation(beads_issues=[issue_mutation()]),
        {"issue-1": initial_issue()},
        mode="normal",
    )
    assert result["status"] == "ok"


def test_setup_apply_accepts_stable_dirty_controller_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mutation = minimal_setup_mutation(authority=setup_authority(controller_state="dirty"))

    result = execute_setup_mutation(tmp_path, monkeypatch, mutation, {}, mode="normal")

    assert result["status"] == "ok"


def test_setup_apply_deletes_and_rereads_reviewed_template_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".beads").mkdir()
    issue_id = "dstack-feature.template"
    present = {issue_id}

    class Client(SetupPostconditionClient):
        def show(self, selected: str) -> dict[str, Any]:
            assert selected in present
            return {"id": selected, "is_template": True}

    client = Client(tmp_path, {})
    mutation = minimal_setup_mutation(
        template_deletions=[{"action": "delete", "issue_id": issue_id, "precondition": "is-template"}]
    )
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        if command[:2] == ["bd", "delete"] and "--force" in command:
            present.clear()
        if command[:2] == ["bd", "show"]:
            return CommandResult(0 if command[2] in present else 1, "[]\n", "")
        return CommandResult(0, "[]\n", "")

    monkeypatch.setattr(setup, "BeadsClient", lambda root: client)
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: mutation["authority"])
    monkeypatch.setattr(setup, "validate_bundle", lambda root: None)
    monkeypatch.setattr(setup, "validate_formula", lambda root, name: None)
    monkeypatch.setattr(setup, "run", fake_run)
    monkeypatch.setattr(
        setup,
        "all_issue_inventory",
        lambda selected: [{"id": item, "is_template": True} for item in sorted(present)],
    )

    result = setup._execute_setup_plan(tmp_path, mutation)

    assert result["status"] == "ok"
    assert present == set()
    assert [command for command in commands if command[:2] == ["bd", "delete"]] == [
        ["bd", "delete", issue_id, "--dry-run", "--json"],
        ["bd", "delete", issue_id, "--force", "--json"],
    ]


def test_setup_apply_fails_closed_when_template_reread_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".beads").mkdir()
    issue_id = "dstack-feature.template"

    class Client(SetupPostconditionClient):
        def show(self, selected: str) -> dict[str, Any]:
            return {"id": selected, "labels": ["template"]}

    mutation = minimal_setup_mutation(
        template_deletions=[{"action": "delete", "issue_id": issue_id, "precondition": "is-template"}]
    )
    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client(tmp_path, {}))
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: mutation["authority"])
    monkeypatch.setattr(setup, "validate_bundle", lambda root: None)
    monkeypatch.setattr(setup, "validate_formula", lambda root, name: None)
    monkeypatch.setattr(setup, "run", lambda *args, **kwargs: CommandResult(0, "[]\n", ""))
    monkeypatch.setattr(
        setup,
        "all_issue_inventory",
        lambda client: (_ for _ in ()).throw(setup.SetupError("template inventory unavailable")),
    )

    with pytest.raises(setup.SetupError, match="template inventory unavailable"):
        setup._execute_setup_plan(tmp_path, mutation)


def test_setup_plan_rejects_reserved_non_template_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue_id = "dstack-feature.template"

    class Client:
        root = tmp_path

        def show(self, selected: str) -> dict[str, Any]:
            assert selected == issue_id
            return {"id": selected, "issue_type": "epic", "labels": []}

    monkeypatch.setattr(setup, "all_issue_inventory", lambda client: [{"id": issue_id}])

    with pytest.raises(setup.SetupError, match="reserved dstack template ID is used by non-template"):
        setup.legacy_template_artifacts(Client())


@pytest.mark.parametrize("mode", ["no-op", "concurrent-extra"])
def test_setup_apply_rejects_success_without_exact_issue_postconditions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    with pytest.raises(
        setup.SetupError,
        match=r"operation=beads_issue.*target_issue=issue-1.*rollback_completed=false.*mutation_state_uncertain=true",
    ):
        execute_setup_mutation(
            tmp_path,
            monkeypatch,
            minimal_setup_mutation(beads_issues=[issue_mutation()]),
            {"issue-1": initial_issue()},
            mode=mode,
        )


@pytest.mark.parametrize(
    ("mode", "operation"),
    [
        ("wrong-relation", "dependency:add"),
        ("wrong-direction", "dependency:add"),
        ("retained-relation", "dependency:remove"),
    ],
)
def test_setup_apply_rejects_wrong_or_retained_relationships(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    operation: str,
) -> None:
    action = "remove" if mode == "retained-relation" else "add"
    dependencies = [] if action == "add" else [{"depends_on_id": "target-1", "type": "blocks"}]
    issue = {**initial_issue(), "dependencies": dependencies}
    issues = {
        "issue-1": issue,
        "target-1": {**initial_issue(), "id": "target-1"},
    }
    mutation = minimal_setup_mutation(
        dependencies=[
            {
                "action": action,
                "source_id": "issue-1",
                "destination_id": "target-1",
                "relationship_type": "blocks",
            }
        ]
    )
    with pytest.raises(
        setup.SetupError,
        match=rf"operation={operation}.*target_issue=issue-1.*expected_post_state=.*observed_post_state=",
    ):
        execute_setup_mutation(tmp_path, monkeypatch, mutation, issues, mode=mode)


def test_setup_apply_rejects_partial_supersession_and_reports_no_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutation = minimal_setup_mutation(supersessions=[{"source_id": "issue-1", "destination_id": "replacement-1"}])
    with pytest.raises(
        setup.SetupError,
        match=r"operation=supersession.*target_issue=issue-1.*rollback_completed=false.*mutation_state_uncertain=true",
    ):
        execute_setup_mutation(
            tmp_path,
            monkeypatch,
            mutation,
            {"issue-1": initial_issue()},
            mode="partial-supersession",
        )


def test_setup_apply_reports_failed_rollback_and_uncertain_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".beads").mkdir()
    mutation = minimal_setup_mutation(beads_issues=[issue_mutation()])
    digest = setup.setup_plan_digest(mutation)
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "mutation_plan": mutation,
            "plan_sha256": digest,
            "preconditions": {"blocked": []},
        },
    )
    monkeypatch.setattr(
        setup,
        "_execute_setup_plan",
        lambda *args: (_ for _ in ()).throw(setup.SetupError("failed")),
    )
    monkeypatch.setattr(
        setup,
        "_restore_setup_files",
        lambda *args: (_ for _ in ()).throw(OSError("rollback failed")),
    )
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    with pytest.raises(
        setup.SetupError,
        match=r"setup-owned file restore failed: rollback failed.*rollback_completed=false.*mutation_state_uncertain=true",
    ):
        setup.apply_setup(
            tmp_path,
            initialize=False,
            force=False,
            expected_plan_sha256=digest,
        )


def test_setup_apply_requires_digest_and_executes_verified_plan_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutation = setup.canonicalize_setup_plan(_setup_mutation_fixture())
    digest = setup.setup_plan_digest(mutation)
    envelope = {
        "status": "ready",
        "mutation_plan": mutation,
        "plan_sha256": digest,
        "preconditions": {"blocked": []},
        "filesystem": [],
    }
    calls: list[dict[str, Any]] = []
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})
    monkeypatch.setattr(setup, "setup_plan", lambda *args, **kwargs: envelope)

    def execute(root: Path, plan: dict[str, Any]) -> dict[str, str]:
        (root / ".beads").mkdir()
        (root / ".beads/.gitignore").write_text("interactions.jsonl\n")
        calls.append(plan)
        return {"status": "ok"}

    monkeypatch.setattr(setup, "_execute_setup_plan", execute)

    with pytest.raises(setup.SetupError, match="plan digest is required"):
        setup.apply_setup(tmp_path, initialize=True, force=False)
    result = setup.apply_setup(
        tmp_path,
        initialize=True,
        force=False,
        expected_plan_sha256=digest,
    )

    assert result["status"] == "ok"
    assert calls == [mutation]


def _commit_tracked_interaction(repo: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    interaction = repo / ".beads/interactions.jsonl"
    interaction.parent.mkdir()
    interaction.write_bytes(b"baseline\n")
    (repo / ".beads/.gitignore").write_text("interactions.jsonl\n")
    subprocess.run(["git", "add", ".beads/.gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "add", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=repo,
        check=True,
    )
    return interaction


@pytest.mark.parametrize(
    ("mode", "worktree_bytes"),
    [
        ("unstaged", b"worktree\n"),
        ("staged", b"staged\n"),
        ("mixed", b"worktree\n"),
    ],
)
def test_forced_setup_apply_accepts_only_dirty_tracked_interaction_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    worktree_bytes: bytes,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    interaction = _commit_tracked_interaction(repo)
    interaction.write_bytes(b"staged\n" if mode != "unstaged" else worktree_bytes)
    if mode != "unstaged":
        subprocess.run(["git", "add", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
    if mode == "mixed":
        interaction.write_bytes(worktree_bytes)

    mutation = minimal_setup_mutation(git_index=[{"path": ".beads/interactions.jsonl", "action": "remove-cached"}])
    digest = setup.setup_plan_digest(mutation)
    monkeypatch.setattr(setup, "git_root", lambda root: repo)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "mutation_plan": mutation,
            "plan_sha256": digest,
            "preconditions": {"blocked": []},
            "documentation": {},
        },
    )
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})

    def execute(root: Path, plan: Mapping[str, Any]) -> dict[str, str]:
        subprocess.run(
            ["git", "rm", "--cached", "--force", "--", ".beads/interactions.jsonl"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        return {"status": "ok"}

    monkeypatch.setattr(setup, "_execute_setup_plan", execute)
    result = setup.apply_setup(
        repo,
        initialize=False,
        force=True,
        expected_plan_sha256=digest,
    )

    assert result["status"] == "ok"
    assert interaction.read_bytes() == worktree_bytes
    assert not setup.tracked(repo, ".beads/interactions.jsonl")
    assert (
        subprocess.run(
            ["git", "check-ignore", ".beads/interactions.jsonl"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == ".beads/interactions.jsonl"
    )


@pytest.mark.parametrize("special_state", ["intent-to-add", "skip-worktree", "symlink"])
def test_forced_setup_rejects_interaction_state_it_cannot_restore_exactly(tmp_path: Path, special_state: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    interaction = _commit_tracked_interaction(repo)
    if special_state in {"intent-to-add", "skip-worktree"}:
        interaction.write_bytes(b"staged\n")
        if special_state == "intent-to-add":
            subprocess.run(["git", "rm", "--cached", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
            subprocess.run(["git", "add", "-N", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
        else:
            subprocess.run(["git", "add", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
            subprocess.run(
                ["git", "update-index", "--skip-worktree", ".beads/interactions.jsonl"], cwd=repo, check=True
            )
    else:
        interaction.unlink()
        interaction.symlink_to(".gitignore")

    status, allowed = setup._setup_preflight(repo, force=True)

    assert status
    assert allowed is False


@pytest.mark.parametrize("special_state", ["assume-unchanged", "skip-worktree", "symlink"])
def test_setup_plan_rejects_clean_interaction_state_it_cannot_restore_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, special_state: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    interaction = _commit_tracked_interaction(repo)
    if special_state == "symlink":
        interaction.unlink()
        interaction.symlink_to(".gitignore")
        subprocess.run(["git", "add", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "symlink"],
            cwd=repo,
            check=True,
        )
    else:
        subprocess.run(["git", "update-index", f"--{special_state}", ".beads/interactions.jsonl"], cwd=repo, check=True)
    monkeypatch.setattr(setup, "git_root", lambda root: repo)
    monkeypatch.setattr(
        setup,
        "_current_setup_authority",
        lambda root: pytest.fail("unsupported index state reached authority discovery"),
    )

    with pytest.raises(setup.SetupError, match="unsupported Git-index state"):
        setup.setup_plan(repo, initialize=False, force=True)


def test_forced_setup_allows_known_corrupt_backup_runtime(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    backup = repo / ".beads/store.corrupt.backup/data"
    backup.parent.mkdir(parents=True)
    backup.write_text("runtime\n")

    status, allowed = setup._setup_preflight(repo, force=True)

    assert status
    assert allowed is True


def test_setup_failure_restores_exact_interaction_index_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    interaction = _commit_tracked_interaction(repo)
    interaction.write_bytes(b"staged\n")
    subprocess.run(["git", "add", "--force", ".beads/interactions.jsonl"], cwd=repo, check=True)
    interaction.write_bytes(b"worktree\n")
    mutation = minimal_setup_mutation(git_index=[{"path": ".beads/interactions.jsonl", "action": "remove-cached"}])
    digest = setup.setup_plan_digest(mutation)
    monkeypatch.setattr(setup, "git_root", lambda root: repo)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "mutation_plan": mutation,
            "plan_sha256": digest,
            "preconditions": {"blocked": []},
            "documentation": {},
        },
    )

    def fail_after_index_mutation(root: Path, plan: Mapping[str, Any]) -> dict[str, str]:
        subprocess.run(
            ["git", "rm", "--cached", "--force", "--", ".beads/interactions.jsonl"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        raise setup.SetupError("injected failure")

    monkeypatch.setattr(setup, "_execute_setup_plan", fail_after_index_mutation)
    with pytest.raises(setup.SetupError, match=r"rollback_completed=true.*mutation_state_uncertain=false"):
        setup.apply_setup(
            repo,
            initialize=False,
            force=True,
            expected_plan_sha256=digest,
        )

    staged = subprocess.run(
        ["git", "show", ":.beads/interactions.jsonl"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    assert staged == b"staged\n"
    assert interaction.read_bytes() == b"worktree\n"


def test_setup_plan_rejects_unrelated_dirty_path_before_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".beads").mkdir()
    (repo / "unrelated.txt").write_text("user work\n")
    monkeypatch.setattr(setup, "git_root", lambda root: repo)
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: setup_authority())
    monkeypatch.setattr(
        setup,
        "_setup_doc_filesystem_plan",
        lambda *args, **kwargs: pytest.fail("dirty plan reached documentation discovery"),
    )
    monkeypatch.setattr(
        setup,
        "BeadsClient",
        lambda root: pytest.fail("dirty plan reached Beads inventory"),
    )

    result = setup.setup_plan(repo, initialize=False, force=True)

    assert result["status"] == "blocked"
    assert result["preconditions"]["blocked"] == ["worktree has unrelated changes"]


def test_setup_plan_creates_missing_existing_beads_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    plan = setup._setup_plan_object(
        tmp_path,
        initialize=False,
        force=False,
        authority=setup_authority(),
        formula_actions={},
        git_index=[],
        client=None,
        inventory=[],
        template_artifacts=[],
    )

    operation = next(item for item in plan["filesystem"] if item["destination"] == ".beads/.gitignore")
    assert operation["action"] == "create"
    assert operation["generated_content"].endswith("interactions.jsonl\n")


def test_setup_without_authorization_refuses_to_initialize(tmp_path: Path) -> None:
    with pytest.raises(setup.SetupError, match="not initialized"):
        setup.ensure_beads(tmp_path, initialize=False)


def test_setup_plan_is_read_only_and_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: setup_authority())
    real_run = setup.run
    monkeypatch.setattr(
        setup,
        "run",
        lambda command, **kwargs: (
            CommandResult(0, "", "")
            if command[:2] == ["git", "status"] and command[2].startswith("--porcelain")
            else real_run(command, **kwargs)
        ),
    )

    first = setup.setup_plan(tmp_path, initialize=True, force=False)
    second = setup.setup_plan(tmp_path, initialize=True, force=False)

    assert first == second
    assert first["status"] == "ready"
    assert first["mutation_plan"]["schema"] == setup.SETUP_PLAN_SCHEMA
    assert first["authority"] == setup_authority()
    assert first["mutation_plan"]["authority"] == setup_authority()
    assert setup.setup_plan_digest(first["mutation_plan"]) == first["plan_sha256"]
    assert set(first["mutation_plan"]) == setup.SETUP_PLAN_FIELDS
    assert {item["action"] for item in first["filesystem"]} == {"create"}
    assert not (tmp_path / ".beads").exists()
    assert not (tmp_path / "docs").exists()


def setup_file_operation(
    *,
    action: str = "create",
    source: str | None = None,
    destination: str | None = None,
    source_hash: str | None = None,
    destination_hash: str | None = None,
    content: str | None = "managed\n",
) -> dict[str, Any]:
    return {
        "action": action,
        "source": source,
        "destination": destination,
        "expected_source_sha256": source_hash,
        "expected_destination_sha256": destination_hash,
        "content_source": "generated" if content is not None else "existing-source",
        "generated_content": content,
        "content_preservation": "generated" if content is not None else "byte-for-byte",
        "conflict_policy": "replace-reviewed" if action == "update" else "fail-if-exists",
    }


def test_setup_formula_install_rejects_external_symlinked_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    package = tmp_path / "package"
    source = package / "formulas/dstack-feature.formula.toml"
    source.parent.mkdir(parents=True)
    source.write_text("formula\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".beads").mkdir(parents=True)
    (repo / ".beads/formulas").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(setup, "package_root", lambda: package)
    mutation = minimal_setup_mutation(
        formulas=[
            {
                "name": "dstack-feature",
                "action": "create",
                "source": "formulas/dstack-feature.formula.toml",
                "destination": ".beads/formulas/dstack-feature.formula.toml",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "expected_destination_sha256": None,
                "conflict_policy": "fail-if-different",
            }
        ]
    )

    with pytest.raises(setup.SetupError, match=r"\.beads/formulas.*contained"):
        execute_setup_mutation(repo, monkeypatch, mutation, {}, mode="normal")

    assert list(outside.iterdir()) == []


def test_setup_filesystem_rejects_external_intermediate_parent(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "docs").mkdir(parents=True)
    (repo / "docs/guides").symlink_to(outside, target_is_directory=True)

    with pytest.raises(setup.SetupError, match=r"docs/guides/page\.md.*contained"):
        setup._setup_write_filesystem(
            repo,
            setup_file_operation(destination="docs/guides/page.md"),
        )

    assert list(outside.iterdir()) == []


def test_setup_filesystem_rejects_external_final_symlink(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    external = tmp_path / "external.md"
    external.write_text("external\n")
    destination = repo / "docs/page.md"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(external)
    original = external.read_bytes()

    with pytest.raises(setup.SetupError, match=r"docs/page\.md.*contained"):
        setup._setup_write_filesystem(
            repo,
            setup_file_operation(
                action="update",
                destination="docs/page.md",
                destination_hash=hashlib.sha256(original).hexdigest(),
            ),
        )

    assert destination.is_symlink()
    assert external.read_bytes() == original


def test_setup_filesystem_rejects_external_source_without_deleting_it(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "legacy.md"
    external.write_text("external\n")
    (repo / "docs").mkdir(parents=True)
    (repo / "docs/legacy").symlink_to(outside, target_is_directory=True)
    original = external.read_bytes()

    with pytest.raises(setup.SetupError, match=r"docs/legacy/legacy\.md.*contained"):
        setup._setup_write_filesystem(
            repo,
            setup_file_operation(
                action="delete",
                source="docs/legacy/legacy.md",
                source_hash=hashlib.sha256(original).hexdigest(),
                content=None,
            ),
        )

    assert external.read_bytes() == original


def test_setup_restore_rejects_external_symlinked_parent(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "page.md"
    external.write_text("external\n")
    (repo / "docs").mkdir(parents=True)
    (repo / "docs/recovery").symlink_to(outside, target_is_directory=True)
    original = external.read_bytes()

    with pytest.raises(setup.SetupError, match=r"docs/recovery/page\.md.*contained"):
        setup._restore_setup_files(repo, {"docs/recovery/page.md": b"restored\n"})

    assert external.read_bytes() == original


def test_setup_apply_rejects_parent_symlink_replaced_after_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    (repo / ".beads").mkdir(parents=True)
    (repo / ".beads/.gitignore").write_text("interactions.jsonl\n")
    reviewed = minimal_setup_mutation(filesystem=[setup_file_operation(destination="docs/generated/page.md")])
    digest = setup.setup_plan_digest(reviewed)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "docs").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(setup, "git_root", lambda root: repo)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})

    def execute(root: Path, mutation: Mapping[str, Any]) -> dict[str, Any]:
        setup._setup_write_filesystem(root, mutation["filesystem"][0])
        return {"status": "ok"}

    monkeypatch.setattr(setup, "_execute_setup_plan", execute)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "preconditions": {"blocked": []},
            "mutation_plan": reviewed,
            "plan_sha256": digest,
            "documentation": {},
        },
    )

    with pytest.raises(setup.SetupError, match=r"docs/generated/page\.md.*contained"):
        setup.apply_setup(repo, initialize=False, force=False, expected_plan_sha256=digest)

    assert list(outside.iterdir()) == []


def test_setup_doctor_rejects_external_beads_symlink_before_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"unchanged\n")
    (repo / ".beads").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(setup, "git_root", lambda root: repo)
    monkeypatch.setattr(
        setup,
        "BeadsClient",
        lambda root: pytest.fail("doctor reached external Beads validation"),
    )

    with pytest.raises(setup.SetupError, match=r"\.beads.*contained"):
        setup.doctor(repo, delivery_mode="merge")

    assert marker.read_bytes() == b"unchanged\n"


def test_setup_filesystem_allows_nested_and_nonexistent_destinations(
    tmp_path: Path,
) -> None:
    setup._setup_write_filesystem(
        tmp_path,
        setup_file_operation(destination="docs/nested/new/page.md"),
    )

    assert (tmp_path / "docs/nested/new/page.md").read_text() == "managed\n"


def test_setup_apply_rejects_formula_destination_drift_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    package = tmp_path / "package"
    (package / "formulas").mkdir(parents=True)
    for name in setup.FORMULA_NAMES:
        (package / "formulas" / f"{name}.formula.toml").write_text(f"{name}\n")
    (tmp_path / ".beads/formulas").mkdir(parents=True)
    for name in setup.FORMULA_NAMES:
        (tmp_path / ".beads/formulas" / f"{name}.formula.toml").write_text("old\n")

    class Client:
        def check_version(self) -> str:
            return "bd version 1.2.2 (6c124203e)"

        def list(self, **kwargs) -> list[dict]:
            return []

    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "package_root", lambda: package)
    monkeypatch.setattr(setup, "_current_setup_authority", lambda root: setup_authority())
    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "all_issue_inventory", lambda client: [])
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client, **kwargs: [])
    monkeypatch.setattr(setup, "normalize_current_features", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "normalize_current_alignments", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "_setup_normalization_plan", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "_setup_feature_design_moves", lambda *args, **kwargs: [])
    real_run = setup.run
    monkeypatch.setattr(
        setup,
        "run",
        lambda command, **kwargs: (
            CommandResult(0, "", "")
            if command[:2] == ["git", "status"] and command[2].startswith("--porcelain")
            else real_run(command, **kwargs)
        ),
    )

    reviewed = setup.setup_plan(tmp_path, initialize=False, force=True)
    reviewed_digest = reviewed["plan_sha256"]
    destination = tmp_path / ".beads/formulas/dstack-feature.formula.toml"
    destination.write_text("changed after review\n")
    monkeypatch.setattr(
        setup,
        "_execute_setup_plan",
        lambda *args: pytest.fail("formula drift reached mutation"),
    )
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)

    with pytest.raises(setup.SetupError, match="authority state changed"):
        setup.apply_setup(
            tmp_path,
            initialize=False,
            force=True,
            expected_plan_sha256=reviewed_digest,
        )
    assert destination.read_text() == "changed after review\n"


def test_setup_apply_refuses_dirty_preconditions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "dirty.txt").write_text("dirty\n")
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: pytest.fail("dirty apply reached planning"),
    )
    with pytest.raises(DstackError, match="worktree changes"):
        setup.apply_setup(
            tmp_path,
            initialize=True,
            force=False,
            expected_plan_sha256="0" * 64,
        )
    assert not (tmp_path / ".beads").exists()


def test_setup_apply_refuses_changed_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "mutation_plan": {
                "schema": setup.SETUP_PLAN_SCHEMA,
                "authority": setup_authority(),
                "initialization": [],
                "beads_issues": [],
                "dependencies": [],
                "supersessions": [],
                "template_deletions": [],
                "filesystem": [],
                "git_index": [],
                "formulas": [],
                "navigation_references": [],
            },
            "plan_sha256": "new",
            "preconditions": {"blocked": []},
            "filesystem": [],
        },
    )
    monkeypatch.setattr(
        setup,
        "install",
        lambda *args, **kwargs: pytest.fail("changed plan reached mutation"),
    )
    with pytest.raises(setup.SetupError, match="authority state changed"):
        setup.apply_setup(
            tmp_path,
            initialize=True,
            force=False,
            expected_plan_sha256="old",
        )


def test_setup_apply_cleans_internally_created_beads_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    mutation = {
        "schema": setup.SETUP_PLAN_SCHEMA,
        "authority": setup_authority(),
        "initialization": [],
        "beads_issues": [],
        "dependencies": [],
        "supersessions": [],
        "template_deletions": [],
        "filesystem": [
            {
                "action": "create",
                "source": None,
                "destination": "docs/src/index.md",
                "expected_source_sha256": None,
                "expected_destination_sha256": None,
                "content_source": "generated",
                "generated_content": "partial\\n",
                "content_preservation": "generated",
                "conflict_policy": "fail-if-exists",
            }
        ],
        "git_index": [],
        "formulas": [],
        "navigation_references": [],
    }
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "mutation_plan": mutation,
            "plan_sha256": setup.setup_plan_digest(mutation),
            "preconditions": {"blocked": []},
            "filesystem": [],
        },
    )

    def fail_install(*args, **kwargs):
        (tmp_path / ".beads").mkdir()
        created = tmp_path / "docs/src/index.md"
        created.parent.mkdir(parents=True)
        created.write_text("partial\n")
        raise setup.SetupError("injected failure")

    monkeypatch.setattr(setup, "_execute_setup_plan", fail_install)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    with pytest.raises(setup.SetupError, match="removed internally created"):
        setup.apply_setup(
            tmp_path,
            initialize=True,
            force=False,
            expected_plan_sha256=setup.setup_plan_digest(mutation),
        )
    assert not (tmp_path / ".beads").exists()
    assert not (tmp_path / "docs/src/index.md").exists()


@pytest.mark.parametrize(
    ("remote_url", "network_failure"),
    [(None, "remote"), ("git@github.com:owner/repo.git", "github")],
)
def test_doctor_reports_all_actionable_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remote_url: str | None,
    network_failure: str,
) -> None:
    (tmp_path / ".beads").mkdir()
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)

    class Client:
        def check_version(self):
            raise DstackError("wrong Beads build")

        def list(self, **kwargs):
            return []

    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(
        setup,
        "validate_docs",
        lambda root: (_ for _ in ()).throw(DstackError("bad docs")),
    )
    monkeypatch.setattr(setup, "tracked", lambda *args: True)
    monkeypatch.setattr(
        setup,
        "missing_feature_reconciliations",
        lambda client: ["missing/index.md"],
    )
    monkeypatch.setattr(
        setup,
        "worktree_records",
        lambda root: [{"worktree": "/missing", "prunable": True}],
    )
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client: [{"id": "legacy"}])
    monkeypatch.setattr(setup, "normalize_current_features", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "normalize_current_alignments", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        setup,
        "legacy_documentation_plan",
        lambda root: {
            "configured_source_moves": [],
            "referenced_content_moves": [],
            "unresolved_outside_markdown": [],
        },
    )

    def fake_run(command, **kwargs):
        if command[:2] == ["mdbook", "--version"]:
            return CommandResult(0, "mdbook v9\n", "")
        if command[:3] == ["git", "remote", "get-url"]:
            return CommandResult(
                0 if remote_url else 1,
                f"{remote_url}\n" if remote_url else "",
                "" if remote_url else "missing",
            )
        if command[:3] == ["gh", "auth", "status"]:
            return CommandResult(1, "", "not authenticated")
        if command[:4] == ["bd", "gate", "create", "--help"]:
            return CommandResult(0, "gh:pr\n", "")
        if command[:3] == ["git", "ls-files", ".beads"]:
            return CommandResult(0, ".beads/interactions.jsonl\n", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(setup, "run", fake_run)
    result = setup.doctor(tmp_path, delivery_mode="pr")

    assert result["status"] == "error"
    assert result["delivery_mode"] == "pr"
    assert set(result["failed"]) == {
        "beads_version",
        "mdbook_version",
        "formula:dstack-feature",
        "formula:dstack-project-alignment",
        "documentation",
        "interaction_policy",
        "feature_reconciliations",
        "worktrees",
        "runtime_paths",
        network_failure,
    }
    assert all(result["checks"][name]["recovery"] for name in result["failed"])


def test_setup_apply_is_retry_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    mutation = minimal_setup_mutation()
    package = tmp_path / "package"
    formulas = package / "formulas"
    formulas.mkdir(parents=True)
    for name in setup.FORMULA_NAMES:
        (formulas / f"{name}.formula.toml").write_text(name)
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "package_root", lambda: package)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "mutation_plan": mutation,
            "plan_sha256": setup.setup_plan_digest(mutation),
            "preconditions": {"blocked": []},
            "filesystem": [],
        },
    )
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})

    def fake_install(*args, **kwargs):
        destination = tmp_path / ".beads/formulas"
        destination.mkdir(parents=True, exist_ok=True)
        for name in setup.FORMULA_NAMES:
            (destination / f"{name}.formula.toml").write_text(name)
        ignore = tmp_path / ".beads/.gitignore"
        ignore.write_text("interactions.jsonl\n")
        return {"status": "ok"}

    def fake_execute(root: Path, plan: Mapping[str, Any]):
        destination = tmp_path / ".beads/formulas"
        destination.mkdir(parents=True, exist_ok=True)
        for name in setup.FORMULA_NAMES:
            (destination / f"{name}.formula.toml").write_text(name)
        ignore = tmp_path / ".beads/.gitignore"
        ignore.parent.mkdir(parents=True, exist_ok=True)
        ignore.write_text("interactions.jsonl\n")
        return {"status": "ok"}

    monkeypatch.setattr(setup, "_execute_setup_plan", fake_execute)
    digest = setup.setup_plan_digest(mutation)
    assert setup.apply_setup(tmp_path, initialize=True, force=False, expected_plan_sha256=digest)["status"] == "ok"
    assert setup.apply_setup(tmp_path, initialize=True, force=False, expected_plan_sha256=digest)["status"] == "ok"


@pytest.mark.parametrize(
    ("remote", "host"),
    [
        ("git@github.com:owner/repo.git", "github.com"),
        ("ssh://git@github.com/owner/repo.git", "github.com"),
        ("https://github.com/owner/repo.git", "github.com"),
        ("https://github.com.attacker.example/owner/repo.git", "github.com.attacker.example"),
        ("https://github.com@attacker.example/owner/repo.git", "attacker.example"),
        ("/tmp/github.com/repo.git", None),
    ],
)
def test_remote_host_parses_exact_authority(remote: str, host: str | None) -> None:
    assert setup._remote_host(remote) == host


def test_setup_parser_exposes_no_direct_legacy_repair_mutator() -> None:
    with pytest.raises(SystemExit):
        setup.build_parser().parse_args(["repair-legacy", "--force"])


def test_doctor_requires_explicit_delivery_mode(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        setup.doctor(tmp_path)  # type: ignore[call-arg]
    with pytest.raises(SystemExit):
        setup.build_parser().parse_args(["doctor", "--root", str(tmp_path)])
    args = setup.build_parser().parse_args(["doctor", "--root", str(tmp_path), "--delivery-mode", "merge"])
    assert args.delivery_mode == "merge"


def test_doctor_passes_healthy_merge_repository_without_remote_or_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    source = package / "formulas"
    installed = tmp_path / ".beads/formulas"
    source.mkdir(parents=True)
    installed.mkdir(parents=True)
    for name in setup.FORMULA_NAMES:
        (source / f"{name}.formula.toml").write_text(name)
        (installed / f"{name}.formula.toml").write_text(name)
    (tmp_path / ".beads/.gitignore").write_text("interactions.jsonl\n")
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "package_root", lambda: package)

    class Client:
        def check_version(self):
            return "bd version 1.2.2 (6c124203e)"

        def list(self, **kwargs):
            return []

    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "validate_formula", lambda *args: None)
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "missing_feature_reconciliations", lambda client: [])
    monkeypatch.setattr(setup, "worktree_records", lambda root: [])
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client: [])
    monkeypatch.setattr(setup, "normalize_current_features", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "normalize_current_alignments", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        setup,
        "legacy_documentation_plan",
        lambda root: {
            "configured_source_moves": [],
            "referenced_content_moves": [],
            "unresolved_outside_markdown": [],
        },
    )

    def fake_run(command, **kwargs):
        if command[:2] == ["mdbook", "--version"]:
            return CommandResult(0, "mdbook v0.5.3\n", "")
        if command[:3] == ["git", "remote", "get-url"]:
            raise AssertionError("merge doctor must not inspect remotes")
        if command[:4] == ["bd", "gate", "create", "--help"]:
            raise AssertionError("merge doctor must not inspect PR gate capability")
        if command[:3] == ["git", "ls-files", ".beads"]:
            return CommandResult(0, "", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(setup, "run", fake_run)
    result = setup.doctor(tmp_path, delivery_mode="merge")
    assert result["status"] == "ok"
    assert result["delivery_mode"] == "merge"
    assert result["failed"] == []
    assert result["checks"]["remote"]["status"] == "not-applicable"
    assert result["checks"]["github"]["status"] == "not-applicable"
    assert result["checks"]["pr_gate"]["status"] == "not-applicable"


def test_doctor_pr_mode_reports_missing_native_gate_capability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "package"
    source = package / "formulas"
    installed = tmp_path / ".beads/formulas"
    source.mkdir(parents=True)
    installed.mkdir(parents=True)
    for name in setup.FORMULA_NAMES:
        (source / f"{name}.formula.toml").write_text(name)
        (installed / f"{name}.formula.toml").write_text(name)
    (tmp_path / ".beads/.gitignore").write_text("interactions.jsonl\n")
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "package_root", lambda: package)

    class Client:
        def check_version(self):
            return "bd version 1.2.2 (6c124203e)"

        def list(self, **kwargs):
            return []

    monkeypatch.setattr(setup, "BeadsClient", lambda root: Client())
    monkeypatch.setattr(setup, "validate_formula", lambda *args: None)
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "missing_feature_reconciliations", lambda client: [])
    monkeypatch.setattr(setup, "worktree_records", lambda root: [])

    def fake_run(command, **kwargs):
        if command[:2] == ["mdbook", "--version"]:
            return CommandResult(0, "mdbook v0.5.3\n", "")
        if command[:3] == ["git", "remote", "get-url"]:
            return CommandResult(0, "git@github.com:owner/repo.git\n", "")
        if command[:4] == ["gh", "auth", "status", "--hostname"]:
            return CommandResult(0, "Logged in\n", "")
        if command[:4] == ["bd", "gate", "create", "--help"]:
            return CommandResult(0, "human, timer\n", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(setup, "run", fake_run)
    result = setup.doctor(tmp_path, delivery_mode="pr")
    assert result["status"] == "error"
    assert result["failed"] == ["pr_gate"]
    assert "gh:pr" in result["checks"]["pr_gate"]["error"]


def test_install_initializes_and_reports_canonical_documentation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Client:
        def check_version(self):
            return "bd version 1.2.2 (6c124203e)"

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
            return "bd version 1.2.2 (6c124203e)"

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
    assert result["missing_feature_reconciliations"] == ["docs/src/features/old/index.md"]
    assert result["interaction_log_untracked"] is True


def test_legacy_repair_reports_required_changes_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("check_version", result="bd version 1.2.2 (6c124203e)"),
    )
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: beads)
    monkeypatch.setattr(
        setup,
        "legacy_template_artifacts",
        lambda client: [{"id": "dstack-feature.template"}],
    )
    monkeypatch.setattr(setup, "_normalize_current_workflows", lambda *args, **kwargs: ["feature-1"])
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
            "manual_actions": [],
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
    feature_index.write_text("# Feature Records\n\n- [Feature](../../features/feature/design.md)\n")
    root = {
        "id": "feature-1",
        "issue_type": "epic",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {
            "dstack.base_branch": "main",
            "dstack.design_path": "docs/features/feature/design.md",
        },
    }
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root]),
        call(
            "update",
            "feature-1",
            "--set-metadata",
            "dstack.design_path=docs/src/features/feature/design.md",
            result={
                **root,
                "metadata": {
                    **root["metadata"],
                    "dstack.design_path": "docs/src/features/feature/design.md",
                },
            },
        ),
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
        "issue_type": "epic",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.design_path": "docs/features/feature/design.md"},
    }
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root]),
        call(
            "update",
            "feature-1",
            "--set-metadata",
            "dstack.design_path=docs/src/features/feature/design.md",
            result=root,
        ),
    )

    assert setup.normalize_current_features(beads, force=True) == ["feature-1"]
    assert destination.read_text() == "moved design\n"
    assert "features/feature/design.md" in (tmp_path / "docs/src/SUMMARY.md").read_text()
    beads.assert_exhausted()


def test_explicit_repair_refuses_missing_legacy_design_before_metadata_update(
    tmp_path: Path,
) -> None:
    root = {
        "id": "feature-1",
        "issue_type": "epic",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.design_path": "docs/features/feature/design.md"},
    }
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root]),
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
        "issue_type": "epic",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.design_path": design_path},
    }
    beads = ScriptedClient(
        tmp_path,
        call("list", all_statuses=True, result=[root]),
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
            result=[
                {
                    "id": "feature-1",
                    "issue_type": "epic",
                    "status": "closed",
                    "labels": ["workflow:feature", "feature:feature"],
                }
            ],
        ),
    )

    assert setup.missing_feature_reconciliations(beads) == ["docs/src/features/feature/index.md"]
    beads.assert_exhausted()


def test_forced_repair_marks_unresolved_documentation_for_manual_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("check_version", result="bd version 1.2.2 (6c124203e)"),
    )
    migration = {
        "configured_source_moves": [],
        "referenced_content_moves": [],
        "unresolved_outside_markdown": ["docs/notes/placement.md"],
        "manual_actions": [
            {
                "path": "docs/notes/placement.md",
                "action": "choose a docs/src chapter, move the file, update SUMMARY.md, and rerun setup",
            }
        ],
    }
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: beads)
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client: [])
    monkeypatch.setattr(setup, "legacy_documentation_plan", lambda root: migration)
    monkeypatch.setattr(setup, "migrate_legacy_documentation", lambda root: migration)
    monkeypatch.setattr(setup, "create_foundation", lambda root: [])
    monkeypatch.setattr(setup, "_normalize_current_workflows", lambda *args, **kwargs: [])
    monkeypatch.setattr(setup, "missing_feature_reconciliations", lambda client: [])
    monkeypatch.setattr(setup, "tracked", lambda *args: False)
    monkeypatch.setattr(setup, "ensure_interaction_log_policy", lambda root: {})
    monkeypatch.setattr(setup, "validate_docs", lambda root: {"status": "ok"})

    result = setup.repair_legacy(tmp_path, force=True)

    assert result["status"] == "manual-action-required"
    assert result["documentation_migration"] == migration
    beads.assert_exhausted()


def test_forced_repair_validates_resulting_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("check_version", result="bd version 1.2.2 (6c124203e)"),
    )
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(setup, "BeadsClient", lambda root: beads)
    monkeypatch.setattr(setup, "legacy_template_artifacts", lambda client: [])
    monkeypatch.setattr(setup, "_normalize_current_workflows", lambda *args, **kwargs: [])
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
    monkeypatch.setattr(dstack_compat, "resolve_legacy_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "is_current_feature", lambda *args: False)
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
