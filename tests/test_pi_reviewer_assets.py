"""Behavior tests for the optional Pi reviewer asset installer."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

import pytest

from tests.support import run_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = REPOSITORY_ROOT / "skills/dstack-core/scripts/sync-pi-reviewers.py"
ASSET_ROOT = REPOSITORY_ROOT / "skills/dstack-core/assets/pi-reviewers"
AGENT_NAMES = {
    "dstack-context-builder",
    "dstack-architecture-reviewer",
    "dstack-simplicity-reviewer",
    "dstack-documentation-reviewer",
    "dstack-execution-reviewer",
    "dstack-task-reviewer",
    "dstack-delivery-reviewer",
    "dstack-drift-reviewer",
}
MANIFEST_NAME = ".dstack-pi-reviewers.json"


def string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload[key]
    assert isinstance(value, list)
    return cast(list[str], value)


def run_sync(
    project: Path,
    *arguments: str,
    source: Path = ASSET_ROOT,
    env: dict[str, str] | None = None,
    expected: int = 0,
) -> dict[str, object]:
    result = run_command(
        [
            "python3",
            str(SYNC_SCRIPT),
            "--project-root",
            str(project),
            "--source",
            str(source),
            *arguments,
            "--json",
        ],
        cwd=REPOSITORY_ROOT,
        env=None if env is None else {**os.environ, **env},
        expected=expected,
    )
    return json.loads(result.stdout)


@pytest.mark.integration
def test_pi_reviewer_sync_installs_and_discovers_project_roster(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    installed = run_sync(project, "--target", "project")

    assert installed["status"] == "ok"
    assert set(string_list(installed, "installed")) == AGENT_NAMES
    target = project / ".pi/agents"
    assert set(path.stem for path in target.glob("dstack-*.md")) == AGENT_NAMES
    manifest = json.loads((target / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["schema"] == "dstack.pi-reviewer-install.v1"
    assert manifest["source_version"] == "0.8.9"
    assert manifest["files"]["dstack-task-reviewer.md"]["managed"] is True
    assert set(string_list(installed, "discovered")) == AGENT_NAMES

    unchanged = run_sync(project, "--target", "project")

    assert unchanged["status"] == "ok"
    assert unchanged["installed"] == []
    assert set(string_list(unchanged, "unchanged")) == AGENT_NAMES


@pytest.mark.integration
def test_pi_reviewer_sync_supports_an_explicit_agent_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = tmp_path / "selected-agents"
    project.mkdir()

    result = run_sync(project, "--target", str(target))

    assert result["status"] == "ok"
    assert (target / MANIFEST_NAME).is_file()
    assert set(string_list(result, "discovered")) == AGENT_NAMES


@pytest.mark.integration
def test_pi_reviewer_sync_check_is_read_only_and_validates_contract(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    missing = run_sync(project, "--target", "project", "--check", expected=1)

    assert missing["status"] == "missing"
    assert not (project / ".pi/agents").exists()

    run_sync(project, "--target", "project")
    checked = run_sync(project, "--target", "project", "--check")

    assert checked["status"] == "ok"
    assert checked["conflicts"] == []
    assert set(string_list(checked, "discovered")) == AGENT_NAMES


@pytest.mark.integration
def test_pi_reviewer_sync_does_not_overwrite_conflicting_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / ".pi/agents"
    target.mkdir(parents=True)
    conflict = target / "dstack-task-reviewer.md"
    conflict.write_text("user-authored definition\n", encoding="utf-8")

    result = run_sync(project, "--target", "project", expected=2)

    assert result["status"] == "conflict"
    assert result["conflicts"] == ["dstack-task-reviewer.md"]
    assert conflict.read_text(encoding="utf-8") == "user-authored definition\n"
    assert not (target / MANIFEST_NAME).exists()
    assert list(target.glob("dstack-*.md")) == [conflict]


@pytest.mark.integration
def test_pi_reviewer_sync_updates_unchanged_owned_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "assets"
    source.mkdir()
    for asset in ASSET_ROOT.glob("*.md"):
        (source / asset.name).write_bytes(asset.read_bytes())
    run_sync(project, "--target", "project", source=source)
    changed = source / "dstack-task-reviewer.md"
    changed.write_text(
        changed.read_text(encoding="utf-8").replace("one dstack implementation", "one bounded dstack implementation"),
        encoding="utf-8",
    )

    result = run_sync(project, "--target", "project", source=source)

    assert result["status"] == "ok"
    assert result["updated"] == ["dstack-task-reviewer"]
    assert "bounded dstack implementation" in (project / ".pi/agents/dstack-task-reviewer.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.integration
def test_pi_reviewer_sync_rejects_corrupt_manifest_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    run_sync(project, "--target", "project")
    manifest_path = project / ".pi/agents" / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_skill"] = "user-authored"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_sync(project, "--target", "project", "--check", expected=1)

    assert result["status"] == "error"


@pytest.mark.integration
def test_pi_reviewer_remove_rejects_manifest_path_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    run_sync(project, "--target", "project")
    outside = tmp_path / "outside.txt"
    outside.write_text("must remain\n", encoding="utf-8")
    manifest_path = project / ".pi/agents" / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["files"].pop("dstack-task-reviewer.md")
    manifest["files"]["../../outside.txt"] = entry
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_sync(project, "--target", "project", "--remove", expected=1)

    assert result["status"] == "error"
    assert outside.read_text(encoding="utf-8") == "must remain\n"


@pytest.mark.integration
def test_pi_reviewer_remove_preserves_modified_files_and_removes_owned_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    run_sync(project, "--target", "project")
    target = project / ".pi/agents"
    modified = target / "dstack-task-reviewer.md"
    modified.write_text(modified.read_text(encoding="utf-8") + "\nlocal change\n", encoding="utf-8")

    result = run_sync(project, "--target", "project", "--remove", expected=2)

    assert result["status"] == "conflict"
    assert result["conflicts"] == ["dstack-task-reviewer.md"]
    assert modified.exists()
    assert not (target / "dstack-context-builder.md").exists()
    assert (target / MANIFEST_NAME).exists()


@pytest.mark.integration
def test_pi_reviewer_sync_contract_is_documented_in_canonical_and_generated_guidance() -> None:
    roster = (REPOSITORY_ROOT / "skills/dstack-core/references/PI-REVIEWER-ROSTER.md").read_text(encoding="utf-8")
    root_guidance = (REPOSITORY_ROOT / "docs/src/development/feature-lifecycle.md").read_text(encoding="utf-8")
    template_guidance = (
        REPOSITORY_ROOT / "skills/setup-project/template/docs/src/development/feature-lifecycle.md.jinja"
    ).read_text(encoding="utf-8")

    for text in (roster, root_guidance, template_guidance):
        normalized = " ".join(text.casefold().split())
        assert "sync-pi-reviewers.py" in text or "explicit project-local sync" in text
        assert "no silent role substitution" in normalized
    assert "dstack.pi-reviewer-install.v1" in roster
    assert "PI_CODING_AGENT_DIR/agents" in roster
    assert "--remove" in roster


@pytest.mark.integration
def test_pi_reviewer_sync_rejects_dangling_agent_symlink(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / ".pi/agents"
    target.mkdir(parents=True)
    dangling = target / "dstack-task-reviewer.md"
    dangling.symlink_to(tmp_path / "missing-agent.md")

    result = run_sync(project, "--target", "project", expected=2)

    assert result["status"] == "conflict"
    assert dangling.is_symlink()
    assert not (target / MANIFEST_NAME).exists()


@pytest.mark.integration
def test_pi_reviewer_remove_preserves_dangling_owned_symlink(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    run_sync(project, "--target", "project")
    target = project / ".pi/agents"
    linked = target / "dstack-task-reviewer.md"
    linked.unlink()
    linked.symlink_to(tmp_path / "missing-agent.md")

    result = run_sync(project, "--target", "project", "--remove", expected=2)

    assert result["status"] == "conflict"
    assert linked.is_symlink()
    assert not (target / "dstack-context-builder.md").exists()


@pytest.mark.integration
def test_pi_reviewer_sync_rejects_dangling_manifest_symlink(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / ".pi/agents"
    target.mkdir(parents=True)
    manifest = target / MANIFEST_NAME
    manifest.symlink_to(tmp_path / "missing-manifest.json")

    result = run_sync(project, "--target", "project", expected=2)

    assert result["status"] == "conflict"
    assert manifest.is_symlink()


def test_pi_reviewer_sync_rejects_symlinked_project_agent_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".pi").symlink_to(outside, target_is_directory=True)

    result = run_sync(project, "--target", "project", expected=1)

    assert result["status"] == "error"
    assert list(outside.iterdir()) == []


@pytest.mark.integration
def test_pi_reviewer_global_target_treats_empty_environment_as_unset(tmp_path: Path) -> None:
    project = tmp_path / "project"
    fake_home = tmp_path / "home"
    project.mkdir()
    fake_home.mkdir()

    result = run_sync(
        project,
        "--target",
        "global",
        "--check",
        env={"PI_CODING_AGENT_DIR": "", "HOME": str(fake_home)},
        expected=1,
    )

    assert result["status"] == "missing"
    assert result["target"] == str(fake_home / ".pi/agent/agents")
