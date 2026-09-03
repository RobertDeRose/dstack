from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pytest

from dstack import cli


def test_parser_exposes_only_targeted_control_plane_areas() -> None:
    parser = cli.build_ctl_parser()
    args = parser.parse_args(["formula", "check"])
    assert args.area == "formula"
    assert args.command == "check"

    task = parser.parse_args(["task", "check", "ds-task"])
    assert task.bead == "ds-task"
    assert not hasattr(task, "base")
    assert not hasattr(task, "validation_command")

    audit = parser.parse_args(
        [
            "audit",
            "evidence",
            "ds-root",
            "--include-task",
            "ds-task",
            "--history-for",
            "ds-task",
        ]
    )
    assert audit.include_task == ["ds-task"]
    assert audit.history_for == ["ds-task"]


def test_root_dispatches_both_supported_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def install(values: Sequence[str] | None = None) -> int:
        calls.append(("install_skills", list(values or [])))
        return 11

    def control(values: Sequence[str] | None = None) -> int:
        calls.append(("ctl", list(values or [])))
        return 12

    monkeypatch.setattr(cli, "install_skills_main", install)
    monkeypatch.setattr(cli, "ctl_main", control)

    assert cli.main(["install_skills", "--agent-dir", "/tmp/agent"]) == 11
    assert cli.main(["ctl", "plan", "check", "ds-plan"]) == 12
    assert calls == [
        ("install_skills", ["--agent-dir", "/tmp/agent"]),
        ("ctl", ["plan", "check", "ds-plan"]),
    ]


def test_ctl_failure_is_compact_json(git_repo: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    result = cli.ctl_main(["--root", str(git_repo), "plan", "check", "missing"])
    captured = capsys.readouterr()
    assert result == 2
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
