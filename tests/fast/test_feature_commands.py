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
        "root": {"id": "feature-1", "status": "open", "title": "Feature: Feature"},
        "slug": "feature",
        "current": True,
        "closed": False,
        "base_branch": "main",
        "design_path": "docs/src/features/feature/design.md",
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
    if hasattr(module, "validate_feature_documentation"):
        monkeypatch.setattr(
            module,
            "validate_feature_documentation",
            lambda client, context: {"status": "ok"},
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


def test_default_design_path_uses_mdbook_feature_directory(tmp_path: Path) -> None:
    assert dstack_feature.default_design_path(tmp_path, "feature") == ("docs/src/features/feature/design.md")


@pytest.mark.parametrize("slug", ["../../x", "Feature Name", ""])
def test_default_design_path_rejects_noncanonical_slug(tmp_path: Path, slug: str) -> None:
    with pytest.raises(DstackError, match="feature slug must be canonical"):
        dstack_feature.default_design_path(tmp_path, slug)


def test_initialize_rejects_design_path_outside_mdbook_features(
    monkeypatch, tmp_path: Path
) -> None:
    beads = ScriptedClient(tmp_path)
    monkeypatch.setattr(dstack_feature, "client_for", lambda root: beads)
    monkeypatch.setattr(
        dstack_feature,
        "resolve_feature",
        lambda client, selector: (_ for _ in ()).throw(DstackError("no feature matches selector")),
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector="Feature",
        title=None,
        slug=None,
        base_branch="main",
        design_path="docs/features/feature/design.md",
    )
    with pytest.raises(DstackError, match="docs/src/features/feature/design.md"):
        dstack_feature.cmd_feature_initialize(args)
    beads.assert_exhausted()


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
                "design_path": "docs/src/features/feature/design.md",
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
            "dstack.design_path=docs/src/features/feature/design.md",
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
    design = worktree / "docs/src/features/feature/design.md"
    summary = worktree / "docs/src/SUMMARY.md"
    feature_index = worktree / "docs/src/features/index.md"
    authored = design.read_text()
    assert "## Validation strategy" in authored
    assert "## Risks and tradeoffs" in authored
    assert "## Documentation impact" in authored
    assert "[Feature Records](features/index.md)" in summary.read_text()
    assert "[Feature](features/feature/design.md)" in summary.read_text()
    assert "[Feature](feature/design.md)" in feature_index.read_text()
    navigation = (summary.read_text(), feature_index.read_text())
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    assert design.read_text() == authored
    assert (summary.read_text(), feature_index.read_text()) == navigation
    assert [item["created"] for item in output] == [True, False]


def test_scaffold_reconciliation_creates_once_and_updates_navigation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    worktree = tmp_path / "worktree"
    design = worktree / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("accepted design\n")
    (worktree / "docs/src/features/index.md").write_text(
        "# Feature Records\n\n- [Authored catalog title](feature/design.md)\n"
    )
    (worktree / "docs/src/SUMMARY.md").write_text(
        "# Summary\n\n- [Feature Records](features/index.md)\n"
        "  - [Authored chapter title](features/feature/design.md)\n"
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    args = argparse.Namespace(root=tmp_path, selector="feature-1")

    assert dstack_feature.cmd_feature_scaffold_reconciliation(args) == 0
    reconciliation = design.with_name("index.md")
    authored = reconciliation.read_text()
    assert "## Delivered capability" in authored
    assert "## Design reconciliation" in authored
    assert "[Authored catalog title](feature/index.md)" in (worktree / "docs/src/features/index.md").read_text()
    summary_path = worktree / "docs/src/SUMMARY.md"
    summary = summary_path.read_text()
    assert summary.count("[Feature Records](features/index.md)") == 1
    assert "  - [Authored chapter title](features/feature/index.md)" in summary
    assert "    - [Design](features/feature/design.md)" in summary

    reconciliation.write_text("authored reconciliation\n")
    summary_path.write_text(summary.replace("[Design]", "[Accepted intent]"))
    assert dstack_feature.cmd_feature_scaffold_design(args) == 0
    assert "[Authored catalog title](feature/index.md)" in (worktree / "docs/src/features/index.md").read_text()
    assert "[Accepted intent](features/feature/design.md)" in summary_path.read_text()
    assert dstack_feature.cmd_feature_scaffold_reconciliation(args) == 0
    assert reconciliation.read_text() == "authored reconciliation\n"
    assert [item["created"] for item in output] == [True, False, False]


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
    design = worktree / "docs/src/features/feature/design.md"
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


def test_finish_task_leaves_workstream_and_closeout_open(
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
            "show",
            "implementation-1",
            result={"id": "implementation-1", "status": "open"},
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
    assert output[0]["workstream"]["closed_now"] is False
    assert output[0]["workstream"]["workstream"]["status"] == "open"
    assert output[0]["workstream"]["closeout"]["status"] == "open"
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


def test_claim_closeout_keeps_closed_closeout_idempotent(
    monkeypatch, tmp_path: Path
) -> None:
    closeout = {"id": "closeout-1", "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    assert dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output[0]["closeout"] == closeout
    assert output[0]["already_closed"] is True
    beads.assert_exhausted()


def test_claim_closeout_delegates_readiness_to_beads(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    with pytest.raises(DstackError, match="not ready according to Beads"):
        dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_claim_closeout_refuses_open_native_child_before_ready_claim(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call(
            "children",
            "implementation-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="native-child"):
        dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_claim_closeout_releases_raced_claim_when_new_child_appears(monkeypatch, tmp_path: Path) -> None:
    claimed = {"id": "closeout-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[claimed],
        ),
        call(
            "children",
            "implementation-1",
            result=[{"id": "raced-child", "status": "open"}],
        ),
        call(
            "update",
            "closeout-1",
            "--status",
            "open",
            result={"id": "closeout-1", "status": "open"},
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)

    with pytest.raises(DstackError, match="raced-child"):
        dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1"))
    beads.assert_exhausted()


def test_claim_closeout_uses_native_atomic_ready_claim(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "open"}
    claimed = {"id": "closeout-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[claimed],
        ),
        call("children", "implementation-1", result=[]),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    assert dstack_feature.cmd_feature_claim_closeout(argparse.Namespace(root=tmp_path, selector="feature-1")) == 0
    assert output[0]["closeout"] == claimed
    beads.assert_exhausted()


def test_closeout_validation_rejects_missing_documentation_impact_target(monkeypatch, tmp_path: Path) -> None:
    import dstack_docs

    worktree = tmp_path / "worktree"
    dstack_docs.create_foundation(worktree)
    design = worktree / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text(
        "# Design\n\n## Documentation impact\n\n[Missing](../../guides/missing.md)\n"
    )
    design.with_name("index.md").write_text("# Reconciliation\n")
    dstack_feature.ensure_feature_navigation(
        worktree, slug="feature", title="Feature", reconciled=True
    )
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )
    monkeypatch.setattr(dstack_docs.shutil, "which", lambda name: "/usr/bin/true")

    with pytest.raises(DstackError, match="guides/missing.md"):
        dstack_feature.validate_feature_documentation(ScriptedClient(tmp_path), view())


def test_finish_closeout_requires_reconciliation_before_beads_mutation(
    monkeypatch, tmp_path: Path
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    monkeypatch.setattr(
        dstack_feature,
        "validate_feature_documentation",
        lambda client, context: (_ for _ in ()).throw(DstackError("feature reconciliation does not exist")),
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )

    with pytest.raises(DstackError, match="reconciliation"):
        dstack_feature.cmd_feature_finish_closeout(args)

    assert output == []
    beads.assert_exhausted()


def test_finish_closeout_keeps_closed_closeout_idempotent(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "closed"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "status": "closed",
                "close_reason": "Delivered by fast-forward merge",
            },
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
    assert output[0]["closeout"] == closeout
    beads.assert_exhausted()


def test_finish_closeout_refuses_when_beads_does_not_mark_it_ready(monkeypatch, tmp_path: Path) -> None:
    closeout = {"id": "closeout-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result=closeout),
        call("children", "implementation-1", result=[]),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="feature-1",
        reason="Closeout completed",
        summary_file=None,
    )
    with pytest.raises(DstackError, match="not ready according to Beads"):
        dstack_feature.cmd_feature_finish_closeout(args)
    beads.assert_exhausted()


def test_finish_closeout_closes_once(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
        call(
            "ready_children",
            "feature-1",
            label="dstack:step:closeout",
            claim=True,
            result=[{"id": "closeout-1", "status": "in_progress"}],
        ),
        call(
            "close",
            "closeout-1",
            "Closeout completed",
            result={"id": "closeout-1", "status": "closed"},
        ),
        call(
            "show",
            "feature-1",
            result={
                "id": "feature-1",
                "status": "closed",
                "close_reason": "all steps complete",
            },
        ),
        call(
            "reopen",
            "feature-1",
            "Await delivery",
            result={"id": "feature-1", "status": "open"},
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


def test_closeout_validation_rejects_untouched_reconciliation_scaffold(monkeypatch, tmp_path: Path) -> None:
    import dstack_docs
    from dstack_commands import RECONCILIATION_SCAFFOLD

    worktree = tmp_path / "worktree"
    dstack_docs.create_foundation(worktree)
    design = worktree / "docs/src/features/feature/design.md"
    design.parent.mkdir(parents=True)
    design.write_text("# Design\n")
    design.with_name("index.md").write_text(RECONCILIATION_SCAFFOLD.format(title="Feature"))
    dstack_feature.ensure_feature_navigation(worktree, slug="feature", title="Feature", reconciled=True)
    monkeypatch.setattr(
        dstack_feature,
        "feature_branch_context",
        lambda *args: ("feat/feature", worktree, "main"),
    )

    with pytest.raises(DstackError, match="untouched scaffold"):
        dstack_feature.validate_feature_documentation(ScriptedClient(tmp_path), view())


def test_finish_workstream_counts_unlabeled_native_children(monkeypatch, tmp_path: Path) -> None:
    implementation = {"id": "implementation-1", "status": "open"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "implementation-1", result=implementation),
        call(
            "children",
            "implementation-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
        call("show", "implementation-1", result=implementation),
        call("show", "closeout-1", result={"id": "closeout-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, dstack_feature, beads)
    args = argparse.Namespace(root=tmp_path, selector="feature-1", quiet=False)
    assert dstack_feature.cmd_feature_finish_workstream(args) == 0
    assert output[0]["open_items"] == ["native-child"]
    assert output[0]["closed_now"] is False
    beads.assert_exhausted()
