from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import SETUP_SCRIPT, run_json


def test_setup_installs_cooks_and_validates_formulas(target_repo: Path) -> None:
    result = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"],
        cwd=target_repo,
    )
    assert result["status"] == "ok"
    assert result["beads_version"] == "bd version 1.2.2"
    assert result["formulas"] == {
        "dstack-feature": "installed",
        "dstack-project-alignment": "installed",
    }
    for name in result["protos"]:
        assert (target_repo / ".beads" / "formulas" / f"{name}.formula.toml").is_file()

    doctor = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "doctor", "--root", str(target_repo)],
        cwd=target_repo,
    )
    assert doctor["status"] == "ok"
    assert set(doctor["formulas"]) == {"dstack-feature", "dstack-project-alignment"}


def test_setup_is_idempotent(target_repo: Path) -> None:
    command = ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"]
    run_json(command, cwd=target_repo)
    second = run_json(command, cwd=target_repo)
    assert set(second["formulas"].values()) == {"unchanged"}


def test_setup_refuses_formula_conflict_without_force(target_repo: Path) -> None:
    command = ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"]
    run_json(command, cwd=target_repo)
    installed = target_repo / ".beads" / "formulas" / "dstack-feature.formula.toml"
    installed.write_text(installed.read_text() + "\n# local change\n")

    failed = run_json(command, cwd=target_repo, check=False)
    assert failed.returncode == 1
    error = json.loads(failed.stderr)
    assert "formula differs" in error["error"]

    forced = run_json([*command, "--force"], cwd=target_repo)
    assert forced["formulas"]["dstack-feature"] == "updated"
