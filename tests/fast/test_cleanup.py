from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    stale_names = ("close-feature", "start-feature", "plan-feature")
    stale = [agent_dir / "skills" / name for name in stale_names]
    unrelated = agent_dir / "skills" / "setup-project"
    for path in stale:
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(f"---\nname: {path.name}\n---\nOld dstack workflow\n")
    unrelated.mkdir(parents=True)
    (unrelated / "SKILL.md").write_text("---\nname: setup-project\n---\nUnrelated setup helper\n")

    dry_run = run_cleanup(agent_dir)
    assert dry_run.returncode == 0, dry_run.stderr
    assert all(path.is_dir() for path in stale)
    assert unrelated.is_dir()
    assert "Dry run only" in dry_run.stdout
    assert "Skipped same-named skills" in dry_run.stdout

    applied = run_cleanup(agent_dir, "--apply")
    assert applied.returncode == 0, applied.stderr
    assert all(not path.exists() for path in stale)
    assert unrelated.is_dir()
    for name in stale_names:
        backups = list((agent_dir / "skills-disabled").glob(f"dstack-legacy-*/{name}"))
        assert len(backups) == 1
