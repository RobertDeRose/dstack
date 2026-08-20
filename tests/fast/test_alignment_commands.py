from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_alignment
from dstack_commands import DstackError

from scripted import ScriptedClient, call


def alignment_view(**overrides) -> dict:
    value = {
        "root": {"id": "alignment-1", "status": "open"},
        "slug": "alignment",
        "target_branch": "main",
        "scope": "repository",
        "human_gate": {"id": "gate-1", "status": "open"},
        "steps": {
            "analysis": {"id": "analysis-1", "status": "open"},
            "approval": {"id": "approval-1", "status": "open"},
            "corrections": {"id": "corrections-1", "status": "open"},
            "landing": {"id": "landing-1", "status": "open"},
        },
    }
    value.update(overrides)
    return value


def patch_command(monkeypatch, beads, current=None):
    current = current or alignment_view()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: beads)
    monkeypatch.setattr(
        dstack_alignment, "alignment_context", lambda client, selector: current
    )
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    return output


def test_inspect_emits_observed_alignment(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    output = patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_view",
        lambda client, selector: alignment_view(),
    )
    assert dstack_alignment.cmd_alignment_inspect(
        argparse.Namespace(root=tmp_path, selector="alignment")
    ) == 0
    assert output[0]["steps"]["corrections"]["id"] == "corrections-1"


def test_initialize_pours_formula_and_records_stable_identity(
    monkeypatch, tmp_path: Path
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "pour",
            "dstack-project-alignment",
            {
                "audit_title": "Repository Alignment",
                "audit_slug": "repository-alignment",
                "scope": "whole repository",
            },
            result={"root_id": "alignment-1"},
        ),
        call(
            "update",
            "alignment-1",
            "--title",
            "Project alignment: Repository Alignment",
            "--add-label",
            "workflow:project-alignment",
            "--add-label",
            "audit:repository-alignment",
            "--set-metadata",
            "dstack.target_branch=main",
            "--set-metadata",
            "dstack.scope=whole repository",
            result={"id": "alignment-1"},
        ),
    )
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: beads)
    views = iter(
        [
            DstackError("alignment selector resolved to 0 roots"),
            alignment_view(slug="repository-alignment"),
        ]
    )

    def observed(client, selector):
        value = next(views)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(dstack_alignment, "alignment_context", observed)
    monkeypatch.setattr(dstack_alignment, "require_installed_formula", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "branch_exists", lambda *args: True)
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path / "worktree")
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    args = argparse.Namespace(
        root=tmp_path,
        title="Repository Alignment",
        slug=None,
        target_branch="main",
        scope="whole repository",
    )
    assert dstack_alignment.cmd_alignment_initialize(args) == 0
    assert output[0]["worktree"].endswith("worktree")
    beads.assert_exhausted()


def test_add_correction_delegates_native_dependencies(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "create",
            "Fix drift",
            parent="corrections-1",
            labels=["dstack:work:correction"],
            dependencies=["approval-1", "external-1"],
            description="details",
            acceptance="observable",
            priority=2,
            result={"id": "correction-1"},
        ),
    )
    output = patch_command(monkeypatch, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        title="Fix drift",
        description="details",
        description_file=None,
        acceptance="observable",
        acceptance_file=None,
        priority=2,
        depends_on=["external-1"],
    )
    assert dstack_alignment.cmd_alignment_add_correction(args) == 0
    assert output == [{"status": "ok", "correction": {"id": "correction-1"}}]
    beads.assert_exhausted()


def test_finish_plan_claims_comments_and_closes_analysis(
    monkeypatch, tmp_path: Path
) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("Material plan")
    calls = []
    beads = ScriptedClient(tmp_path)
    beads.update = lambda *args: calls.append(("update", *args)) or {
        "id": args[0],
        "status": "in_progress",
    }
    beads.add_comment = lambda *args: calls.append(("comment", *args))
    beads.close = lambda *args: calls.append(("close", *args)) or {
        "id": args[0],
        "status": "closed",
    }
    output = patch_command(monkeypatch, beads)
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", summary_file=summary)
    assert dstack_alignment.cmd_alignment_finish_plan(args) == 0
    assert ("comment", "analysis-1", "Material plan") in calls
    assert ("close", "analysis-1", "Corrective plan prepared") in calls
    assert output[0]["audit"] == "alignment-1"
    assert output[0]["analysis"]["status"] == "closed"


