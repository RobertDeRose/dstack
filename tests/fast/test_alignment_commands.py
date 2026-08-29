from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_alignment
import dstack_delivery
from dstack_commands import DstackError, RECORD_SUBJECTS
from dstack_alignment_plan import plan_digest
from dstacklib import CommandResult

from scripted import ScriptedClient, call


@pytest.fixture(autouse=True)
def _ignore_formula_version_stamps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dstack_alignment, "stamp_created_formula_version", lambda *args, **kwargs: 8)
    monkeypatch.setattr(dstack_alignment, "stamp_formula_version", lambda *args, **kwargs: 8)


def alignment_plan_json() -> str:
    return json.dumps(
        {
            "schema": "dstack.alignment-plan/v2",
            "scope": "repository",
            "findings": [],
            "accepted_corrections": [],
            "rejected_corrections": [],
            "validation_expectations": [],
            "documentation_impact": {
                "end_user_operator": [],
                "developer_reviewer": [],
                "future_auditor": [],
            },
            "deferred_findings": [],
            "accepted_risks": [],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def semantic_record(kind: str) -> str:
    lines = ["# Record", ""]
    for subject in RECORD_SUBJECTS[kind]:
        lines.extend([f"## {subject}", "", f"Evidence for {subject}.", ""])
    return "\n".join(lines)


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


def approved_alignment_view() -> dict:
    value = alignment_view()
    value["steps"]["approval"] = {"id": "approval-1", "status": "closed"}
    return value


def patch_command(monkeypatch, beads, current=None):
    current = current or alignment_view()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda client, selector: current)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_branch_context",
        lambda *args: ("audit/alignment", beads.root, "main"),
    )
    monkeypatch.setattr(
        dstack_alignment,
        "canonical_description",
        lambda *args: (
            json.loads(alignment_plan_json()),
            alignment_plan_json(),
            plan_digest(json.loads(alignment_plan_json())),
        ),
    )
    monkeypatch.setattr(dstack_alignment, "verify_correction_graph", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "root_plan_metadata", lambda *args: ("0" * 64, "0" * 64))
    if current["steps"]["approval"].get("status") == "closed":
        monkeypatch.setattr(dstack_alignment, "require_alignment_authorized", lambda *args: {})
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
    monkeypatch.setattr(dstack_alignment, "require_alignment_authorized", lambda *args: {})
    assert dstack_alignment.cmd_alignment_inspect(argparse.Namespace(root=tmp_path, selector="alignment")) == 0
    assert output[0]["steps"]["corrections"]["id"] == "corrections-1"


def test_initialize_rejects_option_like_target_before_beads_mutation(monkeypatch, git_repo: Path) -> None:
    beads = ScriptedClient(git_repo)
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: beads)
    with pytest.raises(DstackError, match="invalid target branch"):
        dstack_alignment.cmd_alignment_initialize(
            argparse.Namespace(
                root=git_repo,
                title="Alignment",
                slug=None,
                target_branch="--help",
                scope="repository",
            )
        )
    beads.assert_exhausted()


def test_initialize_pours_formula_and_records_stable_identity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dstack_alignment, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_alignment, "validate_git_revision", lambda *args, **kwargs: "main")
    monkeypatch.setattr(
        dstack_alignment,
        "ensure_branch_worktree",
        lambda *args: ("audit/repository-alignment", tmp_path / "worktree", False, False),
    )
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
        call("show", "approval-1", result={"id": "approval-1", "status": "open"}),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
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


@pytest.mark.parametrize("title", ["Reconcile documentation", "Document the API"])
def test_add_correction_rejects_documentation_or_reconciliation_work(monkeypatch, tmp_path: Path, title: str) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="sole final reconciliation"):
        dstack_alignment.cmd_alignment_add_correction(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                title=title,
                description="details",
                description_file=None,
                acceptance="observable",
                acceptance_file=None,
                priority=2,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_add_correction_rejects_closed_authorization_without_creation(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call(
            "show",
            "approval-1",
            result={"id": "approval-1", "status": "closed"},
        ),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
    )
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="reauthorization"):
        dstack_alignment.cmd_alignment_add_correction(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                title="Late correction",
                description=None,
                description_file=None,
                acceptance="observable",
                acceptance_file=None,
                priority=2,
                depends_on=[],
            )
        )
    beads.assert_exhausted()


