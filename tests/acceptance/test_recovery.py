from __future__ import annotations

import json
from pathlib import Path

from .conftest import pour_feature, requires_bd, run_command, run_json


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
