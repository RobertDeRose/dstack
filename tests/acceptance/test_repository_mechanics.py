from __future__ import annotations

import subprocess
from pathlib import Path

from .conftest import pour_feature, requires_bd, run_command, run_dstack, run_json


TASK_DESCRIPTION = """Provide a repository evidence fixture through the public commit command.

The description records the planned outcome rather than completed implementation bullets.
"""
TASK_DESIGN = """### Approach

Use the public commit command and native execution notes.

### Invariants

The canonical commit body contains only ordered implementation notes.
"""
PLAN_DESIGN = """### Goals

Provide canonical repository evidence for a native implementation task.

### User-facing behavior

Users create and correct task commits with one deterministic command.

### Implemented design

Git history retains one canonical commit for each implementation task.

### Compatibility and constraints

Legacy ownership footers remain readable but are not emitted.

### Validation

Acceptance exercises commit creation, correction, and close documentation.

### Non-goals

The fixture does not implement a workflow state database.
"""


def approve_feature(repo: Path, root: str, steps: dict[str, dict[str, object]]) -> None:
    run_json(
        repo,
        "update",
        str(steps["plan"]["id"]),
        "--design",
        PLAN_DESIGN,
        "--acceptance",
        "Users can create and correct one canonical implementation commit.",
    )
    run_json(repo, "close", str(steps["plan"]["id"]), "--reason", "Fixture plan complete")
    run_json(repo, "close", str(steps["review"]["id"]), "--reason", "Fixture review complete")
    gates = run_json(repo, "list", "--parent", root, "--all", "--include-gates", "--limit", "0")
    gate = next(issue for issue in gates if issue.get("await_id") == "approve-repository-mechanics-plan")
    run_command(["bd", "gate", "resolve", str(gate["id"]), "--reason", "Fixture approved"], cwd=repo)
    approval = run_json(
        repo,
        "ready",
        "--parent",
        root,
        "--label",
        "dstack:step:approval",
        "--claim",
    )[0]
    run_json(repo, "close", str(approval["id"]), "--reason", "Fixture approved")


