from __future__ import annotations

import argparse
import copy
from pathlib import Path

import pytest

from dstack import alignment as dstack_alignment
from dstack.alignment_authority import require_alignment_authorized
from dstack.commands import DstackError, reopen_authorization_boundary
from dstack.core import ALIGNMENT_STEPS


class BoundaryClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.state: dict[str, dict] = {
            "alignment-1": {"id": "alignment-1", "status": "open"},
            "analysis-1": {
                "id": "analysis-1",
                "status": "open",
                "type": "task",
                "parent": "alignment-1",
                "labels": [ALIGNMENT_STEPS["analysis"]],
                "description": "Analyze repository",
            },
            "approval-1": {
                "id": "approval-1",
                "status": "open",
                "type": "task",
                "parent": "alignment-1",
                "labels": [ALIGNMENT_STEPS["approval"]],
                "dependencies": [{"type": "blocks", "depends_on_id": "gate-1"}],
            },
            "gate-1": {
                "id": "gate-1",
                "status": "open",
                "type": "gate",
                "gate_type": "human",
            },
            "corrections-1": {
                "id": "corrections-1",
                "status": "open",
                "type": "epic",
                "parent": "alignment-1",
                "labels": [ALIGNMENT_STEPS["corrections"]],
            },
            "landing-1": {
                "id": "landing-1",
                "status": "open",
                "type": "task",
                "parent": "alignment-1",
                "labels": [ALIGNMENT_STEPS["landing"]],
            },
        }
        self.fail_at: str | None = None
        self.calls: list[tuple] = []

    def view(self) -> dict:
        return {
            "root": self.show("alignment-1"),
            "slug": "repository",
            "scope": "repository",
            "target_branch": "main",
            "steps": {
                "analysis": self.show("analysis-1"),
                "approval": self.show("approval-1"),
                "corrections": self.show("corrections-1"),
                "landing": self.show("landing-1"),
            },
        }

    def _fail(self, point: str) -> None:
        self.calls.append((point,))
        if self.fail_at == point:
            self.fail_at = None
            raise DstackError(f"injected failure at {point}")

    def show(self, issue_id: str) -> dict:
        return copy.deepcopy(self.state[issue_id])

    def show_optional(self, issue_id: str) -> dict | None:
        value = self.state.get(issue_id)
        return copy.deepcopy(value) if value else None

    def children(self, parent_id: str, **_: object) -> list[dict]:
        if parent_id == "corrections-1":
            return []
        return []

    def ready_children(self, parent: str, *, label: str, claim: bool = False) -> list[dict]:
        if parent == "alignment-1" and label == ALIGNMENT_STEPS["analysis"] and claim:
            self._fail("analysis_claim")
            self.state["analysis-1"]["status"] = "in_progress"
            self.state["analysis-1"]["assignee"] = "current"
            return [self.show("analysis-1")]
        if parent == "alignment-1" and label == ALIGNMENT_STEPS["approval"] and claim:
            self._fail("approval_claim")
            self.state["approval-1"]["status"] = "in_progress"
            self.state["approval-1"]["assignee"] = "current"
            return [self.show("approval-1")]
        return []

    def update(self, issue_id: str, *args: str) -> dict:
        if "--description" in args:
            self._fail("description")
            self.state[issue_id]["description"] = args[args.index("--description") + 1]
        if "--claim" in args:
            self._fail("approval_claim")
            self.state[issue_id]["status"] = "in_progress"
            self.state[issue_id]["assignee"] = "current"
        if "--status" in args:
            self.state[issue_id]["status"] = args[args.index("--status") + 1]
        if "--assignee" in args:
            self.state[issue_id]["assignee"] = args[args.index("--assignee") + 1]
        return self.show(issue_id)

    def close(self, issue_id: str, reason: str) -> dict:
        self._fail("analysis_close" if issue_id == "analysis-1" else "approval_close")
        self.state[issue_id]["status"] = "closed"
        return self.show(issue_id)

    def reopen(self, issue_id: str, reason: str) -> dict:
        self.state[issue_id]["status"] = "open"
        return self.show(issue_id)

    def resolve_gate(self, gate_id: str, reason: str) -> dict:
        self._fail("gate_resolve")
        self.state[gate_id]["status"] = "closed"
        return self.show(gate_id)