def test_alignment_plan_scaffold_is_removed(monkeypatch, tmp_path: Path) -> None:
    with pytest.raises(DstackError, match="canonical JSON"):
        dstack_alignment.cmd_alignment_scaffold_record(argparse.Namespace(kind="plan", path=tmp_path / "plan.md"))


def test_finish_plan_rejects_invalid_json_before_mutation(monkeypatch, tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="invalid alignment plan fields"):
        dstack_alignment.cmd_alignment_finish_plan(
            argparse.Namespace(root=tmp_path, selector="alignment-1", plan_file=plan)
        )
    beads.assert_exhausted()


def test_finish_plan_uses_native_ready_claim_before_completion(monkeypatch, tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(alignment_plan_json())
    calls = []
    beads = ScriptedClient(tmp_path)
    beads.ready_children = lambda *args, **kwargs: (
        calls.append(("ready_children", *args, kwargs)) or [{"id": "analysis-1", "status": "in_progress"}]
    )

    def update(*args):
        calls.append(("update", *args))
        if "--description" in args:
            return {"id": args[0], "status": "open", "description": alignment_plan_json()}
        if "--claim" in args:
            return {"id": args[0], "status": "in_progress", "description": alignment_plan_json()}
        return {"id": args[0], "status": "open", "description": alignment_plan_json()}

    beads.update = update
    beads.show = lambda issue: {"id": issue, "status": "open", "description": alignment_plan_json()}
    beads.close = lambda *args: calls.append(("close", *args)) or {"id": args[0], "status": "closed"}
    output = patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "root_plan_metadata",
        lambda *args: (plan_digest(json.loads(alignment_plan_json())), None),
    )
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", plan_file=plan)
    assert dstack_alignment.cmd_alignment_finish_plan(args) == 0
    assert calls[0][0] in {"update", "ready_children"}
    assert any(call[0] == "ready_children" for call in calls)
    assert any(call[0] == "close" for call in calls)
    assert output[0]["audit"] == "alignment-1"


def test_finish_plan_rejects_changed_bytes_on_open_retry(monkeypatch, tmp_path: Path) -> None:
    existing = json.loads(alignment_plan_json())
    existing["scope"] = "old scope"
    incoming = tmp_path / "plan.json"
    incoming.write_text(alignment_plan_json())

    class Client:
        root = tmp_path

        def show(self, issue_id):
            return {
                "id": issue_id,
                "status": "open",
                "description": json.dumps(existing, sort_keys=True, separators=(",", ":")),
            }

        def update(self, *args):
            raise AssertionError("changed open-analysis retry attempted mutation")

    client = Client()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: client)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda *args: alignment_view())
    monkeypatch.setattr(
        dstack_alignment,
        "root_plan_metadata",
        lambda *args: (plan_digest(json.loads(alignment_plan_json())), None),
    )
    monkeypatch.setattr(dstack_alignment, "verify_correction_graph", lambda *args: None)
    with pytest.raises(DstackError, match="different canonical plan"):
        dstack_alignment.cmd_alignment_finish_plan(
            argparse.Namespace(root=tmp_path, selector="alignment-1", plan_file=incoming)
        )


def test_approve_rejects_open_analysis_before_gate_mutation(monkeypatch, tmp_path: Path) -> None:
    class Client:
        root = tmp_path

        def show(self, issue_id):
            return {"id": issue_id, "status": "open", "description": alignment_plan_json()}

        def update(self, *args):
            raise AssertionError("open analysis approval attempted metadata mutation")

    client = Client()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: client)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda *args: alignment_view())
    monkeypatch.setattr(
        dstack_alignment,
        "root_plan_metadata",
        lambda *args: (plan_digest(json.loads(alignment_plan_json())), None),
    )
    with pytest.raises(DstackError, match="closed analysis"):
        dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1"))


def test_finish_plan_respects_native_analysis_blocker(monkeypatch, tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(alignment_plan_json())
    beads = ScriptedClient(tmp_path)
    beads.show = lambda issue: {"id": issue, "status": "open", "description": alignment_plan_json()}
    beads.update = lambda *args: {
        "id": args[0],
        "status": "open",
        "description": alignment_plan_json(),
    }
    beads.ready_children = lambda *args, **kwargs: []
    patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "root_plan_metadata",
        lambda *args: (plan_digest(json.loads(alignment_plan_json())), None),
    )
    with pytest.raises(DstackError, match="analysis is not ready"):
        dstack_alignment.cmd_alignment_finish_plan(
            argparse.Namespace(root=tmp_path, selector="alignment-1", plan_file=plan)
        )


