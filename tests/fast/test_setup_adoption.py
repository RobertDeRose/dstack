from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

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


def test_raw_poured_topology_rejects_invalid_root_before_identity_update() -> None:
    class Client:
        def show(self, issue_id: str) -> dict[str, Any]:
            return {"id": issue_id, "status": "closed", "issue_type": "epic"}

        def children(self, parent: str) -> list[dict[str, Any]]:
            return []

    with pytest.raises(DstackError, match="invalid status"):
        dstack_adoption_apply.validate_target_topology(Client(), "new-root")


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
    monkeypatch.setattr(dstack_compat, "resolve_feature", lambda *args: legacy)
    monkeypatch.setattr(dstack_compat, "feature_context", lambda *args: {"current": False})
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
            labels=["workflow:feature"],
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


def test_setup_without_authorization_refuses_to_initialize(tmp_path: Path) -> None:
    with pytest.raises(setup.SetupError, match="not initialized"):
        setup.ensure_beads(tmp_path, initialize=False)


def test_setup_plan_is_read_only_and_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    real_run = setup.run
    monkeypatch.setattr(
        setup,
        "run",
        lambda command, **kwargs: (
            CommandResult(0, "", "") if command[:3] == ["git", "status", "--porcelain"] else real_run(command, **kwargs)
        ),
    )

    first = setup.setup_plan(tmp_path, initialize=True, force=False)
    second = setup.setup_plan(tmp_path, initialize=True, force=False)

    assert first == second
    assert first["status"] == "ready"
    assert {item["action"] for item in first["filesystem"]} == {"create"}
    assert not (tmp_path / ".beads").exists()
    assert not (tmp_path / "docs").exists()


def test_setup_apply_refuses_dirty_preconditions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "dirty.txt").write_text("dirty\n")
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: pytest.fail("dirty apply reached planning"),
    )
    with pytest.raises(DstackError, match="worktree changes"):
        setup.apply_setup(tmp_path, initialize=True, force=False)
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
    monkeypatch.setattr(setup, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(
        setup,
        "setup_plan",
        lambda *args, **kwargs: {
            "status": "ready",
            "preconditions": {"blocked": []},
            "filesystem": [{"path": "docs/src/index.md", "action": "create"}],
        },
    )

    def fail_install(*args, **kwargs):
        (tmp_path / ".beads").mkdir()
        created = tmp_path / "docs/src/index.md"
        created.parent.mkdir(parents=True)
        created.write_text("partial\n")
        raise setup.SetupError("injected failure")

    monkeypatch.setattr(setup, "install", fail_install)
    monkeypatch.setattr(setup, "ensure_clean_worktree", lambda root: None)
    with pytest.raises(setup.SetupError, match="removed internally created"):
        setup.apply_setup(tmp_path, initialize=True, force=False)
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

    monkeypatch.setattr(setup, "install", fake_install)
    assert setup.apply_setup(tmp_path, initialize=True, force=False)["status"] == "ok"
    assert setup.apply_setup(tmp_path, initialize=True, force=False)["status"] == "ok"


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
    monkeypatch.setattr(setup, "normalize_current_features", lambda client, force: ["feature-1"])
    monkeypatch.setattr(setup, "normalize_current_alignments", lambda client, force: [])
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
    feature_index.write_text("# Feature Records\n\n- [Feature](../../features/feature/design.md)\n")
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
            result={
                **root,
                "metadata": {
                    **root["metadata"],
                    "dstack.design_path": "docs/src/features/feature/design.md",
                },
            },
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
    assert "features/feature/design.md" in (tmp_path / "docs/src/SUMMARY.md").read_text()
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

    assert setup.missing_feature_reconciliations(beads) == ["docs/src/features/feature/index.md"]
    beads.assert_exhausted()


def test_forced_repair_validates_resulting_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("check_version", result="bd version 1.2.2 (6c124203e)"),
    )
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
    assert dstack_commands.preserve_external_blockers(beads, source, "feature-1") == ["blocker-1"]
    beads.assert_exhausted()