@requires_bd
def test_worktree_commit_correction_and_task_evidence_use_native_state(real_repo: Path, tmp_path: Path) -> None:
    root, steps = pour_feature(real_repo, slug="repository-mechanics")
    task_file = tmp_path / "task.md"
    task_file.write_text(TASK_DESCRIPTION, encoding="utf-8")
    task = run_json(
        real_repo,
        "create",
        "Add repository evidence fixture",
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
        "--design",
        TASK_DESIGN,
        "--acceptance",
        "A reachable canonical commit contains one bullet per implementation note and exactly one matching Task trailer.",
    )
    task_id = str(task["id"])
    approve_feature(real_repo, root, steps)
    claimed = run_json(
        real_repo,
        "ready",
        "--parent",
        steps["implementation"]["id"],
        "--label",
        "dstack:work:implementation",
        "--claim",
    )
    assert claimed[0]["id"] == task_id

    ensured = run_dstack(real_repo, "worktree", "--bead", root)
    worktree = Path(ensured["worktree"])
    try:
        assert worktree.is_dir()
        assert ensured["branch"] == "feat/repository-mechanics"
        (worktree / "evidence.txt").write_text("native evidence\n", encoding="utf-8")
        run_command(["git", "add", "evidence.txt"], cwd=worktree)
        without_notes = run_dstack(worktree, "commit", "--bead", task_id, check=False)
        assert without_notes.returncode != 0
        assert "implementation note" in without_notes.stderr.lower()

        run_command(
            [
                "bd",
                "note",
                task_id,
                "Implementation: Add one repository evidence fixture through the public commit command.",
            ],
            cwd=real_repo,
        )
        committed = run_dstack(worktree, "commit", "--bead", task_id)
        assert committed["subject"] == "feat(repository-mechanics): add repository evidence fixture"
        message = run_command(["git", "log", "-1", "--format=%B"], cwd=worktree).stdout
        assert "- Add one repository evidence fixture through the public commit command" in message
        assert "The description records the planned outcome" not in message
        assert "Use the public commit command and native execution notes." not in message
        assert "The canonical commit body contains only ordered implementation notes." not in message
        assert message.count(f"Task: {task_id}") == 1
        assert "Beads:" not in message
        assert run_dstack(worktree, "check", "task", "--bead", task_id)["status"] == "ok"

        run_json(real_repo, "close", task_id, "--reason", "Fixture first implementation")
        run_json(real_repo, "reopen", task_id, "--reason", "Fixture correction")
        run_json(
            real_repo,
            "update",
            task_id,
            "--title",
            "Refine repository evidence fixture",
            "--description",
            "Preserve corrected repository evidence and reword stale commit messages.",
            "--design",
            "Use a correction note and the canonical autosquash path.",
        )
        reclaimed = run_json(real_repo, "update", task_id, "--claim")
        assert reclaimed[0]["id"] == task_id
        assert reclaimed[0]["status"] == "in_progress"
        run_command(
            ["bd", "note", task_id, "Implementation: Preserve corrected repository evidence."],
            cwd=real_repo,
        )
        run_command(
            ["bd", "note", task_id, "Implementation: Reword stale canonical commit messages."],
            cwd=real_repo,
        )

        (worktree / "evidence.txt").write_text("corrected evidence\n", encoding="utf-8")
        run_command(["git", "add", "evidence.txt"], cwd=worktree)
        corrected = run_dstack(worktree, "commit", "--bead", task_id)

        assert corrected["commit"] != committed["commit"]
        assert corrected["subject"] == "feat(repository-mechanics): refine repository evidence fixture"
        corrected_message = run_command(["git", "log", "-1", "--format=%B"], cwd=worktree).stdout
        assert "- Add one repository evidence fixture through the public commit command" in corrected_message
        assert "- Preserve corrected repository evidence" in corrected_message
        assert "- Reword stale canonical commit messages" in corrected_message
        assert "Preserve corrected repository evidence and reword stale commit messages." not in corrected_message
        assert "feat(repository-mechanics): add repository evidence fixture" not in corrected_message
        records = run_command(
            ["git", "log", "--format=%H%x00%B", "main..feat/repository-mechanics"], cwd=worktree
        ).stdout
        assert records.count(f"Task: {task_id}") == 1
        checked = run_dstack(worktree, "check", "task", "--bead", task_id)
        assert checked["status"] == "ok"
        assert len(checked["evidence"]["commits"]) == 1
        assert checked["evidence"]["commits"][0]["commit"] == corrected["commit"]
        assert checked["evidence"]["commits"][0]["subject"] == corrected["subject"]
        assert "paths" not in checked["evidence"]["commits"][0]

        run_json(real_repo, "close", task_id, "--reason", "Clean close review")
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
        close_step = run_json(
            real_repo,
            "ready",
            "--parent",
            root,
            "--label",
            "dstack:step:audit",
            "--claim",
        )[0]
        exported = run_dstack(worktree, "docs", "export-design", "--bead", root)
        assert exported["status"] == "ok"
        feature_docs = worktree / "docs/src/features/repository-mechanics"
        (feature_docs / "index.md").write_text(
            """# Repository mechanics

## Overview

This feature provides deterministic repository evidence for each implementation task.

## User Impact

Users receive one canonical task commit and one final documentation commit.

## Implemented Design

{{#include design.md}}
""",
            encoding="utf-8",
        )
        summary = worktree / "docs/src/SUMMARY.md"
        summary.write_text(
            "# Summary\n\n- [Repository mechanics](features/repository-mechanics/index.md)\n",
            encoding="utf-8",
        )
        run_command(
            [
                "git",
                "add",
                "docs/src/SUMMARY.md",
                "docs/src/features/repository-mechanics/index.md",
                "docs/src/features/repository-mechanics/design.md",
            ],
            cwd=worktree,
        )
        docs_commit = run_dstack(worktree, "docs", "commit", "--bead", root)
        assert docs_commit["bead"] == close_step["id"]
        assert docs_commit["subject"] == "docs(repository-mechanics): document the feature"
        audit = run_dstack(worktree, "audit", root, "--require-docs")
        assert audit["validation"]["project"]["status"] == "external"
        assert audit["validation"]["feature_docs"]["status"] == "ok"
        assert audit["git"]["close_commit"]["commit"] == docs_commit["commit"]
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=real_repo, check=False)
