from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from dstack import alignment as dstack_alignment
from dstack import alignment_plan as dstack_alignment_plan
from dstack.commands import DstackError, reopen_authorization_boundary
from dstack.alignment_plan import canonical_plan_bytes, plan_digest


def plan() -> dict:
    return {
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
    }


def _view(client: "BoundaryClient") -> dict:
    return {
        "root": {"id": "alignment-1", "status": "open"},
        "target_branch": "main",
        "human_gate": client.show("gate-1"),
        "pending_alignment_plan_sha256": client.show("alignment-1")
        .get("metadata", {})
        .get("dstack.pending_alignment_plan_sha256"),
        "approved_alignment_plan_sha256": client.show("alignment-1")
        .get("metadata", {})
        .get("dstack.approved_alignment_plan_sha256"),
        "steps": {
            key: client.show(issue_id)
            for key, issue_id in {
                "analysis": "analysis-1",
                "approval": "approval-1",
                "corrections": "corrections-1",
                "landing": "landing-1",
            }.items()
        },
    }


class BoundaryClient:
    root: Path

    def __init__(self, root: Path, *, approved: bool = False) -> None:
        self.root = root
        value = json.dumps(plan(), sort_keys=True, separators=(",", ":"))
        digest = plan_digest(plan())
        self.state = {
            "alignment-1": {
                "id": "alignment-1",
                "status": "open",
                "metadata": {"dstack.pending_alignment_plan_sha256": digest}
                if not approved
                else {"dstack.approved_alignment_plan_sha256": digest},
            },
            "analysis-1": {
                "id": "analysis-1",
                "status": "closed" if approved else "open",
                "description": value if approved else "Analyze project alignment",
            },
            "approval-1": {"id": "approval-1", "status": "closed" if approved else "open"},
            "gate-1": {"id": "gate-1", "status": "closed" if approved else "open"},
            "corrections-1": {"id": "corrections-1", "status": "open"},
            "landing-1": {"id": "landing-1", "status": "open"},
        }
        self.fail: str | None = None
        self.calls: list[str] = []

    def _maybe_fail(self, point: str) -> None:
        self.calls.append(point)
        if self.fail == point:
            self.fail = None
            raise DstackError(f"injected failure at {point}")

    def show(self, issue_id: str) -> dict:
        return copy.deepcopy(self.state[issue_id])

    def children(self, parent: str, **kwargs) -> list[dict]:
        assert parent == "corrections-1"
        return []

    def ready_children(self, parent: str, *, label: str, claim: bool = False) -> list[dict]:
        assert parent == "alignment-1"
        assert label == "dstack:step:alignment-analysis"
        if not claim:
            return []
        self._maybe_fail("analysis_claim")
        self.state["analysis-1"]["status"] = "in_progress"
        return [self.show("analysis-1")]

    def update(self, issue_id: str, *args: str) -> dict:
        if "--description" in args:
            self._maybe_fail("description")
            self.state[issue_id]["description"] = args[args.index("--description") + 1]
        elif "--set-metadata" in args:
            key, value = args[args.index("--set-metadata") + 1].split("=", 1)
            point = "pending_metadata" if "pending_alignment" in key else "approved_metadata"
            self._maybe_fail(point)
            self.state[issue_id].setdefault("metadata", {})[key] = value
        elif "--unset-metadata" in args:
            key = args[args.index("--unset-metadata") + 1]
            self._maybe_fail("pending_clear")
            self.state[issue_id].setdefault("metadata", {}).pop(key, None)
        elif "--claim" in args:
            self._maybe_fail("approval_claim")
            self.state[issue_id]["status"] = "in_progress"
        return self.show(issue_id)

    def close(self, issue_id: str, reason: str) -> dict:
        point = "analysis_close" if issue_id == "analysis-1" else "approval_close"
        self._maybe_fail(point)
        self.state[issue_id]["status"] = "closed"
        return self.show(issue_id)

    def resolve_gate(self, gate_id: str, reason: str) -> dict:
        self._maybe_fail("gate_resolve")
        self.state[gate_id]["status"] = "closed"
        return self.show(gate_id)


def patch_alignment(monkeypatch: pytest.MonkeyPatch, client: BoundaryClient) -> None:
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: client)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda c, selector: _view(client))
    monkeypatch.setattr(dstack_alignment, "human_gate_for_step", lambda *args, **kwargs: client.show("gate-1"))
    monkeypatch.setattr(dstack_alignment, "alignment_branch_context", lambda *args: ("audit/x", client.root, "main"))
    monkeypatch.setattr(dstack_alignment, "ensure_clean_worktree", lambda *args: None)
    monkeypatch.setattr(dstack_alignment, "emit", lambda value: None)


def test_legacy_alignment_plan_requires_re_review_before_execution(tmp_path: Path) -> None:
    client = BoundaryClient(tmp_path, approved=True)
    legacy = plan() | {"schema": "dstack.alignment-plan/v1", "baseline_commit": "a" * 40}
    client.state["analysis-1"]["description"] = json.dumps(legacy, sort_keys=True, separators=(",", ":"))

    with pytest.raises(DstackError, match="re-review"):
        dstack_alignment_plan.require_alignment_authorized(client, _view(client))


