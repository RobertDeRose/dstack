"""Filesystem preparation operations for legacy workflow migration."""

# ruff: noqa: S607

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from migration_core import (
    _apply_literal_replacements,
    _compile_literal_replacements,
    _feature_path_replacements,
    delivered_navigation,
    ensure_feature_index_markers,
    ensure_feature_lifecycle_link,
    ensure_summary_concerns,
    ensure_summary_markers,
    FEATURE_INDEX_PATH,
    FEATURES_PATH,
    MARKER_END,
    MARKER_START,
    MIGRATION_MARKER,
    MigrationError,
    read_text,
    replace_marker_body,
    rewrite_roadmap_headings,
    ROADMAP_PATH,
    SUMMARY_PATH,
    utc_now,
    write_text,
)


def assert_clean_worktree(root: Path, *, allow_dirty: bool) -> None:
    if allow_dirty or not (root / ".git").exists():
        return
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        msg = "The working tree is not clean. Commit/stash changes or pass --allow-dirty after reviewing the risk."
        raise MigrationError(msg)


def prepare_filesystem(
    root: Path,
    manifest: dict[str, Any],
    *,
    apply: bool,
    allow_dirty: bool,
) -> None:
    assert_clean_worktree(root, allow_dirty=allow_dirty)
    mapping = {Path(feature["source_dir"]).name: feature["slug"] for feature in manifest["features"]}
    operations: list[str] = []
    for feature in manifest["features"]:
        source = root / feature["source_dir"]
        target = root / feature["target_dir"]
        if source == target or not source.exists():
            continue
        if target.exists():
            msg = f"Target feature directory already exists: {target.relative_to(root)}"
            raise MigrationError(msg)
        operations.append(f"rename {source.relative_to(root)} -> {target.relative_to(root)}")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)

    docs_src = root / "docs/src"
    changed_files: list[Path] = []
    feature_index_path = root / FEATURE_INDEX_PATH
    if not feature_index_path.exists():
        operations.append(f"create {feature_index_path.relative_to(root)}")
        if apply:
            write_text(
                feature_index_path,
                "# Implemented features\n\n" + MARKER_START + "\n" + MARKER_END,
            )
    compiled_feature_paths = {
        rewrite_sibling_links: _compile_literal_replacements(
            _feature_path_replacements(mapping, rewrite_sibling_links=rewrite_sibling_links)
        )
        for rewrite_sibling_links in (False, True)
    }
    if docs_src.exists():
        for path in sorted(docs_src.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".toml", ".json", ".yaml", ".yml"}:
                continue
            old = read_text(path)
            new = _apply_literal_replacements(
                old,
                compiled_feature_paths[path.is_relative_to(root / FEATURES_PATH)],
            )
            if path == root / ROADMAP_PATH:
                new = rewrite_roadmap_headings(
                    new,
                    {feature["slug"]: {"title": feature["title"]} for feature in manifest["features"]},
                )
            if (
                path.name in {"design.md", "index.md"}
                and path.parent.parent == root / FEATURES_PATH
                and path.parent.name in set(mapping.values())
                and MIGRATION_MARKER not in new
            ):
                new = MIGRATION_MARKER + "\n\n" + new.lstrip()
            if path == root / SUMMARY_PATH:
                new, concern_pages = ensure_summary_concerns(root, new, apply=apply)
                for concern_page in concern_pages:
                    operations.append(f"create {concern_page.relative_to(root)}")
                new = ensure_summary_markers(new)
                summary_entries, _ = delivered_navigation(manifest)
                new = replace_marker_body(new, summary_entries, indent="  ")
                if (root / "docs/src/development/feature-lifecycle.md").exists():
                    new = ensure_feature_lifecycle_link(new)
            if path == root / FEATURE_INDEX_PATH:
                new = ensure_feature_index_markers(new)
                _, feature_entries = delivered_navigation(manifest)
                new = replace_marker_body(new, feature_entries)
            if new != old:
                operations.append(f"rewrite {path.relative_to(root)}")
                changed_files.append(path)
                if apply:
                    write_text(path, new)

    if not apply:
        print("Filesystem preparation dry-run:")
        for operation in operations:
            print("  -", operation)
        if not operations:
            print("  - no filesystem changes required")
        return

    manifest["migration_prepared"] = True
    manifest["prepared_at"] = utc_now()
    for feature in manifest["features"]:
        feature["source_dir"] = feature["target_dir"]
        feature["has_design"] = (root / feature["design_path"]).exists()
        feature["has_tasks"] = (root / feature["legacy_tasks_path"]).exists()
        feature["has_index"] = (root / feature["implemented_path"]).exists()
    print(f"Renamed/reconciled {len(operations)} filesystem items.")
