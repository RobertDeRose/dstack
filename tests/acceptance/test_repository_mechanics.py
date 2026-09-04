from __future__ import annotations

import subprocess
from pathlib import Path

from .conftest import pour_feature, requires_bd, run_command, run_dstack, run_json


TASK_DESCRIPTION = """Implement a repository change.

## Documentation impact

- End-user: not affected - The acceptance fixture has no public behavior change.
- Developer: required - The committed file documents the test implementation boundary.
- Future-agent: required - The task and commit footer preserve discoverable rationale.
"""


@requires_bd
def test_worktree_commit_and_task_evidence_use_native_state(real_repo: Path, tmp_path: Path) -> None:
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
        "--labels",
        "dstack:commit:test",
        "--labels",
        "dstack:scope:evidence",
        "--deps",
        f"blocked-by:{steps['approval']['id']}",
        "--description-file",
        str(task_file),
        "--acceptance",
        "A reachable commit contains exactly one matching Beads footer.",
    )
    task_id = str(task["id"])

    ensured = run_dstack(real_repo, "worktree", "--bead", root)
    worktree = Path(ensured["worktree"])
    try:
        assert worktree.is_dir()
        assert ensured["branch"] == "feat/repository-mechanics"
        (worktree / "evidence.txt").write_text("native evidence\n", encoding="utf-8")
        run_command(["git", "add", "evidence.txt"], cwd=worktree)

        committed = run_dstack(worktree, "commit", "--bead", task_id)
        assert committed["subject"] == "test(evidence): add repository evidence fixture"

        (worktree / "evidence.txt").write_text("amended evidence\n", encoding="utf-8")
        run_command(["git", "add", "evidence.txt"], cwd=worktree)
        amended = run_dstack(worktree, "commit", "--amend", "--bead", task_id)
        assert amended["subject"] == committed["subject"]

        checked = run_dstack(worktree, "check", "task", "--bead", task_id)
        assert checked["status"] == "ok"
        assert checked["evidence"]["commits"][0]["commit"] == amended["commit"]
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=real_repo, check=False)
