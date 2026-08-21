from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_feature
from dstack_commands import DstackError

from scripted import ScriptedClient, call


def view(**overrides) -> dict:
    value = {
        "root": {"id": "feature-1", "status": "open"},
        "slug": "feature",
        "current": True,
        "closed": False,
        "base_branch": "main",
        "design_path": "docs/features/feature/design.md",
        "approved_design_sha256": "digest",
        "current_design_sha256": "digest",
        "design_approved": True,
        "human_gate": {"id": "gate-1", "status": "open"},
        "steps": {
            "specification": {"id": "specification-1", "status": "open"},
            "approval": {"id": "approval-1", "status": "open"},
            "implementation": {"id": "implementation-1", "status": "open"},
            "closeout": {"id": "closeout-1", "status": "open"},
        },
        "work_items": [],
    }
    value.update(overrides)
    return value


def patch_command(monkeypatch, module, beads, current=None):
    current = current or view()
    monkeypatch.setattr(module, "client_for", lambda root: beads)
    monkeypatch.setattr(module, "feature_context", lambda client, selector: current)
    monkeypatch.setattr(
        module,
        "feature_design_state",
        lambda client, context: {
            "current_design_sha256": current.get("current_design_sha256"),
            "design_approved": current.get("design_approved", False),
        },
    )
    output = []
    monkeypatch.setattr(module, "emit", output.append)
    return output


def test_resolve_and_inspect_emit_observed_state(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    current = view()
    monkeypatch.setattr(dstack_feature, "client_for", lambda root: beads)
    monkeypatch.setattr(
        dstack_feature,
        "resolve_feature",
        lambda client, selector: current["root"],
    )
    monkeypatch.setattr(dstack_feature, "feature_slug", lambda root: "feature")
    monkeypatch.setattr(dstack_feature, "is_current_feature", lambda client, root: True)
    monkeypatch.setattr(dstack_feature, "feature_view", lambda client, selector: current)
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    assert dstack_feature.cmd_feature_resolve(argparse.Namespace(root=tmp_path, selector="feature")) == 0
    assert dstack_feature.cmd_feature_inspect(argparse.Namespace(root=tmp_path, selector="feature")) == 0
    assert output[0]["root"]["id"] == "feature-1"
    assert output[1]["steps"]["implementation"]["id"] == "implementation-1"


@pytest.mark.parametrize(
    ("feature_directory", "expected"),
    [
        ("docs/src/features", "docs/src/features/feature/design.md"),
        ("docs/features", "docs/features/feature/design.md"),
        (None, "docs/features/feature/design.md"),
    ],
)
def test_default_design_path_uses_repository_convention(
    tmp_path: Path, feature_directory: str | None, expected: str
) -> None:
    if feature_directory:
        (tmp_path / feature_directory).mkdir(parents=True)
    assert dstack_feature.default_design_path(tmp_path, "feature") == expected


def test_initialize_pours_formula_and_records_only_stable_identity(
    monkeypatch, tmp_path: Path
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "pour",
            "dstack-feature",
            {
                "feature_title": "Feature",
                "feature_slug": "feature",
                "design_path": "docs/features/feature/design.md",
            },
            result={"root_id": "feature-1"},
        ),
        call(
            "update",
            "feature-1",
            "--title",
            "Feature: Feature",
            "--add-label",
            "workflow:feature",
            "--add-label",
            "feature:feature",
            "--set-metadata",
            "dstack.base_branch=main",
            "--set-metadata",
            "dstack.design_path=docs/features/feature/design.md",
            result={"id": "feature-1"},
        ),
    )
    monkeypatch.setattr(dstack_feature, "client_for", lambda root: beads)
    monkeypatch.setattr(
        dstack_feature,
        "resolve_feature",
        lambda client, selector: (_ for _ in ()).throw(DstackError("no feature matches selector")),
    )
    monkeypatch.setattr(dstack_feature, "require_installed_formula", lambda *args: None)
    monkeypatch.setattr(
        dstack_feature,
        "ensure_feature_worktree",
        lambda *args: ("feat/feature", tmp_path / "worktree", True, True),
    )
    monkeypatch.setattr(dstack_feature, "feature_context", lambda *args: view())
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)

    args = argparse.Namespace(
        root=tmp_path,
        selector="Feature",
        title=None,
        slug=None,
        base_branch="main",
        design_path=None,
    )
    assert dstack_feature.cmd_feature_initialize(args) == 0
    assert output[0]["created"] is True
    assert output[0]["branch"] == "feat/feature"
    beads.assert_exhausted()