def test_approve_resolves_gate_and_authorizes_execution(monkeypatch, tmp_path: Path) -> None:
    calls = []
    state = {
        "alignment-1": {"id": "alignment-1", "status": "open", "metadata": {}},
        "analysis-1": {
            "id": "analysis-1",
            "status": "closed",
            "description": alignment_plan_json(),
        },
        "approval-1": {"id": "approval-1", "status": "open"},
        "gate-1": {"id": "gate-1", "status": "open"},
    }
    beads = ScriptedClient(tmp_path)
    beads.show = lambda issue_id: dict(state[issue_id])
    beads.resolve_gate = lambda issue_id, reason: (
        calls.append(("resolve", issue_id, reason)) or state[issue_id].update(status="closed") or dict(state[issue_id])
    )
    beads.update = lambda issue_id, *args: (
        calls.append(("update", issue_id, *args))
        or state[issue_id].update(status="in_progress")
        or dict(state[issue_id])
    )
    beads.close = lambda issue_id, reason: (
        calls.append(("close", issue_id, reason)) or state[issue_id].update(status="closed") or dict(state[issue_id])
    )
    output = patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "human_gate_for_step",
        lambda *args, **kwargs: dict(state["gate-1"]),
    )
    digest = plan_digest(json.loads(alignment_plan_json()))
    state["alignment-1"]["metadata"] = {"dstack.pending_alignment_plan_sha256": digest}

    def root_plan_metadata(*args):
        metadata = state["alignment-1"]["metadata"]
        return (
            metadata.get("dstack.pending_alignment_plan_sha256"),
            metadata.get("dstack.approved_alignment_plan_sha256"),
        )

    def update_metadata(issue_id, *args):
        calls.append(("update", issue_id, *args))
        if "--set-metadata" in args:
            key, value = args[args.index("--set-metadata") + 1].split("=", 1)
            state[issue_id].setdefault("metadata", {})[key] = value
        elif "--unset-metadata" in args:
            state[issue_id].setdefault("metadata", {}).pop(args[-1], None)
        return dict(state[issue_id])

    beads.update = update_metadata
    monkeypatch.setattr(dstack_alignment, "root_plan_metadata", root_plan_metadata)
    monkeypatch.setattr(dstack_alignment, "require_alignment_authorized", lambda *args: {})
    assert dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1")) == 0
    assert ("resolve", "gate-1", "Corrective plan approved") in calls
    assert ("close", "approval-1", "Corrective execution authorized") in calls
    assert output[0]["audit"] == "alignment-1"
    assert state["gate-1"]["status"] == "closed"
    assert state["approval-1"]["status"] == "closed"


@pytest.mark.parametrize(
    "metadata",
    [
        {"dstack.pending_alignment_plan_sha256": "wrong"},
        {"dstack.approved_alignment_plan_sha256": plan_digest(json.loads(alignment_plan_json()))},
    ],
)
def test_approve_rejects_inconsistent_identity_before_gate_mutation(
    monkeypatch, tmp_path: Path, metadata: dict[str, str]
) -> None:
    calls = []
    state = {
        "analysis-1": {
            "id": "analysis-1",
            "status": "closed",
            "description": alignment_plan_json(),
        },
        "approval-1": {"id": "approval-1", "status": "open"},
        "gate-1": {"id": "gate-1", "status": "open"},
    }

    class Client:
        root = tmp_path

        def show(self, issue_id):
            return dict(state[issue_id])

        def resolve_gate(self, *args):
            calls.append(("resolve", args))

        def close(self, *args):
            calls.append(("close", args))

        def update(self, *args):
            calls.append(("update", args))

    client = Client()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: client)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda *args: alignment_view())
    monkeypatch.setattr(
        dstack_alignment,
        "human_gate_for_step",
        lambda *args, **kwargs: {"id": "gate-1", "status": "open"},
    )
    monkeypatch.setattr(
        dstack_alignment,
        "root_plan_metadata",
        lambda *args: (
            metadata.get("dstack.pending_alignment_plan_sha256"),
            metadata.get("dstack.approved_alignment_plan_sha256"),
        ),
    )
    with pytest.raises(DstackError, match="identity"):
        dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1"))
    assert calls == []


