from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dstack import commands as subject
from dstack.core import CommandResult


class WorktreeClient:
    def __init__(self, root: Path):
        self.root = root

    def worktrees(self) -> list[dict[str, Any]]:
        return []


def test_worktree_ensure_delegates_creation_to_beads(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = WorktreeClient(git_repo)
    original_run = subject.run
    observed: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> CommandResult:
        observed.append(list(command))
        if command[:3] == ["bd", "worktree", "create"]:
            path = Path(command[3])
            branch = command[5]
            return original_run(["git", "worktree", "add", str(path), branch], cwd=git_repo)
        if command[:3] == ["bd", "worktree", "remove"]:
            return original_run(["git", "worktree", "remove", "--force", command[3]], cwd=git_repo, check=False)
        return original_run(command, **kwargs)

    monkeypatch.setattr(subject, "run", fake_run)
    worktree, created_branch, created_worktree = subject.ensure_branch_worktree(
        client, "feat/native-control-plane", "main"  # type: ignore[arg-type]
    )
    try:
        assert created_branch is True
        assert created_worktree is True
        assert worktree.name.endswith(".feat-native-control-plane")
        assert ["bd", "worktree", "create", str(worktree), "--branch", "feat/native-control-plane"] in observed

        again = subject.ensure_branch_worktree(client, "feat/native-control-plane", "main")  # type: ignore[arg-type]
        assert again == (worktree, False, False)
    finally:
        original_run(["git", "worktree", "remove", "--force", str(worktree)], cwd=git_repo, check=False)
