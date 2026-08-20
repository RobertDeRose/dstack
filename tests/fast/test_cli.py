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
    expected = {
        ("feature", command) for command in (
            "resolve", "inspect", "initialize", "scaffold-design", "add-task",
            "claim-spec", "approve-spec", "claim-next", "finish-task",
            "finish-workstream", "claim-closeout", "finish-closeout",
        )
    } | {
        ("alignment", command) for command in (
            "inspect", "initialize", "add-correction", "finish-plan", "approve",
            "claim-next", "finish-task", "finish-workstream", "claim-landing", "finish-landing",
        )
    } | {
        ("git", command) for command in ("commit", "amend")
    } | {
        ("evidence", command) for command in ("commits", "audit-feature")
    } | {("docs", "check")} | {
        ("delivery", command) for command in (
            "inspect", "pr-preflight", "register-pr", "merge", "finalize-pr",
        )
    } | {("adopt", command) for command in ("inspect", "apply")}
    assert set(found) == expected
    assert all(callable(parser.get_default("func")) for parser in found.values())


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
