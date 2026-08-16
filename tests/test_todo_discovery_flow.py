from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import run_json


def test_todo_is_ordinary_nonblocking_discovered_work(installed_repo: Path) -> None:
    current = run_json(
        [
            "bd",
            "create",
            "Current implementation",
            "--type",
            "task",
            "--description",
            "Current bounded work",
            "--acceptance",
            "Current work is complete",
            "--json",
        ],
        cwd=installed_repo,
    )
    todo = run_json(
        ["bd", "todo", "add", "Update incidental help text", "--json"],
        cwd=installed_repo,
    )
    run_json(
        [
            "bd",
            "dep",
            "add",
            todo["id"],
            current["id"],
            "--type",
            "discovered-from",
            "--json",
        ],
        cwd=installed_repo,
    )

    state = json.loads(Path(os.environ["DSTACK_FAKE_BD_STATE"]).read_text())
    assert state["issues"][todo["id"]]["type"] == "task"
    assert state["issues"][todo["id"]]["status"] == "open"
    assert state["relations"] == [
        {"from": todo["id"], "to": current["id"], "type": "discovered-from"}
    ]
    assert state["issues"][current["id"]]["dependencies"] == []
