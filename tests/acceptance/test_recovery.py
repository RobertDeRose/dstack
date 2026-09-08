from __future__ import annotations

import json
from pathlib import Path

from .conftest import pour_feature, requires_bd, run_command, run_dstack, run_json


@requires_bd
def test_interrupted_plan_is_discoverable_without_claiming_new_work(real_repo: Path) -> None:
    root, steps = pour_feature(real_repo, slug="resume-plan")
    claimed = run_json(real_repo, "ready", "--parent", root, "--label", "dstack:step:plan", "--claim")
    assert claimed[0]["id"] == steps["plan"]["id"]
    # Each command is a fresh process: no retained conversational or CLI state is available.
    assert run_json(real_repo, "ready", "--parent", root, "--label", "dstack:step:plan") == []
    resumed = run_json(real_repo, "list", "--parent", root, "--status", "in_progress", "--limit", "0")
    assert [issue["id"] for issue in resumed] == [steps["plan"]["id"]]
    current = run_json(real_repo, "mol", "current", root)
    assert str(steps["plan"]["id"]) in json.dumps(current)


@requires_bd
def test_review_comment_survives_reopen_and_explicit_json_read(real_repo: Path) -> None:
    root, steps = pour_feature(real_repo, slug="resume-comments")
    plan = str(steps["plan"]["id"])
    run_json(real_repo, "ready", "--parent", root, "--label", "dstack:step:plan", "--claim")
    run_json(real_repo, "close", plan, "--reason", "Initial plan recorded")
    finding = "Preserve the accepted compatibility constraint during correction."
    run_command(["bd", "comments", "add", plan, finding], cwd=real_repo)
    run_json(real_repo, "reopen", plan, "--reason", "Review correction")
    plain = run_json(real_repo, "show", plan)
    detailed = run_json(real_repo, "show", plan, "--include-comments")
    assert finding not in json.dumps(plain)
    assert finding in json.dumps(detailed)


@requires_bd
def test_worktree_entry_locates_native_detached_rebase(real_repo: Path) -> None:
    root, _ = pour_feature(real_repo, slug="resume-rebase")
    worktree = Path(run_dstack(real_repo, "worktree", "--bead", root)["worktree"])
    for directory, content in ((worktree, "feature\n"), (real_repo, "base\n")):
        (directory / "README.md").write_text(content, encoding="utf-8")
        run_command(["git", "add", "README.md"], cwd=directory)
        run_command(["git", "commit", "-m", "Change readme"], cwd=directory)
    conflict = run_command(["git", "rebase", "main"], cwd=worktree, check=False)
    assert conflict.returncode != 0
    located = run_dstack(real_repo, "worktree", "--bead", root)
    assert located["status"] == "recovery_required"
    assert located["git_operation"] == "rebase-merge"
    assert Path(located["worktree"]) == worktree
    assert not located["created_worktree"] and not located["created_branch"]
    (worktree / "README.md").write_text("base and feature\n", encoding="utf-8")
    run_command(["git", "add", "README.md"], cwd=worktree)
    run_command(["git", "rebase", "--continue"], cwd=worktree, env={"GIT_EDITOR": "true"})
    assert run_dstack(real_repo, "worktree", "--bead", root)["status"] == "ok"
    assert (worktree / "README.md").read_text(encoding="utf-8") == "base and feature\n"
