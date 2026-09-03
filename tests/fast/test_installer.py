from __future__ import annotations

from pathlib import Path

import pytest

from dstack.core import DstackError
from dstack.installer import CURRENT_PROMPTS, CURRENT_SKILLS, install_skills

EXPECTED_SKILLS = set(CURRENT_SKILLS)
EXPECTED_PROMPTS = set(CURRENT_PROMPTS)


def test_installer_is_idempotent_and_leaves_unrelated_agent_files_untouched(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    target.mkdir()
    system = target / "APPEND_SYSTEM.md"
    system.write_text("user-owned guidance\n", encoding="utf-8")
    unrelated = target / "skills/user-skill"
    unrelated.mkdir(parents=True)
    (unrelated / "SKILL.md").write_text("---\nname: user-skill\n---\nuser\n", encoding="utf-8")

    first = install_skills(target)
    second = install_skills(target)

    assert set(first["skills"]) == EXPECTED_SKILLS
    assert set(first["prompts"]) == EXPECTED_PROMPTS
    assert second["status"] == "ok"
    assert system.read_text(encoding="utf-8") == "user-owned guidance\n"
    assert unrelated.is_dir()
    assert EXPECTED_SKILLS <= {path.name for path in (target / "skills").iterdir()}
    assert first["removed_stale"] == []


def test_installer_removes_stale_owned_resources(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    stale_skill = target / "skills/dstack-obsolete"
    stale_skill.mkdir(parents=True)
    (stale_skill / "SKILL.md").write_text(
        "---\ndstack-managed: true\nname: dstack-obsolete\n---\nold\n",
        encoding="utf-8",
    )
    stale_prompt = target / "prompts/obsolete.md"
    stale_prompt.parent.mkdir(parents=True)
    stale_prompt.write_text(
        "---\ndstack-managed: true\nname: obsolete\n---\nold\n",
        encoding="utf-8",
    )

    result = install_skills(target)

    assert not stale_skill.exists()
    assert not stale_prompt.exists()
    assert result["removed_stale"] == [
        "skills/dstack-obsolete",
        "prompts/obsolete.md",
    ]


def test_installer_refuses_to_replace_user_owned_current_skill(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    current = target / "skills/dstack-plan-feature"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text("---\nname: dstack-plan-feature\n---\nuser\n", encoding="utf-8")
    original = (current / "SKILL.md").read_bytes()
    with pytest.raises(DstackError):
        install_skills(target)
    assert (current / "SKILL.md").read_bytes() == original
