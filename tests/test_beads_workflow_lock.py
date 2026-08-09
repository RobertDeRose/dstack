# ruff: noqa: EM102, S603

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/dstack-core/scripts/beads-workflow-lock.py"


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(f"command failed: {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def run_lock(
    repository: Path,
    lock_dir: Path,
    command: list[str],
    *,
    timeout: float = 0.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "exec",
            "--repository-root",
            str(repository),
            "--lock-dir",
            str(lock_dir),
            "--timeout",
            str(timeout),
            "--",
            *command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(f"command failed: {result.args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def test_workflow_lock_serializes_repository_mutations(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    lock_dir = tmp_path / "locks"
    marker = tmp_path / "started"
    holder = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT),
            "exec",
            "--repository-root",
            str(repository),
            "--lock-dir",
            str(lock_dir),
            "--timeout",
            "1",
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(0.4)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()

        blocked = run_lock(repository, lock_dir, [sys.executable, "-c", "pass"], check=False)

        assert blocked.returncode != 0
        assert "workflow lock is busy" in blocked.stderr
    finally:
        holder.wait(timeout=3)

    released = run_lock(repository, lock_dir, [sys.executable, "-c", "print('released')"])

    assert released.stdout.strip() == "released"
    assert not (repository / ".dstack-workflow.lock").exists()


def test_workflow_lock_is_shared_by_linked_worktrees(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    lock_dir = tmp_path / "locks"
    run(["git", "init", "-b", "main"], cwd=repository)
    run(["git", "config", "user.name", "Test User"], cwd=repository)
    run(["git", "config", "user.email", "test@example.com"], cwd=repository)
    (repository / "file.txt").write_text("base\n", encoding="utf-8")
    run(["git", "add", "file.txt"], cwd=repository)
    run(["git", "commit", "-m", "initial"], cwd=repository)
    feature = tmp_path / "feature"
    run(["git", "worktree", "add", "-b", "feat/example", str(feature), "main"], cwd=repository)
    marker = tmp_path / "started"
    holder = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT),
            "exec",
            "--repository-root",
            str(repository),
            "--lock-dir",
            str(lock_dir),
            "--timeout",
            "1",
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(0.4)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        blocked = run_lock(feature, lock_dir, [sys.executable, "-c", "pass"], check=False)
        assert blocked.returncode != 0
        assert "workflow lock is busy" in blocked.stderr
    finally:
        holder.wait(timeout=3)


def test_workflow_lock_does_not_create_repository_state(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    lock_dir = tmp_path / "locks"

    run_lock(repository, lock_dir, [sys.executable, "-c", "pass"])

    assert list(repository.iterdir()) == []
    assert list(lock_dir.iterdir())