def test_alignment_reauthorize_reopens_native_boundary_before_scope_changes(monkeypatch, tmp_path: Path) -> None:
    state = {
        "alignment-1": {"id": "alignment-1", "status": "open", "metadata": {}},
        "analysis-1": {"id": "analysis-1", "status": "closed"},
        "approval-1": {"id": "approval-1", "status": "closed"},
        "gate-1": {"id": "gate-1", "status": "closed"},
        "corrections-1": {"id": "corrections-1", "status": "closed"},
        "landing-1": {"id": "landing-1", "status": "open"},
    }
    mutations = []
    beads = ScriptedClient(tmp_path)
    beads.show = lambda issue_id: dict(state[issue_id])

    def reopen(issue_id, reason):
        mutations.append((issue_id, reason))
        state[issue_id]["status"] = "open"
        return dict(state[issue_id])

    beads.reopen = reopen
    beads.children = lambda parent: [{"id": "correction-1", "status": "open"}]
    beads.ready_children = lambda *args, **kwargs: []
    output = patch_command(monkeypatch, beads)
    monkeypatch.setattr(
        dstack_alignment,
        "human_gate_for_step",
        lambda *args, **kwargs: dict(state["gate-1"]),
    )

    assert (
        dstack_alignment.cmd_alignment_reauthorize(
            argparse.Namespace(root=tmp_path, selector="alignment-1", reason="Add scope")
        )
        == 0
    )
    assert mutations[0][0] == "approval-1"
    assert all(item["status"] == "open" for item in state.values())
    assert output[0]["status"] == "ok"
    assert output[0]["invalidation"]["plan"]["status"] == "absent"


def test_reauthorize_reports_plan_without_git_baseline(monkeypatch, tmp_path: Path) -> None:
    description = alignment_plan_json()
    state = {
        "analysis-1": {"id": "analysis-1", "status": "closed", "description": description},
        "approval-1": {"id": "approval-1", "status": "closed"},
        "gate-1": {"id": "gate-1", "status": "closed"},
        "corrections-1": {"id": "corrections-1", "status": "open"},
        "landing-1": {"id": "landing-1", "status": "open"},
    }

    class Client:
        root = tmp_path

        def show(self, issue_id):
            return dict(state[issue_id])

        def ready_children(self, *args, **kwargs):
            return []

        def update(self, issue_id, *args):
            if "--description" in args:
                state[issue_id]["description"] = args[args.index("--description") + 1]
            return dict(state[issue_id])

    client = Client()
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: client)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda *args: alignment_view())
    monkeypatch.setattr(dstack_alignment, "root_plan_metadata", lambda *args: ("pending", "approved"))
    monkeypatch.setattr(dstack_alignment, "human_gate_for_step", lambda *args, **kwargs: dict(state["gate-1"]))

    def reopen(*args, **kwargs):
        for issue_id in ("analysis-1", "approval-1", "gate-1", "corrections-1"):
            state[issue_id]["status"] = "open"

    monkeypatch.setattr(dstack_alignment, "reopen_authorization_boundary", reopen)
    output = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    assert (
        dstack_alignment.cmd_alignment_reauthorize(
            argparse.Namespace(root=tmp_path, selector="alignment-1", reason="Refresh audit")
        )
        == 0
    )
    assert output[0]["invalidation"]["plan"]["status"] == "valid"
    assert state["analysis-1"]["description"] == "Analyze repository"
    assert "baseline" not in output[0]["invalidation"]


def test_claim_next_delegates_readiness_and_claim(monkeypatch, tmp_path: Path) -> None:
    ready = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "open",
        "labels": ["dstack:work:correction"],
    }
    correction = {**ready, "status": "claimed"}
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
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", task=None)
    assert dstack_alignment.cmd_alignment_claim_next(args) == 0
    assert output == [{"status": "ok", "correction": correction, "audit": "alignment-1"}]
    beads.assert_exhausted()


def test_claim_next_requires_closed_approval(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="approval milestone"):
        dstack_alignment.cmd_alignment_claim_next(argparse.Namespace(root=tmp_path, selector="alignment-1", task=None))
    beads.assert_exhausted()


def test_finish_task_rejects_dirty_worktree(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(tmp_path)
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)

    def dirty(*args):
        raise DstackError("worktree changes")

    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", dirty)
    with pytest.raises(DstackError, match="worktree changes"):
        dstack_alignment.cmd_alignment_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                task="correction-1",
                reason=None,
                summary_file=None,
                no_repository_change=False,
            )
        )
    beads.assert_exhausted()


