from __future__ import annotations

import json
from pathlib import Path
import pytest

from dstack import cli


def test_parser_exposes_ergonomic_commands() -> None:
    parser = cli.build_parser()

    install = parser.parse_args(["install", "--agent-dir", "/tmp/agent"])
    assert install.top_command == "install"
    assert install.agent_dir == Path("/tmp/agent")

    formula_check = parser.parse_args(["check", "formula", "--root", "/tmp/project"])
    assert formula_check.command == "formula"
    assert formula_check.root == Path("/tmp/project")

    plan = parser.parse_args(["check", "plan", "--bead", "ds-plan"])
    assert plan.command == "plan"
    assert plan.bead == "ds-plan"

    review = parser.parse_args(["check", "review", "--bead", "ds-root"])
    assert review.command == "review"
    assert review.bead == "ds-root"

    task = parser.parse_args(["check", "task", "-b", "ds-task"])
    assert task.command == "task"
    assert task.bead == "ds-task"

    docs = parser.parse_args(["check", "docs", "--slug", "example"])
    assert docs.command == "docs"
    assert docs.slug == "example"

    export = parser.parse_args(["docs", "export-design", "--bead", "ds-root"])
    assert export.command == "export-design"
    assert export.bead == "ds-root"

    docs_commit = parser.parse_args(["docs", "commit", "--bead", "ds-root"])
    assert docs_commit.command == "commit"
    assert docs_commit.bead == "ds-root"

    commit = parser.parse_args(["commit", "--bead", "ds-task"])
    assert commit.bead == "ds-task"

    worktree = parser.parse_args(["worktree", "--bead", "ds-feature"])
    assert worktree.bead == "ds-feature"

    feature = parser.parse_args(
        ["check", "feature", "--bead", "ds-feature", "--include-plan", "--require-docs"]
    )
    assert feature.bead == "ds-feature"
    assert feature.include_plan is True
    assert feature.require_docs is True


def test_legacy_command_names_are_removed() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ctl", "plan", "check", "ds-plan"])
    with pytest.raises(SystemExit):
        parser.parse_args(["install_skills"])
    with pytest.raises(SystemExit):
        parser.parse_args(["install", "skills"])
    with pytest.raises(SystemExit):
        parser.parse_args(["audit", "--bead", "ds-root"])
    with pytest.raises(SystemExit):
        parser.parse_args(["commit", "--bead", "ds-task", "--subject", "feat: manual"])
    with pytest.raises(SystemExit):
        parser.parse_args(["commit", "--amend", "--bead", "ds-task"])
    with pytest.raises(SystemExit):
        parser.parse_args(["commit", "--body", "/tmp/body", "--bead", "ds-task"])


def test_root_dispatches_new_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def record(name: str, result: int):
        def command(values: object) -> int:
            calls.append((name, dict(vars(values))))
            return result

        return command

    monkeypatch.setattr(cli, "cmd_install_agent_resources", record("install", 11))
    monkeypatch.setattr(cli, "cmd_formula_check", record("formula-check", 17))
    monkeypatch.setattr(cli, "cmd_plan_check", record("plan", 13))
    monkeypatch.setattr(cli, "cmd_review_check", record("review", 18))
    monkeypatch.setattr(cli, "cmd_docs_export", record("docs-export", 19))
    monkeypatch.setattr(cli, "cmd_git_commit_docs", record("docs-commit", 20))
    monkeypatch.setattr(cli, "cmd_git_commit", record("commit", 14))
    monkeypatch.setattr(cli, "cmd_worktree_ensure", record("worktree", 15))
    monkeypatch.setattr(cli, "cmd_feature_check", record("feature-check", 21))

    assert cli.main(["install", "--agent-dir", "/tmp/agent"]) == 11
    assert cli.main(["check", "formula", "--root", "/tmp/project"]) == 17
    assert cli.main(["check", "plan", "--bead", "ds-plan"]) == 13
    assert cli.main(["check", "review", "--bead", "ds-root"]) == 18
    assert cli.main(["docs", "export-design", "--bead", "ds-root"]) == 19
    assert cli.main(["docs", "commit", "--bead", "ds-root"]) == 20
    assert cli.main(["commit", "--bead", "ds-task"]) == 14
    assert cli.main(["worktree", "--bead", "ds-feature"]) == 15
    assert cli.main(["check", "feature", "--bead", "ds-feature"]) == 21
    assert [name for name, _ in calls] == [
        "install",
        "formula-check",
        "plan",
        "review",
        "docs-export",
        "docs-commit",
        "commit",
        "worktree",
        "feature-check",
    ]


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


@pytest.mark.parametrize(
    "command",
    [
        ["check", "plan"],
        ["check", "review"],
        ["check", "feature"],
        ["docs", "export-design"],
        ["docs", "commit"],
        ["worktree"],
    ],
)
def test_feature_commands_use_one_bead_selector(command: list[str]) -> None:
    parser = cli.build_parser()
    assert parser.parse_args([*command, "--bead", "root"]).bead == "root"
    with pytest.raises(SystemExit):
        parser.parse_args([*command, "--feature", "root"])


def test_docs_slug_and_feature_check_bead_are_unambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli.build_parser().parse_args(["check", "docs", "--slug", "example"]).slug == "example"
    captured: list[str] = []
    monkeypatch.setattr(cli, "cmd_feature_check", lambda args: captured.append(args.bead) or 0)
    assert cli.main(["check", "feature", "--bead", "root"]) == 0
    assert captured == ["root"]
    with pytest.raises(SystemExit):
        cli.main(["check", "feature", "root"])
    with pytest.raises(SystemExit):
        cli.main(["check", "feature"])
