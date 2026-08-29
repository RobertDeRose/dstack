from __future__ import annotations

import argparse
import copy
from pathlib import Path

import pytest

from dstack import alignment as dstack_alignment
from dstack.alignment_authority import canonical_authority, require_alignment_authorized
from dstack.commands import DstackError, reopen_authorization_boundary


class BoundaryClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.state = {
            "alignment-1": {"id": "alignment-1", "status": "open", "metadata": {}},
            "analysis-1": {
                "id": "analysis-1",
                "status": "open",
                "description": "Analyze repository",
            },
            "approval-1": {"id": "approval-1", "status": "open"},
            "gate-1": {"id": "gate-1", "status": "open", "type": "gate"},
            "corrections-1": {"id": "corrections-1", "status": "open", "type": "epic"},
            "landing-1": {"id": "landing-1", "status": "open"},
        }
        self.fail_at: str | None = None
        self.calls: list[tuple] = []

    def view(self) -> dict:
        metadata = self.state["alignment-1"].get("metadata", {})
        return {
            "root": self.show("alignment-1"),
            "slug": "repository",
            "scope": "repository",
            "target_branch": "main",
            "human_gate": self.show("gate-1"),
            "pending_alignment_review_sha256": metadata.get("dstack.pending_alignment_review_sha256"),
            "approved_alignment_review_sha256": metadata.get("dstack.approved_alignment_review_sha256"),
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
        if parent == "alignment-1" and label == "dstack:step:alignment-analysis" and claim:
            self._fail("analysis_claim")
            self.state["analysis-1"]["status"] = "in_progress"
            return [self.show("analysis-1")]
        return []

    def update(self, issue_id: str, *args: str) -> dict:
        if "--description" in args:
            self._fail("description")
            self.state[issue_id]["description"] = args[args.index("--description") + 1]
        if "--set-metadata" in args:
            key, value = args[args.index("--set-metadata") + 1].split("=", 1)
            self._fail("pending_metadata" if "pending" in key else "approved_metadata")
            self.state[issue_id].setdefault("metadata", {})[key] = value
        if "--unset-metadata" in args:
            self._fail("pending_clear")
            self.state[issue_id].setdefault("metadata", {}).pop(args[args.index("--unset-metadata") + 1], None)
        if "--claim" in args:
            self._fail("approval_claim")
            self.state[issue_id]["status"] = "in_progress"
        if "--status" in args:
            self.state[issue_id]["status"] = args[args.index("--status") + 1]
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
    monkeypatch.setattr(
        dstack_alignment,
        "human_gate_for_step",
        lambda *args, **kwargs: client.show("gate-1"),
    )
    output: list[dict] = []
    monkeypatch.setattr(dstack_alignment, "emit", output.append)
    return output


def summary_file(tmp_path: Path) -> Path:
    path = tmp_path / "review.md"
    path.write_text("Finding\n\nCorrection rationale.\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("point", ["description", "pending_metadata", "analysis_claim", "analysis_close"])
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
    _, _, digest = canonical_authority(client, client.view(), "Finding\n\nCorrection rationale.")
    assert client.state["alignment-1"]["metadata"]["dstack.pending_alignment_review_sha256"] == digest


@pytest.mark.parametrize(
    "point",
    ["gate_resolve", "approval_claim", "approval_close", "approved_metadata", "pending_clear"],
)
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
    _, _, digest = canonical_authority(client, client.view(), client.state["analysis-1"]["description"])
    client.state["alignment-1"]["metadata"] = {"dstack.pending_alignment_review_sha256": digest}
    if point == "pending_clear":
        client.state["alignment-1"]["metadata"]["dstack.approved_alignment_review_sha256"] = digest
        client.state["approval-1"]["status"] = "closed"
        client.state["gate-1"]["status"] = "closed"
    patch_alignment(monkeypatch, client)
    client.fail_at = point

    with pytest.raises(DstackError, match="injected failure"):
        dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1"))
    dstack_alignment.cmd_alignment_approve(argparse.Namespace(root=tmp_path, selector="alignment-1"))

    metadata = client.state["alignment-1"]["metadata"]
    assert metadata["dstack.approved_alignment_review_sha256"] == digest
    assert "dstack.pending_alignment_review_sha256" not in metadata
    assert require_alignment_authorized(client, client.view())


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
            digest_key="dstack.approved_alignment_review_sha256",
            pending_digest_key="dstack.pending_alignment_review_sha256",
        )


def test_authority_has_no_external_packet_or_git_revision(tmp_path: Path) -> None:
    client = BoundaryClient(tmp_path)
    client.state["analysis-1"].update(status="closed", description="Reviewed current repository semantics.")
    client.state["approval-1"]["status"] = "closed"
    client.state["gate-1"]["status"] = "closed"
    _, _, digest = canonical_authority(client, client.view(), client.state["analysis-1"]["description"])
    client.state["alignment-1"]["metadata"] = {"dstack.approved_alignment_review_sha256": digest}

    authority = require_alignment_authorized(client, client.view())
    assert set(authority) == {"schema", "summary", "corrections"}
    assert "baseline" not in str(authority).casefold()
    assert "plan_file" not in str(authority).casefold()
