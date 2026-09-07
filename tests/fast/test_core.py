from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dstack.core import (
    BeadsClient,
    CommandResult,
    DstackError,
    command_may_mutate,
    commit_records,
    feature_identity,
    footer_mapping,
    parse_beads_version,
    parse_json,
    reject_beads_paths,
    truncate_output,
    worktree_for_branch,
)


def test_timeout_error_does_not_classify_native_command_semantics(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(["bd", "show", "task"], 1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(DstackError, match="inspect native Git/Beads state before retrying"):
        run(["bd", "show", "task"], cwd=git_repo, timeout=1)


def test_show_many_batches_one_native_read_and_preserves_requested_order(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = BeadsClient(git_repo)
    observed: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CommandResult:
        observed.append(command)
        return CommandResult(0, '[{"id":"second"},{"id":"first"}]', "")

    monkeypatch.setattr(client, "_run", fake_run)

    assert [issue["id"] for issue in client.show_many(["first", "second"])] == ["first", "second"]
    assert observed == [["bd", "show", "first", "second", "--json"]]


def test_committed_prime_is_policy_not_generated_beads_state() -> None:
    reject_beads_paths(
        [
            ".beads/PRIME.md",
            ".beads/formulas/dstack-feature.formula.toml",
            "src/app.py",
        ]
    )
    with pytest.raises(DstackError):
        reject_beads_paths([".beads/runtime.json"])


def test_parse_json_unwraps_beads_envelope() -> None:
    payload = parse_json(json.dumps({"schema_version": 1, "data": [{"id": "x"}]}), context="bd list")
    assert payload == [{"id": "x"}]
    assert parse_json('{"schema_version":1,"data":null}', context="bd list") == []


def test_parse_beads_version_accepts_semver_output() -> None:
    assert parse_beads_version("bd version 1.2.2 (abc)") == (1, 2, 2)
    with pytest.raises(DstackError):
        parse_beads_version("beads unknown")


def test_git_evidence_ignores_legacy_beads_footers(git_repo: Path) -> None:
    (git_repo / "legacy.txt").write_text("legacy\n", encoding="utf-8")
    subprocess.run(["git", "add", "legacy.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: add legacy feature", "-m", "Beads: ds-legacy"],
        cwd=git_repo,
        check=True,
    )
    (git_repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.txt"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feat: add feature", "-m", "Task: ds-task"],
        cwd=git_repo,
        check=True,
    )

    records = commit_records(git_repo, "HEAD~2..HEAD", include_paths=True)

    assert [record["footer_kind"] for record in records] == ["Task", None]
    assert records[0]["footer_ids"] == ("ds-task",)
    assert records[1]["footer_ids"] == ()
    assert records[1]["legacy_footer_ids"] == ("ds-legacy",)
    assert "ds-legacy" not in footer_mapping(records)
    assert footer_mapping(records)["ds-task"] == [
        {
            "commit": records[0]["commit"],
            "subject": "feat: add feature",
            "paths": ["feature.txt"],
        }
    ]


def test_diff_stat_is_bounded(git_repo: Path) -> None:
    for index in range(300):
        (git_repo / f"file-{index:03}.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: add files"], cwd=git_repo, check=True)

    from dstack.core import diff_stat

    assert len(diff_stat(git_repo, "HEAD~1", "HEAD")) <= 4000


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


@pytest.mark.parametrize("name", ["tab\tfile", "line\nfile", 'quoted"file', "cr\rfile", "\nleading", "record\x1efile", "raw\udcff"])
def test_evidence_preserves_literal_pathnames(git_repo: Path, name: str) -> None:
    from dstack.core import changed_paths

    (git_repo / name).write_text("content")
    subprocess.run(["git", "add", "--", name], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: add file", "-m", "Task: x"], cwd=git_repo, check=True)
    assert changed_paths(git_repo, "HEAD~1", "HEAD") == [name]
    assert commit_records(git_repo, "HEAD~1..HEAD", include_paths=True)[0]["paths"] == [name]


def test_evidence_handles_empty_body_and_empty_commit(git_repo: Path) -> None:
    subprocess.run(["git", "commit", "--allow-empty", "-qm", "empty"], cwd=git_repo, check=True)
    for include_paths in (False, True):
        result = commit_records(git_repo, "HEAD~1..HEAD", include_paths=include_paths)
        assert len(result) == 1
        assert result[0]["body"] == ""
        assert result[0]["paths"] == []
