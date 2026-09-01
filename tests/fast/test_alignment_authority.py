from __future__ import annotations

import copy

import pytest

from dstack.alignment_authority import correction_graph, normalize_summary, require_alignment_authorized
from dstack.core import ALIGNMENT_STEPS, DstackError


class AuthorityClient:
    def __init__(self, *, approved: bool = False, root_status: str = "open") -> None:
        boundary_status = "closed" if approved else "open"
        self.state: dict[str, dict] = {
            "alignment-1": {"id": "alignment-1", "status": root_status},
            "analysis-1": {
                "id": "analysis-1",
                "status": boundary_status,
                "type": "task",
                "parent": "alignment-1",
                "labels": [ALIGNMENT_STEPS["analysis"]],
                "description": "Finding\n\nCorrection rationale.",
            },
            "approval-1": {
                "id": "approval-1",
                "status": boundary_status,
                "type": "task",
                "parent": "alignment-1",
                "labels": [ALIGNMENT_STEPS["approval"]],
                "dependencies": [{"type": "blocks", "depends_on_id": "gate-1"}],
            },
            "gate-1": {
                "id": "gate-1",
                "status": boundary_status,
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
            "correction-b": {
                "id": "correction-b",
                "status": "open",
                "title": "Second correction",
                "description": "Second description",
                "acceptance_criteria": "Second acceptance",
                "priority": 2,
                "type": "task",
                "parent": "corrections-1",
                "labels": ["dstack:work:correction"],
                "dependencies": [
                    {"type": "parent-child", "depends_on_id": "corrections-1"},
                    {"type": "blocks", "depends_on_id": "approval-1"},
                    {"type": "blocks", "depends_on_id": "correction-a"},
                ],
            },
            "correction-a": {
                "id": "correction-a",
                "status": "open",
                "title": "First correction",
                "description": "First description",
                "acceptance_criteria": "First acceptance",
                "priority": 1,
                "type": "task",
                "parent": "corrections-1",
                "labels": ["dstack:work:correction"],
                "dependencies": [
                    {"type": "parent-child", "depends_on_id": "corrections-1"},
                    {"type": "blocks", "depends_on_id": "approval-1"},
                ],
            },
        }

    def show(self, issue_id: str) -> dict:
        return copy.deepcopy(self.state[issue_id])

    def show_optional(self, issue_id: str) -> dict | None:
        value = self.state.get(issue_id)
        return copy.deepcopy(value) if value is not None else None

    def children(self, parent_id: str, **_: object) -> list[dict]:
        assert parent_id == "corrections-1"
        return [self.show("correction-b"), self.show("correction-a")]

    def view(self) -> dict:
        return {
            "root": self.show("alignment-1"),
            "steps": {
                "analysis": self.show("analysis-1"),
                "approval": self.show("approval-1"),
                "corrections": self.show("corrections-1"),
                "landing": self.show("landing-1"),
            },
        }


def test_summary_normalization_is_small_and_strict() -> None:
    assert normalize_summary("  e\u0301\r\nreview  ") == "é\nreview"
    with pytest.raises(DstackError, match="non-empty"):
        normalize_summary(" \n\t ")


def test_correction_graph_is_derived_from_live_native_records() -> None:
    client = AuthorityClient()
    graph = correction_graph(client, client.view())

    assert [item["id"] for item in graph] == ["correction-a", "correction-b"]
    assert graph[1]["relationships"][-1] == {"type": "parent-child", "target": "corrections-1"}

    client.state["correction-a"]["acceptance_criteria"] = "Changed acceptance"
    changed = correction_graph(client, client.view())
    assert changed[0]["acceptance"] == "Changed acceptance"


def test_correction_graph_rejects_non_native_or_malformed_work() -> None:
    client = AuthorityClient()
    client.state["correction-a"]["labels"] = []
    with pytest.raises(DstackError, match="outside the native correction workstream"):
        correction_graph(client, client.view())

    client = AuthorityClient()
    client.state["correction-a"]["dependencies"].append(
        {"type": "blocks", "depends_on_id": "approval-1"}
    )
    with pytest.raises(DstackError, match="exactly one approval blocker"):
        correction_graph(client, client.view())


def test_authorization_uses_live_beads_without_a_digest_protocol() -> None:
    client = AuthorityClient(approved=True)
    authority = require_alignment_authorized(client, client.view())

    assert authority["summary"].startswith("Finding")
    assert [item["id"] for item in authority["corrections"]] == ["correction-a", "correction-b"]
    assert set(authority) == {"summary", "corrections", "human_gate", "steps"}

    client.state["correction-a"]["description"] = ""
    with pytest.raises(DstackError, match="description must be a non-empty string"):
        require_alignment_authorized(client, client.view())


def test_closed_root_is_inspectable_but_not_executable() -> None:
    client = AuthorityClient(approved=True, root_status="closed")

    with pytest.raises(DstackError, match="inspect-only"):
        require_alignment_authorized(client, client.view())

    authority = require_alignment_authorized(client, client.view(), allow_closed_root=True)
    assert authority["summary"].startswith("Finding")
