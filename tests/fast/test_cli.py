from __future__ import annotations

import json
from pathlib import Path

from dstack import cli


def test_parser_exposes_only_targeted_control_plane_areas() -> None:
    parser = cli.build_ctl_parser()
    args = parser.parse_args(["plan", "check", "ds-plan"])
    assert args.area == "plan"
    assert args.command == "check"
    assert args.bead == "ds-plan"


def test_root_help_describes_two_entry_points(capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli.main([]) == 0
    output = capsys.readouterr().out
    assert "install_skills" in output
    assert "ctl" in output


def test_ctl_failure_is_compact_json(git_repo: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    result = cli.ctl_main(["--root", str(git_repo), "plan", "check", "missing"])
    captured = capsys.readouterr()
    assert result == 2
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
