from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from dstack.audit import bounded, issue_view
from dstack.core import run
from dstack.git_ops import canonical_task_message

if TYPE_CHECKING:
    from conftest import FeatureRepository


def test_audit_collects_compact_facts_through_public_cli(public_feature: FeatureRepository) -> None:
    result = public_feature.invoke("audit", "--bead", "root")
    assert result["status"] == "collected"
    assert result["checks"]["status"] == "ok"
    assert result["plan_validation"]["status"] == "ok"
    assert result["validation"]["project"]["status"] == "external"
    assert "details" not in result
    assert "description" not in result["implementation_tasks"]["items"][0]
    assert [item["id"] for item in result["decisions"]["items"]] == ["decision"]
    assert [item["id"] for item in result["gates"]["items"]] == ["gate"]


def test_audit_reports_missing_branch_and_bad_plan(public_feature: FeatureRepository) -> None:
    run(["git", "switch", "--detach"], cwd=public_feature.worktree)
    run(["git", "branch", "-D", "feat/example"], cwd=public_feature.repo)
    public_feature.data["worktrees"] = []
    public_feature.data["issues"]["plan"]["design"] = ""
    result = public_feature.invoke("audit", "--bead", "root", expected=4)
    assert result["git"]["branch_present"] is False
    assert result["plan_validation"]["status"] == "invalid"
    assert result["validation"]["feature_docs"]["status"] == "blocked"


def test_audit_expands_selected_intent_comments_and_history(public_feature: FeatureRepository) -> None:
    result = public_feature.invoke("audit", "root", "--include-plan", "--include-task", "task",
                                  "--include-decision", "decision", "--history-for", "task")
    details = result["details"]
    assert details["plan"]["id"] == "plan"
    assert details["tasks"]["task"]["comments"][0]["text"].startswith("Review correction:")
    assert details["decisions"]["decision"]["description"] == "Accepted durable rationale."
    assert details["history"]["task"]["items"][0]["event"] == "created"
    with public_feature.calls.open(encoding="utf-8") as log:
        comment_reads = [json.loads(line) for line in log if "--include-comments" in line]
    assert {call[1] for call in comment_reads} == {"task", "decision"}


def test_audit_rejects_foreign_detail_selector(public_feature: FeatureRepository) -> None:
    result = public_feature.invoke("audit", "root", "--include-task", "unrelated", expected=2)
    assert "not an implementation child" in result["error"]


@pytest.mark.parametrize("field,value", [("status", "open"), ("notes", ""), ("design", "")])
def test_audit_rejects_incomplete_native_task(public_feature: FeatureRepository, field: str, value: str) -> None:
    public_feature.data["issues"]["task"][field] = value
    result = public_feature.invoke("audit", "--bead", "root", expected=4)
    assert result["checks"]["error_count"] > 0


@pytest.mark.parametrize(
    "message",
    [
        "feat(old): Stale\n\nTask: task\n",
        "feat(example): implement behavior\n\nBeads: task\n",
        "feat(example): implement behavior\n\nTask: task\nTask: other\n",
    ],
)
def test_audit_checks_real_noncanonical_and_ambiguous_commits(public_feature: FeatureRepository, message: str) -> None:
    public_feature.data["issues"]["task"]["notes"] = "Implementation: Implement behavior."
    public_feature.commit(message)
    result = public_feature.invoke("audit", "--bead", "root", expected=4)
    assert any("canonical" in error or "ownership" in error for error in result["checks"]["errors"])


def test_audit_rejects_noncanonical_close_commit(public_feature: FeatureRepository) -> None:
    public_feature.commit("docs(example): Incorrect title\n\nTask: audit\n")
    result = public_feature.invoke("audit", "--bead", "root", expected=4)
    assert "close documentation commit message is not canonical" in result["checks"]["errors"]


def test_audit_checks_raw_git_paths_and_bounds_diff_stat(public_feature: FeatureRepository) -> None:
    public_feature.commit("chore: Wrong owner\n\nTask: other\n", path=".beads\ttab/config", content="unsafe")
    # .beads-tab is legal, while a control character inside .beads is still forbidden.
    target = public_feature.worktree / ".beads/runtime\tdata"
    target.parent.mkdir()
    target.write_text("runtime\n")
    run(["git", "add", "-f", "--", ".beads/runtime\tdata"], cwd=public_feature.worktree)
    run(["git", "commit", "-m", "chore: Expose runtime\n\nTask: other"], cwd=public_feature.worktree)
    result = public_feature.invoke("audit", "root", "--include-commit-paths", expected=4)
    assert ".beads/runtime\tdata" in result["git"]["changed_paths"]["items"]
    assert any("Beads" in error for error in result["checks"]["errors"])
    assert len(result["git"]["diff_stat"]) <= 4000


def test_feature_size_limits_bound_output_not_validity(public_feature: FeatureRepository) -> None:
    issues = public_feature.data["issues"]
    prototype = issues.pop("task")
    tree = run(["git", "rev-parse", "HEAD^{tree}"], cwd=public_feature.worktree).stdout.strip()
    parent = run(["git", "rev-parse", "HEAD"], cwd=public_feature.worktree).stdout.strip()
    for index in range(100):
        task = {**prototype, "id": f"task-{index:03d}", "notes": f"Implementation: Implement accepted outcome {index}."}
        issues[task["id"]] = task
        parent = run(["git", "commit-tree", tree, "-p", parent], cwd=public_feature.worktree,
                     input_text=canonical_task_message(task, "example")).stdout.strip()
    parent = run(["git", "commit-tree", tree, "-p", parent], cwd=public_feature.worktree,
                 input_text="docs(example): Example\n\nTask: audit\n").stdout.strip()
    run(["git", "reset", "--hard", parent], cwd=public_feature.worktree)
    first = public_feature.invoke("audit", "--bead", "root")
    second = public_feature.invoke("audit", "--bead", "root", "--offset", "100")
    assert first["git"]["commit_count"] == 101
    assert len(first["git"]["commits"]["items"]) == 100
    assert len(second["git"]["commits"]["items"]) == 1
    assert first["checks"]["status"] == second["checks"]["status"] == "ok"
    assert first["implementation_tasks"]["count"] == 100


def test_issue_details_distinguish_omitted_and_empty_comments() -> None:
    assert issue_view({"id": "x", "comments": []})["comments"] == []
    result = issue_view({"id": "x", "comment_count": 2, "comments_omitted": True})
    assert result["comments_omitted"] is True and "comments" not in result


def test_summary_pages_cover_all_rows() -> None:
    pages = [bounded(range(201), offset=offset) for offset in (0, 100, 200)]
    assert [row for page in pages for row in page["items"]] == list(range(201))
    assert pages[0]["next_offset"] == 100
    assert "next_offset" not in pages[-1]
