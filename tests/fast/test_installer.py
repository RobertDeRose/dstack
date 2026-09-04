from __future__ import annotations

from pathlib import Path

import pytest

from dstack import installer
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
    retired_skill = target / "skills/dstack-audit-feature"
    retired_skill.mkdir(parents=True)
    (retired_skill / "SKILL.md").write_text(
        "---\ndstack-managed: true\nname: dstack-audit-feature\n---\nold\n",
        encoding="utf-8",
    )
    stale_prompt = target / "prompts/obsolete.md"
    stale_prompt.parent.mkdir(parents=True)
    stale_prompt.write_text(
        "---\ndstack-managed: true\nname: obsolete\n---\nold\n",
        encoding="utf-8",
    )
    retired_prompt = target / "prompts/audit-feature.md"
    retired_prompt.write_text(
        "---\ndstack-managed: true\nname: audit-feature\n---\nold\n",
        encoding="utf-8",
    )

    result = install_skills(target)

    assert not stale_skill.exists()
    assert not retired_skill.exists()
    assert not stale_prompt.exists()
    assert not retired_prompt.exists()
    assert result["removed_stale"] == [
        "skills/dstack-audit-feature",
        "skills/dstack-obsolete",
        "prompts/audit-feature.md",
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


def test_installer_preflights_every_destination_before_changes(tmp_path: Path) -> None:
    target = tmp_path / "agent"
    installed = target / "skills/dstack-plan-feature/SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_text(
        "---\ndstack-managed: true\nname: dstack-plan-feature\n---\nold\n",
        encoding="utf-8",
    )
    stale = target / "prompts/audit-feature.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(
        "---\ndstack-managed: true\nname: audit-feature\n---\nold\n",
        encoding="utf-8",
    )
    conflict = target / "prompts/review-plan.md"
    conflict.write_text("---\nname: review-plan\n---\nuser\n", encoding="utf-8")
    before = _file_snapshot(target)

    with pytest.raises(DstackError, match="user-owned prompt"):
        install_skills(target)

    assert _file_snapshot(target) == before


def test_installer_preserves_existing_resources_when_staging_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "agent"
    installed = target / "skills/dstack-plan-feature/SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_text(
        "---\ndstack-managed: true\nname: dstack-plan-feature\n---\nold\n",
        encoding="utf-8",
    )
    stale = target / "prompts/audit-feature.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(
        "---\ndstack-managed: true\nname: audit-feature\n---\nold\n",
        encoding="utf-8",
    )
    before = _file_snapshot(target)
    real_copy2 = installer.shutil.copy2

    def fail_on_late_prompt(source: str | Path, destination: str | Path, *args: object, **kwargs: object) -> str:
        if Path(source).name == "review-plan.md":
            raise OSError("simulated copy failure")
        return str(real_copy2(source, destination, *args, **kwargs))

    monkeypatch.setattr(installer.shutil, "copy2", fail_on_late_prompt)

    with pytest.raises(DstackError, match="cannot install dStack agent resources"):
        install_skills(target)

    assert _file_snapshot(target) == before


def test_installer_rolls_back_when_replacement_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "agent"
    installed_skill = target / "skills/dstack-plan-feature/SKILL.md"
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        "---\ndstack-managed: true\nname: dstack-plan-feature\n---\nold\n",
        encoding="utf-8",
    )
    installed_prompt = target / "prompts/review-plan.md"
    installed_prompt.parent.mkdir(parents=True)
    installed_prompt.write_text(
        "---\ndstack-managed: true\nname: review-plan\n---\nold\n",
        encoding="utf-8",
    )
    stale = target / "prompts/audit-feature.md"
    stale.write_text(
        "---\ndstack-managed: true\nname: audit-feature\n---\nold\n",
        encoding="utf-8",
    )
    before = _file_snapshot(target)
    real_replace = installer.os.replace
    failed = False

    def fail_once(source: str | Path, destination: str | Path) -> None:
        nonlocal failed
        if not failed and Path(destination) == installed_prompt and Path(source) != installed_prompt:
            failed = True
            raise OSError("simulated replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(installer.os, "replace", fail_once)

    with pytest.raises(DstackError, match="cannot install dStack agent resources"):
        install_skills(target)

    assert failed is True
    assert _file_snapshot(target) == before


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}
