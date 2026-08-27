from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_cli


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


def test_every_public_leaf_has_dispatch_handler() -> None:
    found = dict(leaves(dstack_cli.build_parser()))
    expected = (
        {
            ("feature", command)
            for command in (
                "resolve",
                "inspect",
                "initialize",
                "scaffold-design",
                "scaffold-reconciliation",
                "add-task",
                "claim-spec",
                "approve-spec",
                "reauthorize",
                "claim-next",
                "finish-task",
                "finish-workstream",
                "claim-closeout",
                "finish-closeout",
            )
        }
        | {
            ("alignment", command)
            for command in (
                "inspect",
                "scaffold-record",
                "initialize",
                "add-correction",
                "finish-plan",
                "approve",
                "reauthorize",
                "claim-next",
                "finish-task",
                "finish-workstream",
                "claim-landing",
                "finish-landing",
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
        | {("adopt", command) for command in ("plan", "inspect", "apply")}
        | {("audit", "feature")}
    )
    assert set(found) == expected
    assert all(callable(parser.get_default("func")) for parser in found.values())


def test_register_pr_help_describes_pre_merge_registration() -> None:
    parser = dict(leaves(dstack_cli.build_parser()))[("delivery", "register-pr")]
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
    monkeypatch.setenv("DSTACK_LOCKED_RUNTIME", "1")
    seen = {}

    def fake(args):
        seen["args"] = args
        print('{"status":"ok"}')
        return 0

    monkeypatch.setattr(dstack_cli, "cmd_feature_resolve", fake)
    assert dstack_cli.main(["feature", "resolve", "feature-1"]) == 0
    assert seen["args"].selector == "feature-1"
    assert capsys.readouterr().out == '{"status":"ok"}\n'