def test_approve_resolves_gate_and_authorizes_execution(monkeypatch, tmp_path: Path) -> None:
    calls = []
    beads = ScriptedClient(tmp_path)
    beads.resolve_gate = lambda *args: calls.append(("resolve", *args))
    beads.update = lambda *args: calls.append(("update", *args)) or {
        "id": args[0],
        "status": "in_progress",
    }
    beads.close = lambda *args: calls.append(("close", *args))
    output = patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "human_gate_for_step",
        lambda *args, **kwargs: {"id": "gate-1", "status": "open"},
    )
    assert dstack_alignment.cmd_alignment_approve(
        argparse.Namespace(root=tmp_path, selector="alignment-1")
    ) == 0
    assert ("resolve", "gate-1", "Corrective plan approved") in calls
    assert ("close", "approval-1", "Corrective execution authorized") in calls
    assert output[0]["audit"] == "alignment-1"


def test_claim_next_delegates_readiness_and_claim(monkeypatch, tmp_path: Path) -> None:
    correction = {"id": "correction-1", "status": "claimed"}
    beads = ScriptedClient(
        tmp_path,
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            claim=True,
            result=[correction],
        ),
    )
    output = patch_command(monkeypatch, beads)
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", task=None)
    assert dstack_alignment.cmd_alignment_claim_next(args) == 0
    assert output == [{"status": "ok", "correction": correction, "audit": "alignment-1"}]
    beads.assert_exhausted()


def test_finish_task_reuses_client_for_workstream_fan_in(
    monkeypatch, tmp_path: Path
) -> None:
    task = {"id": "correction-1", "parent": "corrections-1", "status": "open"}
    closed_task = {**task, "status": "closed"}
    client_requests = []
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call(
            "update",
            "correction-1",
            "--claim",
            result={**task, "status": "in_progress"},
        ),
        call("close", "correction-1", "Correction completed", result=closed_task),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
        call("children", "corrections-1", result=[closed_task]),
        call(
            "close",
            "corrections-1",
            "All corrections completed",
            result={"id": "corrections-1", "status": "closed"},
        ),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "closed"},
        ),
    )
    current = alignment_view()
    monkeypatch.setattr(
        dstack_alignment,
        "client_for",
        lambda root: client_requests.append(root) or beads,
    )
    monkeypatch.setattr(
        dstack_alignment, "alignment_context", lambda client, selector: current
    )
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(
        dstack_alignment,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "subject": "change", "paths": ["file.py"]}],
    )
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        task="correction-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    assert dstack_alignment.cmd_alignment_finish_task(args) == 0
    assert client_requests == [tmp_path]
    assert output[0]["workstream"]["open_items"] == []
    beads.assert_exhausted()


def test_finish_task_requires_reachable_git_evidence(monkeypatch, tmp_path: Path) -> None:
    task = {"id": "correction-1", "parent": "corrections-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call("update", "correction-1", "--claim", result=task),
    )
    patch_command(monkeypatch, beads)
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "evidence_for_bead", lambda *args: [])
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        task="correction-1",
        reason=None,
        summary_file=None,
        no_repository_change=False,
    )
    with pytest.raises(DstackError, match="no commit"):
        dstack_alignment.cmd_alignment_finish_task(args)
    beads.assert_exhausted()


def test_finish_workstream_closes_after_native_children_are_closed(
    monkeypatch, tmp_path: Path
) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call(
            "children",
            "corrections-1",
            result=[
                {
                    "id": "correction-1",
                    "status": "closed",
                    "labels": ["dstack:work:correction"],
                }
            ],
        ),
        call(
            "close",
            "corrections-1",
            "All corrections completed",
            result={"id": "corrections-1", "status": "closed"},
        ),
        call("show", "corrections-1", result={"id": "corrections-1", "status": "closed"}),
    )
    output = patch_command(monkeypatch, beads)
    assert dstack_alignment.cmd_alignment_finish_workstream(
        argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
    ) == 0
    assert output[0]["open_items"] == []
    beads.assert_exhausted()


def test_claim_landing_refuses_open_native_blocker(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "landing-1",
            result={
                "id": "landing-1",
                "status": "open",
                "dependencies": [{"depends_on_id": "task-1", "type": "blocks"}],
            },
        ),
        call("show", "task-1", result={"id": "task-1", "status": "open"}),
    )
    patch_command(monkeypatch, beads)
    args = argparse.Namespace(root=tmp_path, selector="alignment-1")
    with pytest.raises(DstackError, match="remains blocked"):
        dstack_alignment.cmd_alignment_claim_landing(args)
    beads.assert_exhausted()


def test_finish_landing_closes_once(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call(
            "update",
            "landing-1",
            "--claim",
            result={"id": "landing-1", "status": "in_progress"},
        ),
        call(
            "close",
            "landing-1",
            "Alignment landing completed",
            result={"id": "landing-1", "status": "closed"},
        ),
    )
    output = patch_command(monkeypatch, beads)
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        reason="Alignment landing completed",
        summary_file=None,
    )
    assert dstack_alignment.cmd_alignment_finish_landing(args) == 0
    assert output[0]["audit"] == "alignment-1"
    assert output[0]["landing"]["status"] == "closed"
    beads.assert_exhausted()
