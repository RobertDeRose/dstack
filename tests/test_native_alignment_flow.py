from __future__ import annotations

from pathlib import Path

from conftest import run_json


def test_alignment_approval_dynamic_work_and_fan_in(installed_repo: Path) -> None:
    poured = run_json(
        [
            "bd",
            "mol",
            "pour",
            "dstack-project-alignment",
            "--var",
            "audit_title=Repository alignment",
            "--var",
            "audit_slug=repository-alignment",
            "--var",
            "target_branch=dev",
            "--var",
            "scope=whole repository",
            "--json",
        ],
        cwd=installed_repo,
    )
    root = poured["root_id"]
    analysis = poured["step_ids"]["analysis"]
    approval = poured["step_ids"]["approval"]
    corrections = poured["step_ids"]["corrections"]
    landing = poured["step_ids"]["landing"]
    gate = poured["gate_ids"]["approval"]

    assert run_json(["bd", "show", corrections, "--json"], cwd=installed_repo)["type"] == "epic"
    correction = run_json(
        [
            "bd",
            "create",
            "Correct stale API documentation",
            "--type",
            "task",
            "--parent",
            corrections,
            "--no-inherit-labels",
            "--labels",
            "dstack:work:alignment,audit:repository-alignment",
            "--deps",
            approval,
            "--description",
            "Align docs and implementation",
            "--acceptance",
            "Public docs match behavior",
            "--json",
        ],
        cwd=installed_repo,
    )

    assert landing not in {
        item["id"]
        for item in run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    }

    run_json(["bd", "close", analysis, "--json"], cwd=installed_repo)
    assert run_json(
        ["bd", "ready", "--mol", corrections, "--exclude-type", "epic", "--json"],
        cwd=installed_repo,
    ) == []

    run_json(["bd", "gate", "resolve", gate, "--json"], cwd=installed_repo)
    run_json(["bd", "update", approval, "--claim", "--json"], cwd=installed_repo)
    run_json(["bd", "close", approval, "--json"], cwd=installed_repo)

    claimed = run_json(
        ["bd", "ready", "--mol", corrections, "--exclude-type", "epic", "--claim", "--json"],
        cwd=installed_repo,
    )
    assert [item["id"] for item in claimed] == [correction["id"]]
    run_json(["bd", "close", correction["id"], "--json"], cwd=installed_repo)

    ready = run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    assert landing in {item["id"] for item in ready}

    run_json(["bd", "close", corrections, "--json"], cwd=installed_repo)
    ready = run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    assert [item["id"] for item in ready] == [landing]
    run_json(["bd", "close", landing, "--json"], cwd=installed_repo)
    assert run_json(["bd", "show", root, "--json"], cwd=installed_repo)["status"] == "open"