def test_alignment_authorization_has_no_git_revision_precondition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = BoundaryClient(tmp_path, approved=True)
    patch_alignment(monkeypatch, client)
    monkeypatch.setattr(
        dstack_alignment_plan,
        "target_commit",
        lambda *args: (_ for _ in ()).throw(AssertionError("alignment authorization read a Git revision")),
        raising=False,
    )

    assert dstack_alignment_plan.require_alignment_authorized(client, _view(client)) == plan()


@pytest.mark.parametrize("status", ["claimed", "in_progress", "deferred", "closed", "hooked", "pinned", "unknown"])
def test_shared_reauthorization_rejects_every_non_open_terminal_status(tmp_path: Path, status: str) -> None:
    client = BoundaryClient(tmp_path)
    client.state["landing-1"]["status"] = status
    with pytest.raises(DstackError, match="exactly open and unassigned"):
        reopen_authorization_boundary(
            client,
            root_id="alignment-1",
            planning_id="analysis-1",
            approval_id="approval-1",
            gate_id="gate-1",
            workstream_id="corrections-1",
            terminal_id="landing-1",
            reason="scope",
            digest_key="dstack.approved_alignment_plan_sha256",
            pending_digest_key="dstack.pending_alignment_plan_sha256",
        )
    assert client.calls == []


def test_shared_reauthorization_rejects_assigned_open_terminal(tmp_path: Path) -> None:
    client = BoundaryClient(tmp_path)
    client.state["landing-1"]["assignee"] = "other-agent"
    with pytest.raises(DstackError, match="exactly open and unassigned"):
        reopen_authorization_boundary(
            client,
            root_id="alignment-1",
            planning_id="analysis-1",
            approval_id="approval-1",
            gate_id="gate-1",
            workstream_id="corrections-1",
            terminal_id="landing-1",
            reason="scope",
            digest_key=None,
            pending_digest_key=None,
        )


def test_shared_reauthorization_rechecks_terminal_after_reopen_race(tmp_path: Path) -> None:
    client = BoundaryClient(tmp_path)
    for issue_id in ("analysis-1", "approval-1", "gate-1", "corrections-1"):
        client.state[issue_id]["status"] = "closed"

    def reopen(issue_id: str, reason: str) -> dict:
        client.state[issue_id]["status"] = "open"
        if issue_id == "analysis-1":
            client.state["landing-1"]["status"] = "claimed"
        return client.show(issue_id)

    client.reopen = reopen  # type: ignore[attr-defined]
    with pytest.raises(DstackError, match="exactly open and unassigned"):
        reopen_authorization_boundary(
            client,
            root_id="alignment-1",
            planning_id="analysis-1",
            approval_id="approval-1",
            gate_id="gate-1",
            workstream_id="corrections-1",
            terminal_id="landing-1",
            reason="scope",
            digest_key=None,
            pending_digest_key=None,
        )


@pytest.mark.parametrize("point", ["description", "pending_metadata", "analysis_claim", "analysis_close"])
def test_finish_plan_retries_after_each_transition_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, point: str
) -> None:
    client = BoundaryClient(tmp_path)
    client.state["alignment-1"]["metadata"] = {}
    patch_alignment(monkeypatch, client)
    plan_file = tmp_path / "plan.json"
    plan_file.write_bytes(canonical_plan_bytes(plan()))
    client.fail = point
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", plan_file=plan_file)
    with pytest.raises(DstackError, match="injected failure"):
        dstack_alignment.cmd_alignment_finish_plan(args)
    dstack_alignment.cmd_alignment_finish_plan(args)
    assert client.state["analysis-1"]["status"] == "closed"
    assert client.state["alignment-1"]["metadata"]["dstack.pending_alignment_plan_sha256"] == plan_digest(plan())


@pytest.mark.parametrize(
    "point",
    ["gate_resolve", "approval_claim", "approval_close", "approved_metadata", "pending_clear"],
)
def test_approval_retries_after_each_transition_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, point: str
) -> None:
    client = BoundaryClient(tmp_path, approved=False)
    client.state["analysis-1"]["status"] = "closed"
    client.state["analysis-1"]["description"] = json.dumps(plan(), sort_keys=True, separators=(",", ":"))
    patch_alignment(monkeypatch, client)
    args = argparse.Namespace(root=tmp_path, selector="alignment-1")
    if point == "pending_clear":
        client.state["alignment-1"]["metadata"]["dstack.approved_alignment_plan_sha256"] = plan_digest(plan())
        client.state["approval-1"]["status"] = "closed"
        client.state["gate-1"]["status"] = "closed"
    client.fail = point
    with pytest.raises(DstackError, match="injected failure"):
        dstack_alignment.cmd_alignment_approve(args)
    dstack_alignment.cmd_alignment_approve(args)
    metadata = client.state["alignment-1"]["metadata"]
    assert metadata.get("dstack.approved_alignment_plan_sha256") == plan_digest(plan())
    assert "dstack.pending_alignment_plan_sha256" not in metadata
