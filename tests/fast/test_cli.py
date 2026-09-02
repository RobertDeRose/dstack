from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pytest

from dstack import cli


def test_parser_exposes_only_targeted_control_plane_areas() -> None:
    parser = cli.build_ctl_parser()
    args = parser.parse_args(["plan", "check", "ds-plan"])
    assert args.area == "plan"
    assert args.command == "check"
    assert args.bead == "ds-plan"


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
