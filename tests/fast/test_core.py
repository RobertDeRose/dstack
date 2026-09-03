from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dstack.core import (
    DstackError,
    commit_records,
    commits_for_bead,
    feature_identity,
    footer_mapping,
    parse_beads_version,
    parse_json,
    truncate_output,
    worktree_for_branch,
)


def test_parse_json_unwraps_beads_envelope() -> None:
    payload = parse_json(json.dumps({"schema_version": 1, "data": [{"id": "x"}]}), context="bd list")
    assert payload == [{"id": "x"}]
    assert parse_json('{"schema_version":1,"data":null}', context="bd list") == []


def test_parse_beads_version_accepts_semver_output() -> None:
    assert parse_beads_version("bd version 1.2.2 (abc)") == (1, 2, 2)
    with pytest.raises(DstackError):
        parse_beads_version("beads unknown")


def test_git_evidence_is_reconstructed_from_reachable_footers(git_repo: Path) -> None:
    (git_repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: add feature", "-m", "Beads: ds-task"],
        cwd=git_repo,
        check=True,
    )
    records = commit_records(git_repo, "HEAD~1..HEAD")
    assert len(records) == 1
    assert records[0]["footer_ids"] == ("ds-task",)
    assert commits_for_bead(git_repo, "HEAD~1..HEAD", "ds-task")[0]["subject"] == "feat: add feature"
    assert footer_mapping(records) == {
        "ds-task": [
            {
                "commit": records[0]["commit"],
                "subject": "feat: add feature",
                "paths": ["feature.txt"],
            }
        ]
    }


class FakeClient:
    def __init__(self, issues: dict[str, dict[str, Any]]):
        self.issues = issues

    def show(self, issue_id: str) -> dict[str, Any]:
        return self.issues[issue_id]


def test_feature_identity_uses_one_feature_label_authority() -> None:
    client = FakeClient(
        {
            "task": {"id": "task", "issue_type": "task", "parent": "impl"},
            "impl": {"id": "impl", "issue_type": "epic", "parent": "root"},
            "root": {
                "id": "root",
                "issue_type": "molecule",
                "labels": ["workflow:feature", "feature:native-control-plane"],
                "metadata": {"dstack.base_branch": "dev"},
            },
        }
    )
    root, slug, base = feature_identity(client, "task")  # type: ignore[arg-type]
    assert root["id"] == "root"
    assert slug == "native-control-plane"
    assert base == "dev"


def test_worktree_inventory_uses_only_native_beads_view(tmp_path: Path) -> None:
    class WorktreeClient:
        root = tmp_path

        def worktrees(self) -> list[dict[str, Any]]:
            return []

    assert worktree_for_branch(WorktreeClient(), "feat/example") is None  # type: ignore[arg-type]


def test_truncated_command_output_preserves_root_cause_and_tail() -> None:
    value = "ROOT-CAUSE\n" + ("x" * 5000) + "\nSUMMARY"
    observed = truncate_output(value, limit=100)
    assert observed.startswith("ROOT-CAUSE")
    assert observed.endswith("SUMMARY")
    assert "output truncated" in observed


def test_beads_client_requires_exact_tested_version(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dstack import core as subject

    client = subject.BeadsClient(git_repo)
    monkeypatch.setattr(client, "version", lambda: "bd version 1.3.0 (future)")

    with pytest.raises(DstackError):
        client.check_version()
