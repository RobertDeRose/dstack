from __future__ import annotations

import json
from pathlib import Path
import pytest

from dstack import cli


def test_parser_exposes_ergonomic_commands() -> None:
    parser = cli.build_parser()

    skills = parser.parse_args(["install", "skills", "--agent-dir", "/tmp/agent"])
    assert skills.command == "skills"
    assert skills.agent_dir == Path("/tmp/agent")

    formula = parser.parse_args(["install", "formula", "--root", "/tmp/project", "--update"])
    assert formula.command == "formula"
    assert formula.root == Path("/tmp/project")
    assert formula.update is True

    plan = parser.parse_args(["check", "plan", "--bead", "ds-plan"])
    assert plan.command == "plan"
    assert plan.bead == "ds-plan"

    task = parser.parse_args(["check", "task", "-b", "ds-task"])
    assert task.command == "task"
    assert task.bead == "ds-task"

    docs = parser.parse_args(["check", "docs"])
    assert docs.command == "docs"

    commit = parser.parse_args(["commit", "--bead", "ds-task", "--body", "/tmp/body"])
    assert commit.bead == "ds-task"
    assert commit.body_file == Path("/tmp/body")
    assert commit.amend is False

    amend = parser.parse_args(["commit", "-a", "-b", "ds-task"])
    assert amend.amend is True

    worktree = parser.parse_args(["worktree", "--bead", "ds-feature"])
    assert worktree.bead == "ds-feature"

    audit = parser.parse_args(["audit", "ds-feature", "--include-plan"])
    assert audit.feature == "ds-feature"
    assert audit.include_plan is True


def test_legacy_command_names_are_removed() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ctl", "plan", "check", "ds-plan"])
    with pytest.raises(SystemExit):
        parser.parse_args(["install_skills"])
    with pytest.raises(SystemExit):
        parser.parse_args(["commit", "--bead", "ds-task", "--subject", "feat: manual"])


def test_root_dispatches_new_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def record(name: str, result: int):
        def command(values: object) -> int:
            calls.append((name, dict(vars(values))))
            return result

        return command

    monkeypatch.setattr(cli, "cmd_install_skills", record("skills", 11))
    monkeypatch.setattr(cli, "cmd_formula_install", record("formula", 12))
    monkeypatch.setattr(cli, "cmd_plan_check", record("plan", 13))
    monkeypatch.setattr(cli, "cmd_commit", record("commit", 14))
    monkeypatch.setattr(cli, "cmd_worktree_ensure", record("worktree", 15))

    assert cli.main(["install", "skills", "--agent-dir", "/tmp/agent"]) == 11
    assert cli.main(["install", "formula", "--root", "/tmp/project"]) == 12
    assert cli.main(["check", "plan", "--bead", "ds-plan"]) == 13
    assert cli.main(["commit", "--bead", "ds-task"]) == 14
    assert cli.main(["worktree", "--bead", "ds-feature"]) == 15
    assert [name for name, _ in calls] == ["skills", "formula", "plan", "commit", "worktree"]


def test_init_dispatches_from_the_unified_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def initialize(values: object) -> int:
        calls.append(dict(vars(values)))
        return 16

    monkeypatch.setattr(cli, "cmd_init", initialize)

    assert cli.main(["init", "--root", "/tmp/project", "--update"]) == 16
    assert calls[0]["root"] == Path("/tmp/project")
    assert calls[0]["update"] is True


def test_cli_failure_is_compact_json(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(["check", "plan", "--root", str(git_repo), "--bead", "missing"])
    captured = capsys.readouterr()
    assert result == 2
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
