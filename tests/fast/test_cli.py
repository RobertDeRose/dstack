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
                "merge",
                "finalize-pr",
            )
        }
        | {("adopt", command) for command in ("inspect", "apply")}
        | {("audit", "feature")}
    )
    assert set(found) == expected
    assert all(callable(parser.get_default("func")) for parser in found.values())


def test_register_pr_help_describes_pre_merge_registration() -> None:
    parser = dict(leaves(dstack_cli.build_parser()))[("delivery", "register-pr")]
    help_text = parser.format_help()
    assert "open, unmerged" in help_text
    assert "pre-merge gate" in help_text


def test_main_dispatches_in_process(monkeypatch, capsys) -> None:
    seen = {}

    def fake(args):
        seen["args"] = args
        print('{"status":"ok"}')
        return 0

    monkeypatch.setattr(dstack_cli, "cmd_feature_resolve", fake)
    assert dstack_cli.main(["feature", "resolve", "feature-1"]) == 0
    assert seen["args"].selector == "feature-1"
    assert capsys.readouterr().out == '{"status":"ok"}\n'