def test_finish_task_reuses_client_for_workstream_fan_in(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "open",
        "labels": ["dstack:work:correction"],
    }
    closed_task = {**task, "status": "closed"}
    claimed_task = {**task, "status": "in_progress"}
    client_requests = []
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            result=[task],
        ),
        call(
            "ready_children",
            "corrections-1",
            label="dstack:work:correction",
            claim=True,
            result=[claimed_task],
        ),
        call("close", "correction-1", "Correction completed", result=closed_task),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
        call("children", "corrections-1", result=[closed_task]),
        call(
            "show",
            "corrections-1",
            result={"id": "corrections-1", "status": "open"},
        ),
    )
    current = approved_alignment_view()
    monkeypatch.setattr(
        dstack_alignment,
        "client_for",
        lambda root: client_requests.append(root) or beads,
    )
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda client, selector: current)
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_branch_context",
        lambda *args: ("audit/alignment", tmp_path, "main"),
    )
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
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


def test_finish_task_rejects_documentation_changes_before_landing(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "in_progress",
        "labels": ["dstack:work:correction"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call("update", "correction-1", "--claim", result=task),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(
        dstack_alignment,
        "evidence_for_bead",
        lambda *args: [{"commit": "abc", "subject": "docs", "paths": ["docs/src/index.md"]}],
    )
    with pytest.raises(DstackError, match="final reconciliation"):
        dstack_alignment.cmd_alignment_finish_task(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                task="correction-1",
                reason=None,
                summary_file=None,
                no_repository_change=False,
            )
        )
    beads.assert_exhausted()


def test_finish_task_requires_reachable_git_evidence(monkeypatch, tmp_path: Path) -> None:
    task = {
        "id": "correction-1",
        "parent": "corrections-1",
        "status": "in_progress",
        "labels": ["dstack:work:correction"],
    }
    beads = ScriptedClient(
        tmp_path,
        call("show", "correction-1", result=task),
        call("update", "correction-1", "--claim", result=task),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
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


def test_finish_workstream_closes_after_native_children_are_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "close",
            "corrections-1",
            "All corrections completed",
            result={"id": "corrections-1", "status": "closed"},
        ),
        call("show", "corrections-1", result={"id": "corrections-1", "status": "closed"}),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    assert (
        dstack_alignment.cmd_alignment_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
        )
        == 0
    )
    assert output[0]["open_items"] == []
    beads.assert_exhausted()


def test_finish_workstream_requires_authorization(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
    )
    patch_command(monkeypatch, beads)
    with pytest.raises(DstackError, match="approval milestone"):
        dstack_alignment.cmd_alignment_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
        )
    beads.assert_exhausted()


def test_claim_landing_delegates_readiness_to_beads(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "ready_children",
            "alignment-1",
            label="dstack:step:alignment-landing",
            claim=True,
            result=[],
        ),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    args = argparse.Namespace(root=tmp_path, selector="alignment-1")
    with pytest.raises(DstackError, match="not ready according to Beads"):
        dstack_alignment.cmd_alignment_claim_landing(args)
    beads.assert_exhausted()


def test_claim_landing_refuses_open_native_child_before_ready_claim(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call(
            "children",
            "corrections-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())

    with pytest.raises(DstackError, match="native-child"):
        dstack_alignment.cmd_alignment_claim_landing(argparse.Namespace(root=tmp_path, selector="alignment-1"))
    beads.assert_exhausted()


def test_claim_landing_uses_native_atomic_ready_claim(monkeypatch, tmp_path: Path) -> None:
    claimed = {"id": "landing-1", "status": "in_progress"}
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "ready_children",
            "alignment-1",
            label="dstack:step:alignment-landing",
            claim=True,
            result=[claimed],
        ),
        call("children", "corrections-1", result=[]),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    args = argparse.Namespace(root=tmp_path, selector="alignment-1")
    assert dstack_alignment.cmd_alignment_claim_landing(args) == 0
    assert output[0]["landing"] == claimed
    beads.assert_exhausted()


def test_finish_landing_closes_once(monkeypatch, tmp_path: Path) -> None:
    summary = tmp_path / "reconciliation.md"
    summary.write_text(semantic_record("alignment-reconciliation"))
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
        call("children", "corrections-1", result=[]),
        call(
            "ready_children",
            "alignment-1",
            label="dstack:step:alignment-landing",
            claim=True,
            result=[{"id": "landing-1", "status": "in_progress"}],
        ),
        call("children", "corrections-1", result=[]),
        call(
            "add_comment",
            "landing-1",
            semantic_record("alignment-reconciliation").strip(),
        ),
        call(
            "close",
            "landing-1",
            "Alignment landing completed",
            result={"id": "landing-1", "status": "closed"},
        ),
        call(
            "show",
            "alignment-1",
            result={
                "id": "alignment-1",
                "status": "closed",
                "close_reason": "all steps complete",
            },
        ),
        call(
            "reopen",
            "alignment-1",
            "Await delivery",
            result={"id": "alignment-1", "status": "open"},
        ),
    )
    output = patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "validate_docs", lambda *args: {"status": "ok"})
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_delivery_context",
        lambda client, selector: {**alignment_view(), "corrections": []},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_evidence_audit",
        lambda client, view: {
            "status": "ok",
            "missing": [],
            "unexpected_footer_ids": [],
        },
    )
    monkeypatch.setattr(
        dstack_delivery,
        "docs_check",
        lambda *args: {"status": "ok", "violations": []},
    )
    args = argparse.Namespace(
        root=tmp_path,
        selector="alignment-1",
        reason="Alignment landing completed",
        summary_file=summary,
    )
    assert dstack_alignment.cmd_alignment_finish_landing(args) == 0
    assert output[0]["audit"] == "alignment-1"
    assert output[0]["landing"]["status"] == "closed"
    beads.assert_exhausted()


