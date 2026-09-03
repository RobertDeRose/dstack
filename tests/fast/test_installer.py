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
    assert "system_prompt" not in first
    assert first["removed_stale"] == []


def test_installer_removes_stale_owned_resources_without_a_legacy_name_list(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    legacy = target / "skills/dstack-beads-obsolete"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text(
        "---\ndstack-managed: true\nname: dstack-beads-obsolete\n---\nold\n",
        encoding="utf-8",
    )
    stale_prompt = target / "prompts/obsolete.md"
    stale_prompt.parent.mkdir(parents=True)
    stale_prompt.write_text(
        "---\ndstack-managed: true\nname: obsolete\n---\nold\n",
        encoding="utf-8",
    )

    result = install_skills(target)

    assert not legacy.exists()
    assert not stale_prompt.exists()
    assert result["removed_stale"] == [
        "skills/dstack-beads-obsolete",
        "prompts/obsolete.md",
    ]


def test_installer_refuses_to_replace_user_owned_current_skill(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    current = target / "skills/dstack-beads-plan-feature"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text("---\nname: dstack-beads-plan-feature\n---\nuser\n", encoding="utf-8")
    original = (current / "SKILL.md").read_bytes()
    with pytest.raises(DstackError):
        install_skills(target)
    assert (current / "SKILL.md").read_bytes() == original


def test_installer_removes_only_the_obsolete_managed_system_block(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    target.mkdir()
    system = target / "APPEND_SYSTEM.md"
    system.write_text(
        "user before\n\n"
        "<!-- dstack:managed-system-prompt:begin -->\n"
        "obsolete dStack guidance\n"
        "<!-- dstack:managed-system-prompt:end -->\n\n"
        "user after\n",
        encoding="utf-8",
    )

    result = install_skills(target)

    assert system.read_text(encoding="utf-8") == "user before\n\nuser after\n"
    assert "APPEND_SYSTEM.md#dstack-managed-block" in result["removed_stale"]
