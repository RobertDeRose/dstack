"""Behavioral tests for installed-skill version diagnostics."""

# ruff: noqa: S603 - test subprocesses invoke the repository's fixed diagnostic script.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
SCRIPT = REPOSITORY_ROOT / "skills/dstack-core/scripts/check-skill-version.py"
MUTATION_SKILLS = (
    "audit-project",
    "close-feature",
    "implement-feature",
    "implement-task",
    "migrate-workflow",
    "plan-features",
    "setup-project",
    "start-feature",
    "update-project",
)


def run_diagnostic(
    tmp_path: Path,
    *,
    installed_version: str = "1.2.3",
    canonical_version: str | None = "1.2.3",
) -> dict[str, object]:
    installed = tmp_path / "installed/start-feature"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text(
        f'---\nname: start-feature\nmetadata:\n  version: "{installed_version}"\n---\n',
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(SCRIPT),
        "--skill-name",
        "start-feature",
        "--installed-skill-dir",
        str(installed),
        "--format",
        "json",
    ]
    if canonical_version is not None:
        canonical = tmp_path / "canonical"
        (canonical / "skills/start-feature").mkdir(parents=True)
        (canonical / "skills/start-feature/SKILL.md").write_text(
            f'---\nname: start-feature\nmetadata:\n  version: "{canonical_version}"\n---\n',
            encoding="utf-8",
        )
        (canonical / "pyproject.toml").write_text(
            f'[project]\nname = "dstack-workflow"\nversion = "{canonical_version}"\n',
            encoding="utf-8",
        )
        command.extend(["--canonical-root", str(canonical)])
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_equal_versions_are_current_and_recorded(tmp_path: Path) -> None:
    evidence = run_diagnostic(tmp_path)

    assert evidence["status"] == "current"
    assert evidence["installed_version"] == "1.2.3"
    assert evidence["canonical_version"] == "1.2.3"
    assert "Skill version evidence:" in str(evidence["evidence_line"])
    assert "installed=1.2.3" in str(evidence["evidence_line"])


def test_stale_versions_warn_with_refresh_command(tmp_path: Path) -> None:
    evidence = run_diagnostic(tmp_path, installed_version="1.1.0", canonical_version="1.2.3")

    assert evidence["status"] == "stale"
    assert evidence["installed_version"] == "1.1.0"
    assert evidence["canonical_version"] == "1.2.3"
    assert evidence["refresh_command"] == "npx skills update"
    assert "stale" in str(evidence["message"]).casefold()
    assert "npx skills update" in str(evidence["evidence_line"])


def test_refresh_requires_a_new_session_boundary_across_mutation_skills() -> None:
    reference = (REPOSITORY_ROOT / "skills/dstack-core/references/SKILL-VERSION.md").read_text(encoding="utf-8")
    assert "session must stop" in reference
    assert "dstack.skill-session-rebind.v1" in reference
    assert "prior_evidence" in reference
    assert "new_evidence" in reference
    assert "refresh_action" in reference
    assert "new_session_id" in reference
    assert "workflow_run_id" in reference
    assert "Beads-backed workflows" in reference
    assert "response/JSON workflows" in reference
    assert "new session" in reference
    for skill in MUTATION_SKILLS:
        text = (REPOSITORY_ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").casefold()
        assert "new session" in text
        assert "refreshed" in text
        assert "workflow_run_id" in text


def test_missing_canonical_evidence_is_reported_without_freshness_claim(tmp_path: Path) -> None:
    evidence = run_diagnostic(tmp_path, canonical_version=None)

    assert evidence["status"] == "unavailable"
    assert evidence["installed_version"] == "1.2.3"
    assert evidence["canonical_version"] is None
    assert "unavailable" in str(evidence["message"]).casefold()
    assert "freshness claim" in str(evidence["message"]).casefold()
    assert evidence["refresh_command"] is None
