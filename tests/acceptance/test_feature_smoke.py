from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import run_ctl, run_json


def dependency_ids(issue: dict, relation: str = "blocks") -> set[str]:
    return {
        str(record.get("depends_on_id") or record.get("id"))
        for record in issue.get("dependencies", [])
        if (record.get("type") or record.get("dependency_type") or "blocks") == relation
    }


def resolved_id(repo: Path, selector: str) -> str:
    return run_ctl(repo, "feature", "resolve", selector)["root"]["id"]


def test_feature_smoke_runs_shipped_lifecycle(acceptance_repo: Path) -> None:
    created = run_ctl(
        acceptance_repo, "feature", "initialize", "Acceptance smoke", "--base-branch", "main"
    )
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    run_ctl(acceptance_repo, "feature", "claim-spec", root_id)
    scaffolded = run_ctl(acceptance_repo, "feature", "scaffold-design", root_id)
    assert scaffolded["created"] is True
    design = worktree / created["design_path"]
    design.write_text("# Acceptance smoke revised\n\nA minimal shipped feature.\n")

    worktrees = run_command(["git", "worktree", "list", "--porcelain"], cwd=acceptance_repo).stdout
    for selector in (planned["id"], "acceptance-smoke", revised_title):
        repeated = run_ctl(acceptance_repo, "feature", "initialize", selector, "--base-branch", "main")
        assert repeated["created"] is False
        assert repeated["root"]["id"] == root_id
        assert Path(repeated["worktree"]) == worktree
    assert run_command(
        ["git", "worktree", "list", "--porcelain"], cwd=acceptance_repo
    ).stdout == worktrees
    assert run_ctl(
        acceptance_repo, "feature", "scaffold-design", root_id
    )["created"] is False
    assert design.read_text() == "# Acceptance smoke revised\n\nA minimal shipped feature.\n"
    current_roots = [
        issue
        for issue in items(run_json(acceptance_repo, "list", "--all"))
        if "workflow:feature" in issue.get("labels", [])
    ]
    assert [issue["id"] for issue in current_roots] == [root_id]
    current_graph = [
        items(run_json(acceptance_repo, "show", root_id))[0],
        *items(
            run_json(
                acceptance_repo,
                "list",
                "--all",
                "--parent",
                root_id,
                "--limit",
                "0",
            )
        ),
    ]
    assert any(blocker_b["id"] in dependency_ids(issue) for issue in current_graph)
    assert all(blocker_a["id"] not in dependency_ids(issue) for issue in current_graph)
    source = items(run_json(acceptance_repo, "show", planned["id"]))[0]
    assert source["status"] == "closed"
    assert root_id in dependency_ids(source, "supersedes")
    materialized = items(run_json(acceptance_repo, "show", root_id))[0]
    assert materialized["description"] == revised_body
    assert materialized["acceptance_criteria"] == revised_acceptance
    assert materialized["priority"] == 3

    run_ctl(acceptance_repo, "feature", "approve-spec", root_id)
    task = run_ctl(
        acceptance_repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Ship smoke behavior",
        "--acceptance",
        "The smoke behavior is delivered with Git evidence.",
    )["task"]
    change = worktree / "smoke.py"
    change.write_text("SMOKE = True\n")
    subprocess.run(
        ["git", "add", "smoke.py", created["design_path"]],
        cwd=worktree,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", f"feat: ship smoke behavior\n\nBeads: {task['id']}"],
        cwd=worktree,
        check=True,
    )
    run_ctl(acceptance_repo, "feature", "finish-task", root_id, "--task", task["id"])
    refused = run_ctl(
        acceptance_repo,
        "feature",
        "finish-closeout",
        root_id,
        check=False,
    )
    assert refused.returncode != 0
    assert "implementation workstream is not closed" in refused.stderr
    run_command(
        ["bd", "close", blocker_b["id"], "--reason", "External dependency shipped"],
        cwd=acceptance_repo,
    )
    run_ctl(acceptance_repo, "feature", "finish-workstream", root_id)
    run_ctl(acceptance_repo, "feature", "claim-closeout", root_id)
    run_ctl(acceptance_repo, "feature", "finish-closeout", root_id)
    ready_root = run_json(acceptance_repo, "show", root_id)
    assert ready_root[0]["status"] == "open"

    delivered = run_ctl(acceptance_repo, "delivery", "merge", root_id)
    assert delivered["root"] == root_id
    assert delivered["previous_target_head"] != delivered["delivered_head"]
    closed = run_json(acceptance_repo, "show", root_id)
    assert closed[0]["status"] == "closed"
