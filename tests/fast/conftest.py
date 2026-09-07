from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_git_repo(path: Path, *, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--initial-branch", branch, "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    (path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=path, check=True)
    return path


@pytest.fixture(autouse=True)
def forbid_unmocked_beads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "forbidden-bin"
    bin_dir.mkdir()
    bd = bin_dir / "bd"
    bd.write_text("#!/bin/sh\necho 'fast tests must not invoke real bd' >&2\nexit 97\n", encoding="utf-8")
    bd.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    return make_git_repo(tmp_path / "repo")


# Public-command fixtures replace only the bd process, not dStack's cooperating functions.
from dstack import cli
from dstack.core import run
from dstack.policy import PLAN_SECTIONS


@dataclass
class FeatureRepository:
    repo: Path
    worktree: Path
    catalog: Path
    calls: Path
    data: dict[str, Any]

    def save(self) -> None:
        self.catalog.write_text(json.dumps(self.data), encoding="utf-8")

    def invoke(self, *arguments: str, expected: int = 0, primary: bool = False) -> dict[str, Any]:
        self.save()
        stdout, stderr = io.StringIO(), io.StringIO()
        root = self.repo if primary else self.worktree
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main([*arguments, "--root", str(root)])
        assert code == expected, (code, stdout.getvalue(), stderr.getvalue())
        return json.loads(stdout.getvalue() or stderr.getvalue())

    def commit(self, message: str, *, path: str = "change.txt", content: str = "change\n") -> str:
        target = self.worktree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        run(["git", "add", "--", path], cwd=self.worktree)
        run(["git", "commit", "-F", "-"], cwd=self.worktree, input_text=message)
        return run(["git", "rev-parse", "HEAD"], cwd=self.worktree).stdout.strip()


@pytest.fixture
def public_feature(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FeatureRepository:
    workspace = git_repo / ".beads"
    workspace.mkdir()
    (git_repo / ".git/info/exclude").write_text(".beads/\n", encoding="utf-8")
    worktree = git_repo.with_name(git_repo.name + ".feat-example")
    run(["git", "worktree", "add", "-b", "feat/example", str(worktree)], cwd=git_repo)
    roles = {
        name: {
            "id": name,
            "title": name.title(),
            "parent": "root",
            "status": "closed",
            "issue_type": "epic" if name == "implementation" else "task",
            "labels": [f"dstack:step:{name}"],
        }
        for name in ("plan", "review", "approval", "implementation", "audit")
    }
    roles["implementation"]["status"] = "open"
    roles["audit"].update(status="in_progress", dependencies=[
        {"id": "approval", "dependency_type": "blocks"},
        {"id": "implementation", "dependency_type": "waits-for"},
        {"id": "gate", "dependency_type": "blocks"},
    ])
    roles["plan"].update(description="Deliver the reviewed behavior.",
                         design="\n\n".join(f"### {title}\n\nUse native evidence for this outcome." for title in PLAN_SECTIONS) + "\n",
                         acceptance_criteria="The requested outcome is observable.")
    task = {"id": "task", "title": "Implement behavior", "status": "closed", "parent": "implementation",
            "issue_type": "task", "labels": ["dstack:work:implementation"], "description": "Implement behavior.",
            "design": "Use native ownership and acceptance criteria.", "acceptance_criteria": "The behavior is tested.",
            "notes": "No repository change: The accepted investigation requires no changes.",
            "dependencies": [{"id": "approval", "dependency_type": "blocks"}],
            "comments": [{"text": "Review correction: preserve inbound timestamps."}]}
    decision = {"id": "decision", "title": "Use native state", "status": "closed", "issue_type": "decision",
                "labels": ["decision:example"], "description": "Accepted durable rationale.",
                "dependencies": [{"id": "root", "dependency_type": "relates-to"}]}
    data = {"workspace": str(workspace), "worktrees": [{"path": str(worktree), "branch": "feat/example"}],
            "issues": {**roles, "task": task, "decision": decision,
                       "unrelated": {**decision, "id": "unrelated", "dependencies": []},
                       "gate": {"id": "gate", "issue_type": "gate", "status": "closed", "title": "Review gate"},
                       "root": {"id": "root", "title": "Feature: Example", "issue_type": "molecule", "status": "open",
                                "labels": ["workflow:feature", "feature:example"],
                                "metadata": {"dstack.base_branch": "main"}}}}
    catalog, calls = tmp_path / "beads.json", tmp_path / "calls.jsonl"
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    stub = stub_dir / "bd"
    stub.write_text(f"#!{sys.executable} -S\n" + Path(__file__).with_name("bd_stub.py").read_text(), encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("DSTACK_TEST_BEADS", str(catalog))
    monkeypatch.setenv("DSTACK_TEST_CALLS", str(calls))
    monkeypatch.setenv("PATH", f"{stub_dir}:{os.environ.get('PATH', '')}")
    feature = FeatureRepository(git_repo, worktree, catalog, calls, data)
    feature.save()
    return feature