def test_add_task_delegates_acceptance_and_dependencies(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "create",
            "Implement outcome",
            parent="implementation-1",
            labels=["dstack:work:implementation"],
            dependencies=["approval-1", "blocker-1"],
            description="details",
            acceptance="observable result",
            priority=1,
            result={"id": "task-1"},
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        title="Implement outcome",
        description="details",
        description_file=None,
        acceptance="observable result",
        acceptance_file=None,
        priority=1,
        depends_on=["blocker-1"],
    )
    assert dstack_feature.cmd_feature_add_task(args) == 0
    assert output == [{"status": "ok", "task": {"id": "task-1"}}]
    beads.assert_exhausted()


def test_add_task_rejects_blank_acceptance_before_write(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        title="Invalid",
        description=None,
        description_file=None,
        acceptance="  ",
        acceptance_file=None,
        priority=2,
        depends_on=[],
    )
    with pytest.raises(DstackError, match="acceptance criteria is required"):
        dstack_feature.cmd_feature_add_task(args)
    beads.assert_exhausted()


def test_scaffold_design_creates_once_without_overwriting(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    args = argparse.Namespace(root=tmp_path, selector="feature-1")
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    design = worktree / "docs/features/feature/design.md"
    authored = design.read_text()
    assert "## Validation strategy" in authored
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    assert design.read_text() == authored
    assert [item["created"] for item in output] == [True, False]


def test_claim_spec_claims_open_specification(monkeypatch, tmp_path: Path) -> None:
    claimed = {"id": "specification-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("update", "specification-1", "--claim", result=claimed),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    assert dstack_feature.cmd_feature_claim_spec(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output[0]["specification"] == claimed
    beads.assert_exhausted()


def test_approve_spec_persists_digest_and_resolves_native_gate(
    monkeypatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "worktree"
    design = worktree / "docs/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("accepted design\n")
    # Digest is dynamic, so verify the exact call with a tiny recorder rather than
    # teaching the scripted client matching rules.
    calls = []
    beads = ScriptedClient(tmp_path)
    beads.update = lambda *args: calls.append(("update", *args)) or {"id": args[0]}
    beads.close = lambda *args: calls.append(("close", *args)) or {"id": args[0], "status": "closed"}
    beads.resolve_gate = lambda *args: calls.append(("resolve_gate", *args)) or {"id": args[0], "status": "closed"}
    beads.show = lambda issue_id: {"id": issue_id, "status": "open"}
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    monkeypatch.setattr(
        dstack_feature,
        "human_gate_for_step",
        lambda *args, **kwargs: {"id": "gate-1", "status": "open"},
    )
    args = argparse.Namespace(root=tmp_path, selector="feature-1", summary_file=None)
    assert dstack_feature.cmd_feature_approve_spec(args) == 0
    assert calls[0][0:2] == ("update", "feature-1")
    assert str(calls[0][-1]).startswith("dstack.approved_design_sha256=")
    assert ("resolve_gate", "gate-1", "Specification approved") in calls
    assert ("close", "approval-1", "Implementation authorized") in calls


def test_claim_next_uses_native_ready_result(monkeypatch, tmp_path: Path) -> None:
    task = {"id": "task-1", "status": "claimed", "owner": "worker"}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            claim=True,
            result=[task],
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", task=None)
    assert dstack_feature.cmd_feature_claim_next(args) == 0
    assert output == [{"status": "ok", "task": task, "feature": "feature-1"}]
    beads.assert_exhausted()


def test_claim_next_rejects_explicit_task_not_ready(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "task-1",
            result={"id": "task-1", "parent": "implementation-1", "status": "open"},
        ),
        call(
            "ready_children",
            "implementation-1",
            label="dstack:work:implementation",
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", task="task-1")
    with pytest.raises(DstackError, match="not currently ready"):
        dstack_feature.cmd_feature_claim_next(args)
    beads.assert_exhausted()


def test_finish_task_reuses_client_for_workstream_fan_in(
    monkeypatch, tmp_path: Path
) -> None:
    task = {"id": "task-1", "parent": "implementation-1", "status": "open"}
    closed_task = {**task, "status": "closed"}
    client_requests = []
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result={**task, "status": "in_progress"}),
        call("close", "task-1", "Implementation completed", result=closed_task),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "open"},
        ),
        call("children", "implementation-1", result=[closed_task]),
        call(
            "close",
            "implementation-1",
            "All implementation work completed",
            result={"id": "implementation-1", "status": "closed"},
        ),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "closed"},
        ),
        call(
            "show",
            "closeout-1",
            result={"id": "closeout-1", "status": "open"},
        ),
    )
    current = view()
    monkeypatch.setattr(
        dstack_feature,
        "client_for",
        lambda root: client_requests.append(root) or beads,
    )
    monkeypatch.setattr(dstack_feature, "feature_context", lambda client, selector: current)
    monkeypatch.setattr(
        dstack_feature,
        "feature_design_state",
        lambda client, context: {"design_approved": True},
    )
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(
        dstack_feature,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "subject": "change", "paths": ["file.py"]}],
    )
    output = []
    monkeypatch.setattr(dstack_feature, "emit", output.append)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        task="task-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    assert dstack_feature.cmd_feature_finish_task(args) == 0
    assert client_requests == [tmp_path]
    assert output[0]["workstream"]["closed_now"] is True
    beads.assert_exhausted()


