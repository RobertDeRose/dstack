from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dstack import audit as subject
from dstack.core import DstackError


def implementation_task() -> dict[str, Any]:
    return {
        "id": "task",
        "title": "Implement behavior",
        "status": "closed",
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
        "dependencies": [
            {"id": "implementation", "dependency_type": "parent-child"},
            {"id": "approval", "dependency_type": "blocks"},
        ],
        "notes": "No repository change: The unit fixture exercises evidence collection only.",
    }


class FakeClient:
    def __init__(self, root: Path, issues: dict[str, dict[str, Any]]):
        self.root = root
        self.issues = issues

    def show(self, issue_id: str) -> dict[str, Any]:
        return self.issues[issue_id]

    def show_optional(self, issue_id: str) -> dict[str, Any] | None:
        return self.issues.get(issue_id)

    def show_many(self, issue_ids: list[str]) -> list[dict[str, Any]]:
        return [self.issues[issue_id] for issue_id in issue_ids]

    def children(self, parent: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [self.issues["task"]] if parent == "implementation" else []

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        if kwargs.get("issue_type_filter") == "decision":
            return [self.issues["decision"], self.issues["unrelated-decision"]]
        return []

    def history(self, issue_id: str) -> list[dict[str, Any]]:
        return [{"id": issue_id, "event": "created"}]


def fixture_data(tmp_path: Path) -> tuple[FakeClient, dict[str, Any], dict[str, dict[str, Any]]]:
    root_issue = {
        "id": "root",
        "title": "Feature",
        "status": "open",
        "issue_type": "molecule",
        "labels": ["workflow:feature", "feature:feature"],
        "metadata": {"dstack.base_branch": "main"},
    }
    steps = {
        "plan": {
            "id": "plan",
            "title": "Plan",
            "status": "closed",
            "issue_type": "task",
            "labels": ["dstack:step:plan"],
            "design": "",
            "acceptance_criteria": "",
        },
        "review": {"id": "review", "title": "Review", "status": "closed", "issue_type": "task"},
        "approval": {"id": "approval", "title": "Approval", "status": "closed", "issue_type": "task"},
        "implementation": {
            "id": "implementation",
            "title": "Implementation",
            "status": "open",
            "issue_type": "epic",
        },
        "audit": {"id": "audit", "title": "Audit", "status": "open", "issue_type": "task"},
    }
    issues = {
        **{str(issue["id"]): issue for issue in steps.values()},
        "root": root_issue,
        "task": implementation_task(),
        "decision": {
            "id": "decision",
            "title": "Use native Beads",
            "status": "closed",
            "issue_type": "decision",
            "description": "Long rationale that should be hidden by default.",
            "labels": ["decision:feature"],
            "dependencies": [{"id": "root", "dependency_type": "relates-to"}],
        },
        "unrelated-decision": {
            "id": "unrelated-decision",
            "title": "Unrelated",
            "status": "closed",
            "issue_type": "decision",
            "labels": ["decision:feature"],
        },
        "gate": {"id": "gate", "title": "Approval gate", "status": "closed", "issue_type": "gate"},
    }
    issues["audit"] = {
        **issues["audit"],
        "dependencies": [
            {"id": "approval", "dependency_type": "blocks"},
            {"id": "implementation", "dependency_type": "waits-for"},
            {"id": "gate", "dependency_type": "blocks"},
        ],
    }
    steps["audit"] = issues["audit"]
    return FakeClient(tmp_path, issues), root_issue, steps


def install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeClient,
    root_issue: dict[str, Any],
    steps: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(subject, "client_for", lambda root: client)
    monkeypatch.setattr(subject, "feature_identity", lambda client, selector: (root_issue, "feature", "main"))
    monkeypatch.setattr(subject, "feature_steps", lambda client, root_id: steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: False)
    monkeypatch.setattr(subject, "worktree_for_branch", lambda client, branch: None)


def test_bounded_payload_reports_truncation() -> None:
    result = subject.bounded(range(subject.MAX_AUDIT_ITEMS + 1))

    assert result["count"] == subject.MAX_AUDIT_ITEMS + 1
    assert result["truncated"] is True
    assert len(result["items"]) == subject.MAX_AUDIT_ITEMS


def test_audit_evidence_is_bounded_fact_collection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    install_fakes(monkeypatch, client, root_issue, steps)

    result = subject.collect_audit_evidence(tmp_path, "root")

    assert result["status"] == "collected"
    assert result["checks"]["status"] == "invalid"
    assert result["git"]["branch_present"] is False
    assert result["plan_validation"]["status"] == "invalid"
    assert result["validation"]["project"]["status"] == "external"
    assert result["validation"]["feature_docs"]["status"] == "blocked"
    task = result["implementation_tasks"]["items"][0]
    assert task["validation"]["status"] == "ok"
    assert "description" not in task
    assert "details" not in result
    assert "footer_mapping" not in result["git"]
    assert result["checks"]["error_count"] == len(result["checks"]["errors"])
    assert result["decisions"]["items"] == [
        {
            "id": "decision",
            "title": "Use native Beads",
            "status": "closed",
            "issue_type": "decision",
        }
    ]
    assert [gate["id"] for gate in result["gates"]["items"]] == ["gate"]


def test_audit_rejects_close_while_an_implementation_task_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    client.issues["task"]["status"] = "open"
    install_fakes(monkeypatch, client, root_issue, steps)

    result = subject.collect_audit_evidence(tmp_path, "root")

    assert "implementation task task is not closed" in result["checks"]["errors"]


def test_audit_expands_only_explicitly_requested_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    install_fakes(monkeypatch, client, root_issue, steps)

    result = subject.collect_audit_evidence(
        tmp_path,
        "root",
        include_plan=True,
        include_task_ids=["task"],
        include_decision_ids=["decision"],
        history_ids=["task"],
    )

    assert result["details"]["plan"]["id"] == "plan"
    assert "description" in result["details"]["tasks"]["task"]
    assert "description" in result["details"]["decisions"]["decision"]
    assert result["details"]["history"]["task"]["items"][0]["event"] == "created"


def test_audit_rejects_detail_ids_outside_feature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    install_fakes(monkeypatch, client, root_issue, steps)

    with pytest.raises(DstackError):
        subject.collect_audit_evidence(tmp_path, "root", include_task_ids=["other"])


def test_audit_rejects_noncanonical_task_commit_subject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    client.issues["task"]["notes"] = "Implementation:"
    install_fakes(monkeypatch, client, root_issue, steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: True)
    monkeypatch.setattr(subject, "validate_git_revision", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(subject, "ancestry", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        subject,
        "commit_records",
        lambda *args, **kwargs: [
            {
                "commit": "abc123",
                "subject": "feat(old): stale subject",
                "footer_ids": ("task",),
                "paths": [],
            }
        ],
    )
    monkeypatch.setattr(subject, "changed_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(subject, "diff_stat", lambda *args, **kwargs: "")

    result = subject.collect_audit_evidence(tmp_path, "root")

    assert "implementation task task violates dStack policy or graph invariants" in result["checks"]["errors"]
    assert "implementation task task commit message is not canonical" in result["checks"]["errors"]
    assert any(
        "implementation note" in error for error in result["implementation_tasks"]["items"][0]["validation"]["errors"]
    )


def test_audit_reports_missing_implementation_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    client.issues["task"]["notes"] = ""
    install_fakes(monkeypatch, client, root_issue, steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: True)
    monkeypatch.setattr(subject, "validate_git_revision", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(subject, "ancestry", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        subject,
        "commit_records",
        lambda *args, **kwargs: [
            {
                "commit": "abc123",
                "subject": "feat(feature): stale subject",
                "body": "Task: task",
                "footer_ids": ("task",),
                "paths": [],
            }
        ],
    )
    monkeypatch.setattr(subject, "changed_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(subject, "diff_stat", lambda *args, **kwargs: "")

    result = subject.collect_audit_evidence(tmp_path, "root")

    assert any(
        "requires at least one Implementation note" in error
        for error in result["implementation_tasks"]["items"][0]["validation"]["errors"]
    )
    assert "implementation task task commit message is not canonical" in result["checks"]["errors"]


def test_audit_rejects_legacy_and_multiple_task_footers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    client.issues["task"]["notes"] = "Implementation: Deliver the reviewed behavior."
    install_fakes(monkeypatch, client, root_issue, steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: True)
    monkeypatch.setattr(subject, "validate_git_revision", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(subject, "ancestry", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        subject,
        "commit_records",
        lambda *args, **kwargs: [
            {
                "commit": "legacy123",
                "subject": "feat(feature): legacy evidence",
                "body": "Beads: task",
                "footer_ids": (),
                "legacy_footer_ids": ("task",),
                "paths": [],
            },
            {
                "commit": "multiple123",
                "subject": "feat(feature): multiple evidence",
                "body": "Task: task\nTask: other",
                "footer_ids": ("task", "other"),
                "legacy_footer_ids": (),
                "paths": [],
            },
        ],
    )
    monkeypatch.setattr(subject, "changed_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(subject, "diff_stat", lambda *args, **kwargs: "")

    result = subject.collect_audit_evidence(tmp_path, "root")

    assert result["git"]["invalid_footer_commits"]["items"] == ["legacy123", "multiple123"]
    assert "feature commits contain missing, multiple, or unaccepted ownership footers" in result["checks"]["errors"]


def test_audit_rejects_noncanonical_close_commit_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    install_fakes(monkeypatch, client, root_issue, steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: True)
    monkeypatch.setattr(subject, "validate_git_revision", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(subject, "ancestry", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        subject,
        "commit_records",
        lambda *args, **kwargs: [
            {
                "commit": "close123",
                "subject": "docs(feature): document the feature",
                "body": "- Document the accepted feature.\n\nTask: audit",
                "footer_ids": ("audit",),
                "paths": [],
            }
        ],
    )
    monkeypatch.setattr(subject, "changed_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(subject, "diff_stat", lambda *args, **kwargs: "")

    result = subject.collect_audit_evidence(tmp_path, "root")

    assert "close documentation commit message is not canonical" in result["checks"]["errors"]


def test_audit_bounds_diff_stat_and_rejects_beads_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, root_issue, steps = fixture_data(tmp_path)
    install_fakes(monkeypatch, client, root_issue, steps)
    monkeypatch.setattr(subject, "branch_exists", lambda root, branch: True)
    monkeypatch.setattr(subject, "validate_git_revision", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(subject, "ancestry", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        subject,
        "commit_records",
        lambda *args, **kwargs: [
            {
                "commit": "abc123",
                "subject": "chore: unrelated",
                "footer_ids": ("other",),
                "paths": [],
            }
        ],
    )
    monkeypatch.setattr(subject, "changed_paths", lambda *args, **kwargs: [".beads/runtime.json"])
    monkeypatch.setattr(subject, "diff_stat", lambda *args, **kwargs: "x" * 5000)

    result = subject.collect_audit_evidence(tmp_path, "root")
    expanded = subject.collect_audit_evidence(tmp_path, "root", include_commit_paths=True)

    assert len(result["git"]["diff_stat"]) <= 4000
    assert "paths" not in result["git"]["commits"]["items"][0]
    assert expanded["git"]["commits"]["items"][0]["paths"]["items"] == []
    assert result["git"]["invalid_footer_commits"]["items"] == ["abc123"]
    assert any("Beads" in error for error in result["checks"]["errors"])
    assert any("ownership" in error for error in result["checks"]["errors"])
