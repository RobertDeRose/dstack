from __future__ import annotations

import copy

import pytest

from dstack.alignment_authority import (
    SCHEMA,
    canonical_authority,
    correction_graph,
    normalize_summary,
    require_alignment_authorized,
)
from dstack.core import DstackError


class AuthorityClient:
    def __init__(self, *, approved: bool = False) -> None:
        self.state = {
            "alignment-1": {
                "id": "alignment-1",
                "status": "open",
                "metadata": {},
            },
            "analysis-1": {
                "id": "analysis-1",
                "status": "closed" if approved else "open",
                "description": "Finding\n\nCorrection rationale.",
            },
            "approval-1": {"id": "approval-1", "status": "closed" if approved else "open"},
            "gate-1": {"id": "gate-1", "status": "closed" if approved else "open", "type": "gate"},
            "corrections-1": {"id": "corrections-1", "status": "open", "type": "epic"},
            "correction-b": {
                "id": "correction-b",
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
        if approved:
            view = self.view()
            _, _, digest = canonical_authority(self, view, self.state["analysis-1"]["description"])
            self.state["alignment-1"]["metadata"] = {
                "dstack.approved_alignment_review_sha256": digest,
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
            "human_gate": self.show("gate-1"),
            "steps": {
                "analysis": self.show("analysis-1"),
                "approval": self.show("approval-1"),
                "corrections": self.show("corrections-1"),
                "landing": {"id": "landing-1", "status": "open"},
            },
        }


def test_summary_normalization_is_small_and_strict() -> None:
    assert normalize_summary("  e\u0301\r\nreview  ") == "é\nreview"
    with pytest.raises(DstackError, match="non-empty"):
        normalize_summary(" \n\t ")


def test_authority_is_derived_from_summary_and_native_corrections() -> None:
    client = AuthorityClient()
    view = client.view()

    graph = correction_graph(client, view)
    assert [item["id"] for item in graph] == ["correction-a", "correction-b"]
    assert graph[1]["relationships"][-1] == {"type": "parent-child", "target": "corrections-1"}

    authority, encoded, digest = canonical_authority(client, view, "Review summary")
    assert authority["schema"] == SCHEMA
    assert authority["summary"] == "Review summary"
    assert len(digest) == 64
    assert encoded == encoded.strip()

    client.state["correction-a"]["acceptance_criteria"] = "Changed acceptance"
    _, _, changed = canonical_authority(client, view, "Review summary")
    assert changed != digest


def test_correction_graph_rejects_non_native_or_malformed_work() -> None:
    client = AuthorityClient()
    client.state["correction-a"]["labels"] = []
    with pytest.raises(DstackError, match="outside the native correction workstream"):
        correction_graph(client, client.view())

    client = AuthorityClient()
    client.state["correction-a"]["dependencies"].append({"type": "blocks", "depends_on_id": "approval-1"})
    with pytest.raises(DstackError, match="exactly one approval blocker"):
        correction_graph(client, client.view())


def test_authorization_recomputes_current_native_authority() -> None:
    client = AuthorityClient(approved=True)
    authority = require_alignment_authorized(client, client.view())
    assert authority["summary"].startswith("Finding")

    client.state["correction-a"]["title"] = "Drifted title"
    with pytest.raises(DstackError, match="does not match current Beads state"):
        require_alignment_authorized(client, client.view())
