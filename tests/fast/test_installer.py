from __future__ import annotations

from pathlib import Path

import pytest

from dstack.core import DstackError
from dstack.installer import SYSTEM_BEGIN, SYSTEM_END, install_skills


EXPECTED_SKILLS = {
    "dstack-beads-audit-feature",
    "dstack-beads-implement",
    "dstack-beads-plan-feature",
    "dstack-beads-review-plan",
}
EXPECTED_PROMPTS = {"audit-feature.md", "implement.md", "plan-feature.md", "review-plan.md"}


def test_installer_is_idempotent_and_preserves_user_system_guidance(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    target.mkdir()
    system = target / "APPEND_SYSTEM.md"
    system.write_text("user prefix\n", encoding="utf-8")

    first = install_skills(target)
    second = install_skills(target)

    assert set(first["skills"]) == EXPECTED_SKILLS
    assert set(first["prompts"]) == EXPECTED_PROMPTS
    assert second["status"] == "ok"
    text = system.read_text(encoding="utf-8")
    assert text.startswith("user prefix")
    assert text.count(SYSTEM_BEGIN) == 1
    assert text.count(SYSTEM_END) == 1
    assert {path.name for path in (target / "skills").iterdir()} == EXPECTED_SKILLS


def test_installer_removes_only_dstack_owned_legacy_resources(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    legacy = target / "skills/dstack-beads-close-feature"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text(
        "---\ndstack-managed: true\nname: dstack-beads-close-feature\n---\nold\n",
        encoding="utf-8",
    )
    user = target / "skills/close-feature"
    user.mkdir(parents=True)
    (user / "SKILL.md").write_text("---\nname: close-feature\n---\nuser\n", encoding="utf-8")

    result = install_skills(target)
    assert "skills/dstack-beads-close-feature" in result["removed_stale"]
    assert not legacy.exists()
    assert user.exists()


def test_installer_refuses_to_replace_user_owned_current_skill(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    current = target / "skills/dstack-beads-plan-feature"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text("---\nname: dstack-beads-plan-feature\n---\nuser\n", encoding="utf-8")
    with pytest.raises(DstackError, match="user-owned"):
        install_skills(target)