def test_finish_alignment_workstream_counts_unlabeled_native_children(monkeypatch, tmp_path: Path) -> None:
    beads = ScriptedClient(
        tmp_path,
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
        call(
            "children",
            "corrections-1",
            result=[{"id": "native-child", "status": "open", "labels": []}],
        ),
        call("show", "corrections-1", result={"id": "corrections-1", "status": "open"}),
    )
    output = patch_command(monkeypatch, beads)
    assert (
        dstack_alignment.cmd_alignment_finish_workstream(
            argparse.Namespace(root=tmp_path, selector="alignment-1", quiet=False)
        )
        == 0
    )
    assert output[0]["open_items"] == ["native-child"]
    beads.assert_exhausted()


def test_initialize_rolls_back_poured_state_when_worktree_registration_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dstack_alignment, "validate_git_branch", lambda *args, **kwargs: "main")
    monkeypatch.setattr(dstack_alignment, "validate_git_revision", lambda *args, **kwargs: "main")
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
    monkeypatch.setattr(
        dstack_alignment,
        "alignment_context",
        lambda *args: (_ for _ in ()).throw(DstackError("alignment selector resolved to 0 roots")),
    )
    monkeypatch.setattr(
        dstack_alignment,
        "ensure_branch_worktree",
        lambda *args: (_ for _ in ()).throw(DstackError("failed to register worktree")),
    )
    commands = []
    monkeypatch.setattr(
        dstack_alignment,
        "run",
        lambda command, **kwargs: commands.append(tuple(command)) or CommandResult(0, "", ""),
    )

    with pytest.raises(DstackError, match="failed to register worktree"):
        dstack_alignment.cmd_alignment_initialize(
            argparse.Namespace(
                root=tmp_path,
                title="Repository Alignment",
                slug=None,
                target_branch="main",
                scope="whole repository",
            )
        )

    assert commands == [("bd", "delete", "alignment-1", "--cascade", "--force")]
    beads.assert_exhausted()


def test_finish_landing_refuses_failed_evidence_audit_before_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = tmp_path / "reconciliation.md"
    summary.write_text(semantic_record("alignment-reconciliation"))
    beads = ScriptedClient(
        tmp_path,
        call("show", "landing-1", result={"id": "landing-1", "status": "open"}),
    )
    patch_command(monkeypatch, beads, approved_alignment_view())
    monkeypatch.setattr(dstack_alignment, "worktree_for_branch", lambda *args: tmp_path)
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "validate_docs", lambda *args: {"status": "ok"})
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_delivery_context",
        lambda client, selector: {**alignment_view(), "corrections": []},
    )
    monkeypatch.setattr(
        dstack_delivery,
        "alignment_evidence_audit",
        lambda client, view: {
            "status": "issues",
            "missing": ["correction-1"],
            "unexpected_footer_ids": [],
        },
    )

    with pytest.raises(DstackError, match="evidence audit failed"):
        dstack_alignment.cmd_alignment_finish_landing(
            argparse.Namespace(
                root=tmp_path,
                selector="alignment-1",
                reason="Alignment landing completed",
                summary_file=summary,
            )
        )
    beads.assert_exhausted()
