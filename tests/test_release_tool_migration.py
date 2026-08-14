"""Release-authority reconciliation tests for legacy workflow migration."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = REPOSITORY_ROOT / "skills/migrate-workflow/scripts/migration_core.py"


def load_core() -> ModuleType:
    directory = str(CORE_PATH.parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location("migration_core", CORE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_semantic_release_project(root: Path) -> None:
    (root / ".github/workflows").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".releaserc.json").write_text('{"branches":["main"]}\n', encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps({"devDependencies": {"semantic-release": "^24.0.0"}}), encoding="utf-8"
    )
    (root / "package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/semantic-release": {"version": "24.0.0"}}}), encoding="utf-8"
    )
    (root / ".github/workflows/release.yml").write_text("steps:\n  - run: npx semantic-release\n", encoding="utf-8")
    (root / "mise.toml").write_text('[tasks.release]\nrun = "npx semantic-release"\n', encoding="utf-8")
    (root / "docs/releasing.md").write_text("# Releasing\n\nRun semantic-release from CI.\n", encoding="utf-8")


def write_cog_project(root: Path) -> None:
    (root / "docs").mkdir(exist_ok=True)
    (root / "cog.toml").write_text("from_latest_tag = true\n", encoding="utf-8")
    (root / "mise.toml").write_text('[tools]\ncocogitto = "latest"\n', encoding="utf-8")
    (root / "mise.lock").write_text('[[tools.cocogitto]]\nversion = "6.3.0"\n', encoding="utf-8")
    (root / "docs/releasing.md").write_text("# Releasing\n\nUse Cog for releases.\n", encoding="utf-8")


def decision(action: str, tool: str, reason: str) -> dict[str, str]:
    return {
        "action": action,
        "tool": tool,
        "reason": reason,
        "recorded_at": "2026-08-14T00:00:00+00:00",
    }


def test_release_authority_scan_reports_paths_kinds_and_ownership(tmp_path: Path) -> None:
    core = load_core()
    write_semantic_release_project(tmp_path)
    write_cog_project(tmp_path)

    authorities = core.detect_release_authorities(tmp_path)

    assert {item["tool"] for item in authorities} == {"cog", "semantic-release"}
    assert {item["kind"] for item in authorities} >= {
        "config",
        "dependency",
        "workflow",
        "tooling",
        "lock",
        "documentation",
    }
    assert all(item["ownership"] == "project" for item in authorities)
    assert {item["path"] for item in authorities} >= {
        ".releaserc.json",
        "package.json",
        ".github/workflows/release.yml",
        "mise.toml",
        "docs/releasing.md",
        "cog.toml",
    }


def test_release_reconciliation_fails_closed_without_decision_or_on_contradiction(tmp_path: Path) -> None:
    core = load_core()
    write_semantic_release_project(tmp_path)
    write_cog_project(tmp_path)
    state = core.release_tooling_state(tmp_path, None)
    empty = tmp_path / "empty"
    empty.mkdir()
    empty_state = core.release_tooling_state(empty, None)

    assert {issue["kind"] for issue in state["issues"]} == {"contradictory_release_tools", "missing_release_decision"}
    assert {issue["kind"] for issue in empty_state["issues"]} == {"missing_release_decision"}
    with pytest.raises(core.MigrationError, match="Release tooling reconciliation"):
        core.require_release_tool_reconciliation({"release_tooling": state})
    stale_clear_state = {
        "decision": decision("convert", "cog", "Convert releases."),
        "authorities": [],
        "issues": [],
    }
    with pytest.raises(core.MigrationError, match="Release tooling reconciliation"):
        core.require_release_tool_reconciliation({"release_tooling": stale_clear_state}, root=tmp_path)


def test_release_reconciliation_accepts_converted_and_retained_projects(tmp_path: Path) -> None:
    core = load_core()
    converted = tmp_path / "converted"
    retained = tmp_path / "retained"
    removed = tmp_path / "removed"
    converted.mkdir()
    retained.mkdir()
    removed.mkdir()
    write_cog_project(converted)
    write_semantic_release_project(retained)
    write_semantic_release_project(removed)

    converted_decision = decision("convert", "cog", "Convert release automation and documentation.")
    retained_decision = decision("retain", "semantic-release", "Keep the existing project-owned release process.")
    removal_decision = decision("remove", "semantic-release", "Remove legacy release automation.")
    converted_state = core.release_tooling_state(converted, converted_decision)
    retained_state = core.release_tooling_state(retained, retained_decision)
    blocked_removal = core.release_tooling_state(removed, removal_decision)
    assert any(issue["kind"] == "release_tool_removal_incomplete" for issue in blocked_removal["issues"])
    shutil.rmtree(removed)
    removed.mkdir()
    write_cog_project(removed)
    removed_state = core.release_tooling_state(removed, removal_decision)

    assert converted_state["issues"] == []
    assert retained_state["issues"] == []
    assert removed_state["issues"] == []
    core.require_release_tool_reconciliation({"release_tooling": converted_state})
    core.require_release_tool_reconciliation({"release_tooling": retained_state})
    core.require_release_tool_reconciliation({"release_tooling": removed_state})

    (converted / "docs/releasing.md").unlink()
    (retained / "docs/releasing.md").unlink()
    assert any(
        issue["kind"] == "release_conversion_incomplete"
        for issue in core.release_tooling_state(converted, converted_decision)["issues"]
    )
    assert any(
        issue["kind"] == "retained_release_tool_conflict"
        for issue in core.release_tooling_state(retained, retained_decision)["issues"]
    )


def test_release_decision_validation_requires_timestamp_and_finds_package_scripts(tmp_path: Path) -> None:
    core = load_core()
    write_semantic_release_project(tmp_path)
    package = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    package.pop("devDependencies")
    package["scripts"] = {"release": "npx semantic-release"}
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")
    (tmp_path / ".releaserc.json").unlink()
    (tmp_path / "package-lock.json").unlink()
    (tmp_path / ".github/workflows/release.yml").unlink()
    (tmp_path / "mise.toml").unlink()

    valid = decision("retain", "semantic-release", "Keep package release script.")
    assert core.release_tooling_state(tmp_path, valid)["issues"] == []
    assert any(item["kind"] == "package-script" for item in core.detect_release_authorities(tmp_path))
    for bad_timestamp in (None, "not-a-timestamp", "2026-08-14T00:00:00"):
        invalid = {**valid, "recorded_at": bad_timestamp}
        assert any(
            issue["kind"] == "invalid_release_decision"
            for issue in core.release_tooling_state(tmp_path, invalid)["issues"]
        )


def test_release_decision_is_durable_and_retains_detection_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = load_core()
    write_semantic_release_project(tmp_path)
    manifest: dict[str, object] = {}
    saved: list[dict[str, object]] = []
    monkeypatch.setattr(core, "save_manifest_and_report", lambda _root, _manifest, _report, value: saved.append(value))

    core.set_release_tool_decision(
        tmp_path,
        manifest,
        manifest_path=Path("migration/workflow-migration.json"),
        report_path=Path("migration/workflow-migration.md"),
        action="retain",
        tool="semantic-release",
        reason="Keep the existing release workflow.",
    )

    state = cast(dict[str, Any], manifest["release_tooling"])
    assert state["decision"]["action"] == "retain"
    assert state["decision"]["recorded_at"]
    assert state["issues"] == []
    assert saved == [manifest]


def test_manifest_scan_preserves_release_decision_and_refreshes_evidence(tmp_path: Path) -> None:
    core = load_core()
    write_semantic_release_project(tmp_path)
    (tmp_path / "migration").mkdir()
    manifest_path = Path("migration/workflow-migration.json")

    first = core.build_manifest(tmp_path, manifest_path=manifest_path)
    assert any(item["kind"] == "missing_release_decision" for item in first["release_tooling"]["issues"])
    first["release_tooling"]["decision"] = {
        "action": "retain",
        "tool": "semantic-release",
        "reason": "Keep existing release automation.",
        "recorded_at": "2026-08-14T00:00:00+00:00",
    }
    core.dump_json(tmp_path / manifest_path, first)

    rescanned = core.build_manifest(tmp_path, manifest_path=manifest_path)

    assert rescanned["release_tooling"]["decision"] == first["release_tooling"]["decision"]
    assert rescanned["release_tooling"]["issues"] == []
    assert {item["path"] for item in rescanned["release_tooling"]["authorities"]} >= {
        ".releaserc.json",
        "package.json",
    }


def test_generated_cog_project_rejects_unresolved_legacy_release_authority(tmp_path: Path) -> None:
    core = load_core()
    write_semantic_release_project(tmp_path)
    template = REPOSITORY_ROOT / "skills/setup-project/template"
    (tmp_path / "cog.toml").write_bytes((template / "cog.toml").read_bytes())
    (tmp_path / "mise.toml").write_bytes((template / "mise.toml.jinja").read_bytes())

    state = core.release_tooling_state(tmp_path, None)

    assert {item["tool"] for item in state["authorities"]} == {"cog", "semantic-release"}
    assert any(item["kind"] == "contradictory_release_tools" for item in state["issues"])