def patch_alignment(monkeypatch: pytest.MonkeyPatch, client: BoundaryClient) -> list[dict]:
    monkeypatch.setattr(dstack_alignment, "client_for", lambda root: client)
    monkeypatch.setattr(dstack_alignment, "alignment_context", lambda *_: client.view())
    output: list[dict] = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    return output


def summary_file(tmp_path: Path) -> Path:
    path = tmp_path / "review.md"
    path.write_text("Finding\n\nCorrection rationale.\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("point", ["description", "analysis_claim", "analysis_close"])
def test_finish_review_retries_after_each_transition_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    point: str,
) -> None:
    client = BoundaryClient(tmp_path)
    patch_alignment(monkeypatch, client)
    args = argparse.Namespace(root=tmp_path, selector="alignment-1", summary_file=summary_file(tmp_path))
    client.fail_at = point

    with pytest.raises(DstackError, match="injected failure"):
        dstack_alignment.cmd_alignment_finish_plan(args)
    dstack_alignment.cmd_alignment_finish_plan(args)

    assert client.state["analysis-1"]["status"] == "closed"
    assert client.state["analysis-1"]["description"] == "Finding\n\nCorrection rationale."
    assert client.state["alignment-1"].get("metadata", {}) == {}


@pytest.mark.parametrize("point", ["gate_resolve", "approval_close"])
def test_approval_retries_after_each_transition_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    point: str,
) -> None:
    client = BoundaryClient(tmp_path)
    client.state["analysis-1"].update(
        status="closed",
        description="Finding\n\nCorrection rationale.",
    )
    patch_alignment(monkeypatch, client)
    client.fail_at = point

    with pytest.raises(DstackError, match="injected failure"):
        dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1"))
    dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1"))

    assert client.state["approval-1"]["status"] == "closed"
    assert client.state["gate-1"]["status"] == "closed"
    assert require_alignment_authorized(client, client.view())
    assert client.state["alignment-1"].get("metadata", {}) == {}


@pytest.mark.parametrize("status", ["claimed", "in_progress", "deferred", "closed", "unknown"])
def test_shared_reauthorization_rejects_non_open_terminal(tmp_path: Path, status: str) -> None:
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
            reason="scope changed",
        )


def test_reauthorization_clears_preserved_assignments(tmp_path: Path) -> None:
    client = BoundaryClient(tmp_path)
    for issue_id in ("analysis-1", "approval-1", "gate-1", "corrections-1"):
        client.state[issue_id].update(status="closed", assignee="other")

    reopen_authorization_boundary(
        client,
        root_id="alignment-1",
        planning_id="analysis-1",
        approval_id="approval-1",
        gate_id="gate-1",
        workstream_id="corrections-1",
        terminal_id="landing-1",
        reason="scope changed",
    )

    for issue_id in ("analysis-1", "approval-1", "gate-1", "corrections-1"):
        assert client.state[issue_id]["status"] == "open"
        assert client.state[issue_id].get("assignee") == ""


def test_authority_has_no_external_packet_digest_or_git_revision(tmp_path: Path) -> None:
    client = BoundaryClient(tmp_path)
    client.state["analysis-1"].update(status="closed", description="Reviewed current repository semantics.")
    client.state["approval-1"]["status"] = "closed"
    client.state["gate-1"]["status"] = "closed"

    authority = require_alignment_authorized(client, client.view())
    rendered = str(authority).casefold()
    assert set(authority) == {"summary", "corrections", "human_gate", "steps"}
    assert "sha256" not in rendered
    assert "baseline" not in rendered
    assert "plan_file" not in rendered