def test_finish_task_requires_git_evidence(monkeypatch, tmp_path: Path) -> None:
    task = {"id": "task-1", "parent": "implementation-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "task-1", result=task),
        call("update", "task-1", "--claim", result=task),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_feature, "evidence_for_bead", lambda *args: [])
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        task="task-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    with pytest.raises(DstackError, match="no reachable commit"):
        dstack_feature.cmd_feature_finish_task(args)
    beads.assert_exhausted()


def test_finish_workstream_closes_only_after_all_children(monkeypatch, tmp_path: Path) -> None:
    implementation = {"id": "implementation-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "implementation-1", result=implementation),
        call(
            "children",
            "implementation-1",
            result=[
                {
                    "id": "task-1",
                    "status": "closed",
                    "labels": ["dstack:work:implementation"],
                }
            ],
        ),
        call(
            "close",
            "implementation-1",
            "All implementation work completed",
            result={"id": "implementation-1", "status": "closed"},
        ),
        call(
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "closed"},
        ),
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", quiet=False)
    assert dstack_feature.cmd_feature_finish_workstream(args) == 0
    assert output[0]["closed_now"] is True
    beads.assert_exhausted()


def test_claim_closeout_refuses_open_blocker(monkeypatch, tmp_path: Path) -> None:
    closeout = {
        "id": "closeout-1",
        "status": "open",
        "dependencies": [{"depends_on_id": "task-1", "type": "blocks"}],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("show", "task-1", result={"id": "task-1", "status": "open"}),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="closeout remains blocked"):
        dstack_feature.cmd_feature_claim_closeout(
            argparse.Namespace(root=tmp_path, selector="feature-1")
        )
    beads.assert_exhausted()


def test_finish_closeout_closes_once(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call(
            "update",
            "closeout-1",
            "--claim",
            result={"id": "closeout-1", "status": "in_progress"},
        ),
        call(
            "close",
            "closeout-1",
            "Closeout completed",
            result={"id": "closeout-1", "status": "closed"},
        ),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )
    assert dstack_feature.cmd_feature_finish_closeout(args) == 0
    assert output[0]["feature"] == "feature-1"
    assert output[0]["closeout"]["status"] == "closed"
    beads.assert_exhausted()


def test_safe_design_file_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(DstackError, match="repository-relative"):
        dstack_feature.safe_design_file(tmp_path, "../outside.md")
