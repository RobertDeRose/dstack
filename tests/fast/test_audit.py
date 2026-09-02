from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dstack import audit as subject


def implementation_task() -> dict[str, Any]:
    return {
        "id": "task",
        "title": "Implement behavior",
        "issue_type": "task",
        "labels": ["dstack:work:implementation", "dstack:commit:feat"],
        "description": """Implement behavior.

## Documentation impact

- End-user: required - Update the usage guide with the new behavior.
- Developer: required - Document the implementation boundary and tests.
- Future-agent: required - Record the invariant and linked decision rationale.
""",
        "acceptance_criteria": "The behavior is observable in tests.",
        "parent": "implementation",
    }


class FakeClient:
    def __init__(self, root: Path):
        self.root = root

    def children(self, parent: str) -> list[dict[str, Any]]:
        return [implementation_task()] if parent == "implementation" else []

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        if kwargs.get("issue_type_filter") == "decision":
            return [{"id": "decision", "issue_type": "decision", "title": "Use native Beads"}]
        return []

    def history(self, issue_id: str) -> list[dict[str, Any]]:
        return [{"id": issue_id, "event": "created"}]


def test_audit_evidence_is_read_only_fact_collection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root_issue = {"id": "root", "issue_type": "molecule", "labels": ["workflow:feature"]}
    steps = {
        "plan": {
            "id": "plan",
            "issue_type": "task",
            "labels": ["dstack:step:plan"],
            "design": "",
            "acceptance_criteria": "",
        },
        "review": {"id": "review", "issue_type": "task"},
        "approval": {"id": "approval", "issue_type": "task"},
        "implementation": {"id": "implementation", "issue_type": "epic"},
        "audit": {"id": "audit", "issue_type": "task"},
    }
    client = FakeClient(tmp_path)
    monkeypatch.setattr(subject, "client_for", lambda root: client)
    monkeypatch.setattr(subject, "feature_identity", lambda client, selector: (root_issue, "feature", "main"))
    monkeypatch.setattr(subject, "feature_steps", lambda client, root_id: steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: False)
    monkeypatch.setattr(subject, "worktree_for_branch", lambda client, branch: None)

    result = subject.collect_audit_evidence(tmp_path, "root")
    assert result["status"] == "ok"
    assert result["git"]["branch_present"] is False
    assert result["plan_validation"]["status"] == "invalid"
    assert result["implementation_tasks"][0]["validation"]["status"] == "ok"
    assert result["decisions"][0]["id"] == "decision"
