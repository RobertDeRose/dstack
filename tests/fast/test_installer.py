from __future__ import annotations

import json
from pathlib import Path

import pytest

from dstack import installer as dstack_installer
from dstack.core import DstackError
from dstack.installer import SYSTEM_BEGIN, SYSTEM_END, default_agent_dir, install_skills


def test_install_skills_installs_decision_resources_and_system_additive(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    payload = install_skills(agent)

    assert payload["status"] == "ok"
    assert "dstack-beads-core" not in payload["skills"]
    assert (agent / "skills/dstack-beads-plan-feature/SKILL.md").is_file()
    assert (agent / "prompts/plan-feature.md").is_file()
    system = (agent / "APPEND_SYSTEM.md").read_text()
    assert SYSTEM_BEGIN in system and SYSTEM_END in system
    assert "formulas define how dstack creates and reviews new work" in system.casefold()
    assert "dstack ctl" in system


def test_install_skills_is_idempotent_and_preserves_unrelated_system_prompt(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    agent.mkdir(parents=True)
    system = agent / "APPEND_SYSTEM.md"
    system.write_text("User-owned instruction.\n")

    install_skills(agent)
    first = system.read_text()
    install_skills(agent)
    second = system.read_text()

    assert second == first
    assert second.count(SYSTEM_BEGIN) == 1
    assert second.count(SYSTEM_END) == 1
    assert "User-owned instruction." in second


@pytest.mark.parametrize("managed", ["prompt", "system"])
def test_install_skills_rejects_symlinked_managed_destinations(tmp_path: Path, managed: str) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("keep me\n")
    if managed == "prompt":
        destination = agent / "prompts/plan-feature.md"
        destination.parent.mkdir()
    else:
        destination = agent / "APPEND_SYSTEM.md"
    destination.symlink_to(outside)

    with pytest.raises(DstackError, match="symlink"):
        install_skills(agent)

    assert outside.read_text() == "keep me\n"


def test_install_skills_rejects_duplicate_managed_system_blocks(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    system = agent / "APPEND_SYSTEM.md"
    original = f"{SYSTEM_BEGIN}\none\n{SYSTEM_END}\n{SYSTEM_BEGIN}\ntwo\n{SYSTEM_END}\n"
    system.write_text(original)

    with pytest.raises(DstackError, match="exactly one"):
        install_skills(agent)

    assert system.read_text() == original


def test_install_skills_preserves_unmarked_stale_core_skill(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    stale = agent / "skills/dstack-beads-core"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("legacy dStack core")

    install_skills(agent)

    assert stale.exists()


def test_install_skills_removes_only_owned_legacy_dstack_resources(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    stale = agent / "skills/start-feature"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("---\nname: start-feature\ndstack-managed: true\n---\nOld dStack workflow\n")
    unrelated = agent / "skills/setup-project"
    unrelated.mkdir(parents=True)
    (unrelated / "SKILL.md").write_text("---\nname: setup-project\n---\nUnrelated setup helper\n")
    stale_prompt = agent / "prompts/setup-project.md"
    stale_prompt.parent.mkdir(parents=True)
    stale_prompt.write_text(
        "---\nname: setup-project\ndstack-managed: true\n---\nLoad the old dStack setup workflow.\n"
    )
    stale_adopt = agent / "skills/dstack-beads-adopt-feature"
    stale_adopt.mkdir(parents=True)
    (stale_adopt / "SKILL.md").write_text(
        "---\nname: dstack-beads-adopt-feature\ndstack-managed: true\n---\nOld adoption workflow\n"
    )
    stale_adopt_prompt = agent / "prompts/adopt-feature.md"
    stale_adopt_prompt.write_text(
        "---\nname: adopt-feature\ndstack-managed: true\n---\nLoad the old adoption workflow.\n"
    )
    stale_alignment = agent / "skills/dstack-beads-project-alignment-review"
    stale_alignment.mkdir(parents=True)
    (stale_alignment / "SKILL.md").write_text(
        "---\nname: dstack-beads-project-alignment-review\ndstack-managed: true\n---\nOld alignment workflow\n"
    )
    stale_alignment_prompt = agent / "prompts/project-alignment-review.md"
    stale_alignment_prompt.write_text(
        "---\nname: project-alignment-review\ndstack-managed: true\n---\nOld alignment prompt\n"
    )

    payload = install_skills(agent)

    assert not stale.exists()
    assert unrelated.exists()
    assert not stale_prompt.exists()
    assert not stale_adopt.exists()
    assert not stale_adopt_prompt.exists()
    assert not stale_alignment.exists()
    assert not stale_alignment_prompt.exists()
    assert "skills/start-feature" in payload["removed_stale"]
    assert "skills/dstack-beads-adopt-feature" in payload["removed_stale"]
    assert "prompts/setup-project.md" in payload["removed_stale"]
    assert "prompts/adopt-feature.md" in payload["removed_stale"]
    assert "skills/dstack-beads-project-alignment-review" in payload["removed_stale"]
    assert "prompts/project-alignment-review.md" in payload["removed_stale"]


def test_default_agent_dir_honors_environment(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "pi-agent"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(configured))
    assert default_agent_dir() == configured


def test_installer_filesystem_error_uses_json_contract(tmp_path: Path, capsys) -> None:
    target = tmp_path / "not-a-directory"
    target.write_text("occupied\n")

    assert dstack_installer.main(["--agent-dir", str(target)]) == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "error"
    assert "cannot install dStack agent resources" in payload["error"]


def test_install_skills_rejects_symlinked_agent_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside-agent"
    outside.mkdir()
    agent = tmp_path / "agent"
    agent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(DstackError, match="symlink"):
        install_skills(agent)

    assert list(outside.iterdir()) == []
