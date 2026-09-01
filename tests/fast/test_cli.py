from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
from dstack import cli as dstack_cli
from dstack.commands import required_task_text, task_text
from dstack.core import DstackError


def leaves(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()):
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            child_prefix = (*prefix, name)
            nested = any(isinstance(item, argparse._SubParsersAction) for item in child._actions)
            if nested:
                yield from leaves(child, child_prefix)
            else:
                yield child_prefix, child


def test_task_text_preserves_file_content(tmp_path: Path) -> None:
    source = tmp_path / "body.md"
    content = "# Goal\n\nPreserve durable planning text.\n"
    source.write_text(content, encoding="utf-8")

    assert task_text(source, None) == content


def test_required_task_text_rejects_whitespace_only_file(tmp_path: Path) -> None:
    source = tmp_path / "body.md"
    source.write_text(" \n\t", encoding="utf-8")

    try:
        required_task_text(source, None)
    except DstackError as exc:
        assert "required" in str(exc)
    else:
        raise AssertionError("whitespace-only task text should be rejected")


def test_every_public_leaf_has_dispatch_handler() -> None:
    found = dict(leaves(dstack_cli.build_ctl_parser()))
    expected = (
        {
            ("feature", command)
            for command in (
                "resolve",
                "inspect",
                "initialize",
                "plan",
                "scaffold-design",
                "scaffold-reconciliation",
                "add-task",
                "claim-spec",
                "approve-spec",
                "audit-complete",
                "reauthorize",
                "claim-next",
                "finish-task",
                "finish-workstream",
                "claim-closeout",
                "finish-closeout",
            )
        }
        | {("git", command) for command in ("commit", "amend")}
        | {("evidence", command) for command in ("commits", "audit-feature")}
        | {("docs", command) for command in ("check", "validate")}
        | {
            ("delivery", command)
            for command in (
                "inspect",
                "pr-preflight",
                "register-pr",
                "replace-pr",
                "cancel-pr-gate",
                "merge",
                "finalize-pr",
            )
        }
        | {("audit", "feature")}
        | {("infra", "check")}
    )
    assert set(found) == expected
    assert all(callable(parser.get_default("func")) for parser in found.values())


def test_register_pr_help_describes_pre_merge_registration() -> None:
    parser = dict(leaves(dstack_cli.build_ctl_parser()))[("delivery", "register-pr")]
    help_text = parser.format_help()
    assert "open, unmerged" in help_text
    assert "pre-merge gate" in help_text


def test_ctl_reports_missing_input_files_as_json(monkeypatch, capsys, tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    def fake_add_task(args):
        return task_text(args.description_file, args.description)

    monkeypatch.setattr(dstack_cli, "cmd_feature_add_task", fake_add_task)

    assert (
        dstack_cli.ctl_main(
            [
                "feature",
                "add-task",
                "feature-1",
                "--title",
                "Task",
                "--description-file",
                str(missing),
            ]
        )
        == 1
    )
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "error"
    assert str(missing) in error["error"]


def test_main_dispatches_in_process(monkeypatch, capsys) -> None:
    seen = {}

    def fake(args):
        seen["args"] = args
        print('{"status":"ok"}')
        return 0

    monkeypatch.setattr(dstack_cli, "cmd_feature_resolve", fake)
    assert dstack_cli.ctl_main(["feature", "resolve", "feature-1"]) == 0
    assert seen["args"].selector == "feature-1"
    assert capsys.readouterr().out == '{"status":"ok"}\n'


def test_ctl_normalizes_expected_filesystem_errors(monkeypatch, capsys) -> None:
    def fail_with_permission(args):
        del args
        raise PermissionError("permission denied")

    monkeypatch.setattr(dstack_cli, "cmd_feature_resolve", fail_with_permission)
    assert dstack_cli.ctl_main(["feature", "resolve", "feature-1"]) == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload == {
        "status": "error",
        "error": "filesystem operation failed: permission denied",
    }
