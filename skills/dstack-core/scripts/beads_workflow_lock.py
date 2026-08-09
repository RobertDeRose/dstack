#!/usr/bin/env python3
# ruff: noqa: EM102, S603, S607
"""Serialize dstack Beads mutation intervals without repository state."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import IO, NoReturn


class WorkflowLockError(RuntimeError):
    """Raised when a repository workflow lock cannot be acquired."""


class WorkflowLock(AbstractContextManager["WorkflowLock"]):
    """Hold an exclusive process-backed lock for one repository."""

    def __init__(
        self,
        repository_root: Path,
        *,
        lock_dir: Path | None = None,
        timeout: float = 0.0,
        run_id: str | None = None,
    ) -> None:
        self.repository_root = canonical_repository_root(repository_root)
        self.lock_dir = (lock_dir or default_lock_dir()).expanduser().resolve()
        self.timeout = timeout
        self.run_id = run_id or os.environ.get("DSTACK_WORKFLOW_RUN_ID", "unknown")
        digest = hashlib.sha256(str(self.repository_root).encode()).hexdigest()[:24]
        self.path = self.lock_dir / f"{digest}.lock"
        self._handle: IO[str] | None = None

    def __enter__(self) -> WorkflowLock:
        if not self.repository_root.is_dir():
            raise WorkflowLockError(f"repository root does not exist: {self.repository_root}")
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + max(self.timeout, 0.0)
        while True:
            try:
                flags = fcntl.LOCK_EX | fcntl.LOCK_NB
                fcntl.flock(self._handle.fileno(), flags)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._close()
                    raise WorkflowLockError(
                        f"workflow lock is busy for {self.repository_root}; another dstack mutation is active"
                    ) from None
                time.sleep(min(0.05, max(deadline - time.monotonic(), 0.0)))
        self._handle.seek(0)
        self._handle.truncate()
        json.dump(
            {
                "repository_root": str(self.repository_root),
                "run_id": self.run_id,
                "pid": os.getpid(),
            },
            self._handle,
            sort_keys=True,
        )
        self._handle.write("\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._close()

    def _close(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def canonical_repository_root(repository_root: Path) -> Path:
    resolved = repository_root.expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return resolved
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = resolved / common
    common = common.resolve()
    return common.parent if common.name == ".git" else resolved


def default_lock_dir() -> Path:
    configured = os.environ.get("DSTACK_WORKFLOW_LOCK_DIR")
    if configured:
        return Path(configured)
    return Path(os.environ.get("TMPDIR", "/tmp")) / "dstack-workflow-locks"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser("exec", help="run a command while holding the repository lock")
    execute.add_argument("--repository-root", type=Path, required=True)
    execute.add_argument("--lock-dir", type=Path)
    execute.add_argument("--timeout", type=float, default=0.0)
    execute.add_argument("--run-id")
    execute.add_argument("--", dest="separator", action="store_true")
    execute.add_argument("command_args", nargs=argparse.REMAINDER)
    return result


def fail(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command != "exec":
        fail(f"unsupported command: {args.command}")
    if not args.command_args:
        fail("exec requires a command after --")
    command = list(args.command_args)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        fail("exec requires a command after --")
    try:
        with WorkflowLock(
            args.repository_root,
            lock_dir=args.lock_dir,
            timeout=args.timeout,
            run_id=args.run_id,
        ):
            completed = subprocess.run(command, check=False)
    except WorkflowLockError as error:
        fail(str(error))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
