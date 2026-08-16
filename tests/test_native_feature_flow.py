from __future__ import annotations

from pathlib import Path

from conftest import run_json


def test_feature_gate_dynamic_work_and_fan_in(installed_repo: Path) -> None:
    poured = run_json(
        [
            "bd",
            "mol",
            "pour",
            "dstack-feature",
            "--var",
            "feature_title=Provisioning API",
            "--var",
            "feature_slug=provisioning-api",
            "--var",
            "base_branch=dev",
            "--var",
            "design_path=docs/src/features/provisioning-api/design.md",
            "--json",
        ],
        cwd=installed_repo,
    )
    root = poured["root_id"]
    spec = poured["step_ids"]["specification"]
    implementation = poured["step_ids"]["implementation"]
    closeout = poured["step_ids"]["closeout"]
    gate = poured["gate_ids"]["implementation"]

    run_json(
        [
            "bd",
            "update",
            root,
            "--title",
            "Feature: Provisioning API",
            "--add-label",
            "workflow:feature",
            "--add-label",
            "feature:provisioning-api",
        ],
        cwd=installed_repo,
    )
    first = run_json(
        [
            "bd",
            "create",
            "Implement request validation",
            "--type",
            "task",
            "--parent",
            implementation,
            "--no-inherit-labels",
            "--labels",
            "dstack:work:implementation,feature:provisioning-api",
            "--deps",
            spec,
            "--waits-for-gate",
            gate,
            "--description",
            "Validate API input",
            "--acceptance",
            "Invalid input is rejected",
            "--json",
        ],
        cwd=installed_repo,
    )
    second = run_json(
        [
            "bd",
            "create",
            "Add API tests",
            "--type",
            "task",
            "--parent",
            implementation,
            "--no-inherit-labels",
            "--labels",
            "dstack:work:implementation,feature:provisioning-api",
            "--deps",
            f"{spec},{first['id']}",
            "--waits-for-gate",
            gate,
            "--description",
            "Test validation behavior",
            "--acceptance",
            "Focused tests pass",
            "--json",
        ],
        cwd=installed_repo,
    )

    # The stable closeout task is sequenced behind the specification task and
    # separately fans in over dynamic implementation children. It must not be
    # ready before either condition is satisfied.
    assert closeout not in {
        item["id"]
        for item in run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    }

    assert run_json(
        ["bd", "ready", "--mol", implementation, "--exclude-type", "epic", "--json"],
        cwd=installed_repo,
    ) == []

    run_json(["bd", "close", spec, "--json"], cwd=installed_repo)
    assert closeout not in {
        item["id"]
        for item in run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    }
    assert run_json(
        ["bd", "ready", "--mol", implementation, "--exclude-type", "epic", "--json"],
        cwd=installed_repo,
    ) == []

    run_json(["bd", "gate", "resolve", gate, "--json"], cwd=installed_repo)
    ready = run_json(
        ["bd", "ready", "--mol", implementation, "--exclude-type", "epic", "--claim", "--json"],
        cwd=installed_repo,
    )
    assert [item["id"] for item in ready] == [first["id"]]
    run_json(["bd", "close", first["id"], "--json"], cwd=installed_repo)
    assert closeout not in {
        item["id"]
        for item in run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    }

    ready = run_json(
        ["bd", "ready", "--mol", implementation, "--exclude-type", "epic", "--claim", "--json"],
        cwd=installed_repo,
    )
    assert [item["id"] for item in ready] == [second["id"]]
    run_json(["bd", "close", second["id"], "--json"], cwd=installed_repo)

    # children-of(implementation) is the native dynamic fan-in. Once all
    # implementation children close, closeout is eligible even before the
    # container epic is closed; the skill closes that epic before claiming it.
    ready_root = run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    assert closeout in {item["id"] for item in ready_root}

    run_json(["bd", "close", implementation, "--json"], cwd=installed_repo)
    ready_root = run_json(["bd", "ready", "--mol", root, "--json"], cwd=installed_repo)
    assert [item["id"] for item in ready_root] == [closeout]

    run_json(["bd", "close", closeout, "--json"], cwd=installed_repo)
    assert run_json(["bd", "show", root, "--json"], cwd=installed_repo)["status"] == "open"
