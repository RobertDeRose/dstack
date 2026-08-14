"""Behavior tests for the optional Pi reviewer asset installer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from tests.support import run_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = REPOSITORY_ROOT / "skills/dstack-core/scripts/sync-pi-reviewers.py"
ASSET_ROOT = REPOSITORY_ROOT / "skills/dstack-core/assets/pi-reviewers"
AGENT_NAMES = {
    "dstack-clarity-reviewer",
    "dstack-readiness-reviewer",
    "dstack-task-reviewer",
    "dstack-implementation-reviewer",
    "dstack-delivery-integrity-reviewer",
}
REMOVED_AGENT_NAMES = {
    "dstack-context-builder",
    "dstack-architecture-reviewer",
    "dstack-simplicity-reviewer",
    "dstack-documentation-reviewer",
    "dstack-execution-reviewer",
    "dstack-delivery-reviewer",
    "dstack-drift-reviewer",
    "dstack-holistic-reviewer",
}
ROLE_REVIEWERS = AGENT_NAMES
MANIFEST_NAME = ".dstack-pi-reviewers.json"
RUNTIME_BUDGET = {"timeoutMs": 600000}


def load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_pi_reviewers", SYNC_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_frontmatter(path: Path) -> dict[str, str | bool | int]:
    text = path.read_text(encoding="utf-8")
    block = text.split("---\n", 2)[1]
    fields: dict[str, str | bool | int] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = raw.strip()
        if value in {"true", "false"}:
            fields[key] = value == "true"
        elif key == "timeoutMs" and value.isdigit():
            fields[key] = int(value)
        else:
            fields[key] = value
    return fields


def test_pi_reviewer_assets_enforce_runtime_budget_and_partial_report_policy() -> None:
    for name in AGENT_NAMES:
        fields = parse_frontmatter(ASSET_ROOT / f"{name}.md")
        assert {key: fields.get(key) for key in RUNTIME_BUDGET} == RUNTIME_BUDGET


def test_role_reviewer_capabilities_disable_ambient_context_and_execution() -> None:
    expected = {
        "systemPromptMode": "replace",
        "inheritProjectContext": False,
        "inheritSkills": False,
        "extensions": "",
        "defaultContext": "fresh",
        "acceptanceRole": "read-only",
        "tools": "read,grep,find,ls",
    }
    for name in ROLE_REVIEWERS:
        fields = parse_frontmatter(ASSET_ROOT / f"{name}.md")
        assert {key: fields.get(key) for key in expected} == expected


def test_role_reviewer_obsolete_assets_are_removed() -> None:
    for name in REMOVED_AGENT_NAMES:
        assert not (ASSET_ROOT / f"{name}.md").exists()


def test_close_roles_have_disjoint_direct_review_purposes() -> None:
    implementation = (ASSET_ROOT / "dstack-implementation-reviewer.md").read_text(encoding="utf-8")
    delivery = (ASSET_ROOT / "dstack-delivery-integrity-reviewer.md").read_text(encoding="utf-8")
    assert "correct code behavior, quality and simplicity, security, maintainability" in " ".join(
        implementation.split()
    )
    assert (
        "documentation, validation evidence, Beads state, implemented record, roadmap/navigation, delivery claims, and "
        "drift" in " ".join(delivery.split())
    )
    assert "do not own delivery documentation" in implementation.casefold()
    assert "do not duplicate implementation-integrity review" in delivery.casefold()


@pytest.mark.parametrize("override", ["flags: --approve --tools bash,write", "task-expansion: shell"])
def test_role_reviewer_sync_rejects_isolation_overrides(tmp_path: Path, override: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = copied_assets(tmp_path, override.split(":", 1)[0])
    target = source / "dstack-task-reviewer.md"
    text = target.read_text(encoding="utf-8")
    target.write_text(
        text.replace("tools: read,grep,find,ls", f"tools: read,grep,find,ls\n{override}"), encoding="utf-8"
    )

    result = run_sync(project, "--target", "project", source=source, expected=1)

    assert result["status"] == "error"
    assert "unexpected frontmatter fields" in str(result["error"])
    assert not (project / ".pi/agents").exists()


def copied_assets(tmp_path: Path, name: str) -> Path:
    source = tmp_path / name
    source.mkdir()
    for asset in ASSET_ROOT.glob("*.md"):
        (source / asset.name).write_bytes(asset.read_bytes())
    return source


def test_pi_reviewer_sync_rejects_missing_or_malformed_runtime_budget(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for field, bad_value in (("timeoutMs", "0"), ("timeoutMs", "five")):
        source = copied_assets(tmp_path, f"{field}-{bad_value}")
        target = source / "dstack-task-reviewer.md"
        text = target.read_text(encoding="utf-8")
        text = text.replace(f"{field}: {RUNTIME_BUDGET[field]}", f"{field}: {bad_value}")
        target.write_text(text, encoding="utf-8")
        result = run_sync(project, "--target", "project", source=source, expected=1)
        assert result["status"] == "error"


@pytest.mark.parametrize("bad_line", [" timeoutMs: 600000", "timeoutMs : 600000"])
def test_pi_reviewer_sync_rejects_noncanonical_budget_keys(tmp_path: Path, bad_line: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = copied_assets(tmp_path, bad_line.replace(" ", "-").replace(":", ""))
    target = source / "dstack-task-reviewer.md"
    text = target.read_text(encoding="utf-8").replace("timeoutMs: 600000", bad_line)
    target.write_text(text, encoding="utf-8")

    result = run_sync(project, "--target", "project", source=source, expected=1)

    assert result["status"] == "error"
    assert "noncanonical frontmatter" in str(result["error"])


@pytest.mark.parametrize("field", ["timeoutMs"])
def test_pi_reviewer_sync_rejects_duplicate_budget_keys(tmp_path: Path, field: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = copied_assets(tmp_path, f"duplicate-{field}")
    target = source / "dstack-task-reviewer.md"
    text = target.read_text(encoding="utf-8")
    existing = f"{field}: {RUNTIME_BUDGET[field]}"
    target.write_text(text.replace(existing, f"{existing}\n{field}: 1", 1), encoding="utf-8")

    result = run_sync(project, "--target", "project", source=source, expected=1)

    assert result["status"] == "error"
    assert "repeats frontmatter key" in str(result["error"])


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
    assert manifest["source_version"] == installed["source_version"]
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
def test_pi_reviewer_sync_removes_unchanged_obsolete_managed_assets(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / ".pi/agents"
    target.mkdir(parents=True)
    obsolete = target / "dstack-context-builder.md"
    obsolete.write_text("obsolete owned definition\n", encoding="utf-8")
    digest = hashlib.sha256(obsolete.read_bytes()).hexdigest()
    manifest = {
        "schema": "dstack.pi-reviewer-install.v1",
        "roster_schema": "dstack.pi-reviewer-roster.v1",
        "source_skill": "dstack-core",
        "source_version": "old",
        "files": {obsolete.name: {"sha256": digest, "managed": True}},
    }
    (target / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    result = run_sync(project, "--target", "project")

    assert result["status"] == "ok"
    assert result["removed"] == ["dstack-context-builder"]
    assert not obsolete.exists()
    assert set(path.stem for path in target.glob("dstack-*.md")) == AGENT_NAMES


def test_pi_reviewer_sync_rolls_back_files_when_manifest_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_sync_module()
    target = tmp_path / "agents"
    target.mkdir()
    task = target / "dstack-task-reviewer.md"
    obsolete = target / "dstack-context-builder.md"
    task.write_text("old task definition\n", encoding="utf-8")
    obsolete.write_text("old context builder\n", encoding="utf-8")
    manifest = {
        "schema": "dstack.pi-reviewer-install.v1",
        "roster_schema": "dstack.pi-reviewer-roster.v1",
        "source_skill": "dstack-core",
        "source_version": "old",
        "files": {
            path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "managed": True}
            for path in (task, obsolete)
        },
    }
    manifest_path = target / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    original_manifest = manifest_path.read_bytes()
    monkeypatch.setattr(module, "_write_manifest", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError, match="disk full"):
        module._sync(ASSET_ROOT, target, check=False, remove=False)

    assert task.read_text(encoding="utf-8") == "old task definition\n"
    assert obsolete.read_text(encoding="utf-8") == "old context builder\n"
    assert manifest_path.read_bytes() == original_manifest
    assert set(path.name for path in target.glob("*.md")) == {task.name, obsolete.name}


@pytest.mark.integration
def test_pi_reviewer_sync_preserves_arbitrary_manifest_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / ".pi/agents"
    target.mkdir(parents=True)
    unrelated = target / "notes.md"
    unrelated.write_text("must remain\n", encoding="utf-8")
    digest = hashlib.sha256(unrelated.read_bytes()).hexdigest()
    manifest = {
        "schema": "dstack.pi-reviewer-install.v1",
        "roster_schema": "dstack.pi-reviewer-roster.v1",
        "source_skill": "dstack-core",
        "source_version": "old",
        "files": {unrelated.name: {"sha256": digest, "managed": True}},
    }
    (target / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    result = run_sync(project, "--target", "project")

    assert result["status"] == "ok"
    assert result["removed"] == []
    assert unrelated.read_text(encoding="utf-8") == "must remain\n"


@pytest.mark.integration
def test_pi_reviewer_sync_preserves_modified_or_unowned_obsolete_assets(tmp_path: Path) -> None:
    for managed in (True, False):
        project = tmp_path / str(managed)
        target = project / ".pi/agents"
        target.mkdir(parents=True)
        obsolete = target / "dstack-context-builder.md"
        obsolete.write_text("current user bytes\n", encoding="utf-8")
        manifest = {
            "schema": "dstack.pi-reviewer-install.v1",
            "roster_schema": "dstack.pi-reviewer-roster.v1",
            "source_skill": "dstack-core",
            "source_version": "old",
            "files": {obsolete.name: {"sha256": "0" * 64, "managed": managed}},
        }
        (target / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

        result = run_sync(project, "--target", "project", expected=2 if managed else 0)

        assert obsolete.read_text(encoding="utf-8") == "current user bytes\n"
        assert result["status"] == ("conflict" if managed else "ok")


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
        changed.read_text(encoding="utf-8").replace(
            "one bounded dstack task", "one bounded dstack implementation task"
        ),
        encoding="utf-8",
    )

    result = run_sync(project, "--target", "project", source=source)

    assert result["status"] == "ok"
    assert result["updated"] == ["dstack-task-reviewer"]
    assert "bounded dstack implementation task" in (project / ".pi/agents/dstack-task-reviewer.md").read_text(
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
    assert not (target / "dstack-clarity-reviewer.md").exists()
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
    assert not (target / "dstack-clarity-reviewer.md").exists()


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
