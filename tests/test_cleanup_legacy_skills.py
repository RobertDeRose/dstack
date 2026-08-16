from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cleanup-legacy-pi-skills.py"


def run_cleanup(agent_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--agent-dir", str(agent_dir), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cleanup_is_dry_run_by_default_and_archives_only_dstack_skills(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    stale = agent_dir / "skills" / "close-feature"
    unrelated = agent_dir / "skills" / "setup-project"
    stale.mkdir(parents=True)
    unrelated.mkdir(parents=True)
    (stale / "SKILL.md").write_text("---\nname: close-feature\n---\nOld dstack workflow\n")
    (unrelated / "SKILL.md").write_text("---\nname: setup-project\n---\nUnrelated setup helper\n")

    dry_run = run_cleanup(agent_dir)
    assert dry_run.returncode == 0, dry_run.stderr
    assert stale.is_dir()
    assert unrelated.is_dir()
    assert "Dry run only" in dry_run.stdout
    assert "Skipped same-named skills" in dry_run.stdout

    applied = run_cleanup(agent_dir, "--apply")
    assert applied.returncode == 0, applied.stderr
    assert not stale.exists()
    assert unrelated.is_dir()
    backups = list((agent_dir / "skills-disabled").glob("dstack-legacy-*/close-feature"))
    assert len(backups) == 1
