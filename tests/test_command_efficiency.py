from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/dstack-beads-core/scripts"
sys.path.insert(0, str(SCRIPTS))

import dstacklib


def test_beads_read_cache_is_request_local_and_write_invalidated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    issue = {"id": "bd-1", "status": "open", "title": "one"}

    def fake_run(command, *, cwd, check=True, **kwargs):
        del cwd, check, kwargs
        calls.append(tuple(command))
        if command[:2] == ["bd", "show"]:
            return dstacklib.CommandResult(0, json.dumps([issue]), "")
        if command[:2] == ["bd", "list"]:
            return dstacklib.CommandResult(0, json.dumps([issue]), "")
        if command[:2] == ["bd", "update"]:
            return dstacklib.CommandResult(0, json.dumps([issue]), "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(dstacklib, "run", fake_run)
    client = dstacklib.BeadsClient.__new__(dstacklib.BeadsClient)
    client.root = tmp_path
    client._read_cache = {}

    client.show("bd-1")
    client.show("bd-1")
    client.list()
    client.list()
    assert calls.count(("bd", "show", "bd-1", "--json")) == 1
    assert calls.count(("bd", "list", "--limit", "0", "--json", "--all")) == 1

    client.update("bd-1", "--title", "updated")
    client.show("bd-1")
    assert calls.count(("bd", "show", "bd-1", "--json")) == 2


def test_footer_audit_reads_commit_paths_with_one_git_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    output = "\x1eabc123\x00subject\x00subject\n\nBeads: bd-1\n\x00\n\nfile.py\n"

    def fake_run(command, *, cwd, check=True, **kwargs):
        del cwd, check, kwargs
        calls.append(tuple(command))
        if command[:2] == ["git", "log"]:
            return dstacklib.CommandResult(0, output, "")
        raise AssertionError(f"footer audit spawned another Git command: {command}")

    monkeypatch.setattr(dstacklib, "run", fake_run)
    assert dstacklib.commit_footer_ids(tmp_path, "main..feature") == {
        "bd-1": [
            {"commit": "abc123", "subject": "subject", "paths": ["file.py"]}
        ]
    }
    assert len(calls) == 1
