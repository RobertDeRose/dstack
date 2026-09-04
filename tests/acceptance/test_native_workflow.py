from __future__ import annotations

from pathlib import Path

from .conftest import pour_feature, requires_bd, run_command, run_dstack, run_dstack_root, run_json


PLAN = """### Goals
Use Beads as workflow authority.

### User-facing behavior
Explicit lifecycle commands expose native ready work.

### Implemented design
Use one native molecule and targeted skills.

### Compatibility and constraints
Retain the stable internal final-step identity.

### Validation
Exercise native dependencies, gates, and dynamic children.

### Non-goals
No custom scheduler or lifecycle database.
"""

TASK_DESCRIPTION = """- Implement the reviewed outcome through the public workflow.
"""


@requires_bd
def test_dstack_init_bootstraps_and_validates_beads(uninitialized_repo: Path) -> None:
    initialized = run_dstack_root(uninitialized_repo, "init")

    assert initialized["status"] == "ok"
    assert initialized["initialized"] is True
    assert initialized["validated"] is True
    assert initialized["formula_changed"] is True
    assert initialized["prime_changed"] is True
    assert (uninitialized_repo / ".beads/formulas/dstack-feature.formula.toml").is_file()
    assert (uninitialized_repo / ".beads/PRIME.md").is_file()
    assert not (uninitialized_repo / "AGENTS.md").exists()
    prime = run_command(["bd", "prime", "--mcp"], cwd=uninitialized_repo).stdout
    assert "explicitly activated dStack workflow" in prime
    assert "/close-feature" in prime
    assert "/audit-project" in prime

    repeated = run_dstack_root(uninitialized_repo, "init")
    assert repeated["initialized"] is False
    assert repeated["formula_changed"] is False
    assert repeated["prime_changed"] is False


@requires_bd
def test_native_beads_graph_is_the_only_ready_work_authority(real_repo: Path, tmp_path: Path) -> None:
    root, steps = pour_feature(real_repo)

    plan_claim = run_json(
        real_repo,
        "ready",
        "--parent",
        root,
        "--label",
        "dstack:step:plan",
        "--claim",
    )
    assert plan_claim[0]["id"] == steps["plan"]["id"]

    plan_file = tmp_path / "plan.md"
    plan_file.write_text(PLAN, encoding="utf-8")
    run_json(
        real_repo,
        "update",
        steps["plan"]["id"],
        "--design-file",
        str(plan_file),
        "--acceptance",
        "The native graph exposes each reviewed step in dependency order.",
    )
    assert run_dstack(real_repo, "check", "plan", "--bead", steps["plan"]["id"])["status"] == "ok"
    run_json(real_repo, "close", steps["plan"]["id"], "--reason", "Plan completed")

    review_claim = run_json(
        real_repo,
        "ready",
        "--parent",
        root,
        "--label",
        "dstack:step:review",
        "--claim",
    )
    assert review_claim[0]["id"] == steps["review"]["id"]

    task_file = tmp_path / "task.md"
    task_file.write_text(TASK_DESCRIPTION, encoding="utf-8")
    task = run_json(
        real_repo,
        "create",
        "Implement native workflow",
        "--type",
        "task",
        "--parent",
        steps["implementation"]["id"],
        "--no-inherit-labels",
        "--labels",
        "dstack:work:implementation",
        "--deps",
        f"blocked-by:{steps['approval']['id']}",
        "--description-file",
        str(task_file),
        "--acceptance",
        "The tested behavior uses native Beads readiness.",
    )
    task_id = str(task["id"])
    assert "dstack:step:implementation" not in task.get("labels", [])
    assert "dstack:commit:feat" not in task.get("labels", [])
    assert (
        run_json(
            real_repo,
            "ready",
            "--parent",
            steps["implementation"]["id"],
            "--label",
            "dstack:work:implementation",
        )
        == []
    )
    review = run_dstack(real_repo, "check", "review", "--bead", root)
    assert review["status"] == "ok"
    assert review["tasks"] == [task_id]
    run_json(real_repo, "close", steps["review"]["id"], "--reason", "Reviewed graph created")

    assert (
        run_json(
            real_repo,
            "ready",
            "--parent",
            root,
            "--label",
            "dstack:step:approval",
        )
        == []
    )

    gates = run_json(real_repo, "list", "--parent", root, "--all", "--include-gates", "--limit", "0")
    gate = next(issue for issue in gates if issue.get("await_id") == "approve-native-workflow-plan")
    # Beads 1.2.2 accepts the global --json flag for gate resolution but still
    # emits human-readable output. Treat it as a state-changing command; the
    # following native ready claim verifies that the gate actually closed.
    run_command(
        ["bd", "gate", "resolve", gate["id"], "--reason", "User approved reviewed scope"],
        cwd=real_repo,
    )

    approval_claim = run_json(
        real_repo,
        "ready",
        "--parent",
        root,
        "--label",
        "dstack:step:approval",
        "--claim",
    )
    assert approval_claim[0]["id"] == steps["approval"]["id"]
    run_json(real_repo, "close", steps["approval"]["id"], "--reason", "Scope approved")

    task_claim = run_json(
        real_repo,
        "ready",
        "--parent",
        steps["implementation"]["id"],
        "--label",
        "dstack:work:implementation",
        "--claim",
    )
    assert task_claim[0]["id"] == task_id
    assert (
        run_json(
            real_repo,
            "ready",
            "--parent",
            root,
            "--label",
            "dstack:step:audit",
        )
        == []
    )

    run_json(real_repo, "close", task_id, "--reason", "Implemented")
    audit_ready = run_json(
        real_repo,
        "ready",
        "--parent",
        root,
        "--label",
        "dstack:step:audit",
    )
    assert audit_ready[0]["id"] == steps["audit"]["id"]

    # Close reviews before claiming the now-ready final step. A correction
    # discovered during that review becomes a native implementation child and
    # the existing waits-for fan-in blocks the still-open final step again.
    late_task = run_json(
        real_repo,
        "create",
        "Correct a close review finding",
        "--type",
        "task",
        "--parent",
        steps["implementation"]["id"],
        "--no-inherit-labels",
        "--labels",
        "dstack:work:implementation",
        "--deps",
        f"blocked-by:{steps['approval']['id']}",
        "--description",
        "Correct one finding returned by close review.",
        "--acceptance",
        "The reviewed defect no longer occurs.",
    )
    assert late_task["status"] == "open"
    assert (
        run_json(
            real_repo,
            "ready",
            "--parent",
            root,
            "--label",
            "dstack:step:audit",
        )
        == []
    )
    run_json(real_repo, "close", late_task["id"], "--reason", "Correction completed")
    audit_ready_again = run_json(
        real_repo,
        "ready",
        "--parent",
        root,
        "--label",
        "dstack:step:audit",
    )
    assert audit_ready_again[0]["id"] == steps["audit"]["id"]
