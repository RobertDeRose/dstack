"""Migration inventory, graph, and documentation verification."""

# ruff: noqa: S603, S607

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from migration_beads import (
    bd_feature_relationship_graph,
    reconcile_existing_beads_state,
    run_command,
)
from migration_core import (
    _compile_literal_replacements,
    archived_task_identity,
    BEADS_TRACKED_CONTROL_PATHS,
    beads_traversal_cycles,
    capture_hk_inventory,
    DEFAULT_BASELINE_JSON,
    DEFAULT_BASELINE_REPORT,
    DEFAULT_MANIFEST,
    DEFAULT_REPORT,
    DEFAULT_TASK_ARCHIVE,
    DOCS_CHECKER_PATH,
    existing_feature_dirs,
    FEATURES_PATH,
    graph_cycles,
    hk_reconciliation_state,
    MigrationError,
    parse_roadmap,
    read_text,
    release_tooling_state,
    render_relationship_cycle,
    render_typed_cycle,
    ROADMAP_PATH,
    SESSION_AUTHORITY_PATH,
    task_references,
    TEMPLATE_BACKUP_DIR,
    TEMPLATE_CANDIDATE_DIR,
)
from migration_git import (
    git_repository,
    safe_repository_path,
)


def finalized_inventory_errors(root: Path, manifest: Mapping[str, Any]) -> list[str]:
    roadmap_entries, _ = parse_roadmap(root / ROADMAP_PATH)
    directories = existing_feature_dirs(root / FEATURES_PATH)
    stored = {
        str(feature.get("slug")): feature
        for feature in manifest.get("features", [])
        if isinstance(feature, dict) and feature.get("slug")
    }
    current_slugs = {entry.slug for entry in roadmap_entries} | set(directories)
    errors: list[str] = []
    added = sorted(current_slugs - set(stored))
    omitted = sorted(set(stored) - current_slugs)
    if added:
        errors.append("Finalized migration inventory has unrecorded features: " + ", ".join(added))
    if omitted:
        errors.append("Finalized migration inventory no longer contains recorded features: " + ", ".join(omitted))
    authorized_archives: dict[str, str] = {}
    for slug, feature in stored.items():
        tasks_path = safe_repository_path(
            root,
            feature.get("legacy_tasks_path", ""),
            description=f"{slug}.legacy_tasks_path after finalization",
            required_prefix=PurePosixPath(FEATURES_PATH.as_posix()),
        )
        if tasks_path.exists():
            errors.append(f"Finalized migration has a reappearing legacy task file: {tasks_path.relative_to(root)}")
        if feature.get("has_design"):
            design_path = safe_repository_path(
                root,
                feature.get("design_path", ""),
                description=f"{slug}.design_path after finalization",
                required_prefix=PurePosixPath(FEATURES_PATH.as_posix()),
            )
            if not design_path.is_file():
                errors.append(f"Finalized migration design evidence is missing: {design_path.relative_to(root)}")
        archive = feature.get("legacy_tasks_archive")
        expected_digest = str(feature.get("legacy_tasks_archive_digest") or "")
        expected_identity = feature.get("legacy_tasks_archive_identity")
        if archive == "deleted; retained in Git history":
            if not expected_digest or not isinstance(expected_identity, list):
                errors.append(f"Finalized deleted task evidence lacks a sealed digest and identity: {slug}")
            continue
        if isinstance(archive, str) and archive:
            archive_path = safe_repository_path(
                root,
                archive,
                description=f"{slug}.legacy_tasks_archive after finalization",
                required_prefix=PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix()),
            )
            authorized_archives[archive] = expected_digest
            if not archive_path.is_file():
                errors.append(f"Finalized migration archive is missing: {archive_path.relative_to(root)}")
            elif not expected_digest:
                errors.append(f"Finalized migration archive lacks a sealed digest: {archive}")
            else:
                actual_digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
                if actual_digest != expected_digest:
                    errors.append(f"Finalized migration archive digest changed: {archive}")
                if archived_task_identity(archive_path) != expected_identity:
                    errors.append(f"Finalized migration archive task identity changed: {archive}")
    for raw_path, raw_digest in manifest.get("preexisting_legacy_task_archives", {}).items():
        archive_path = safe_repository_path(
            root,
            raw_path,
            description="preexisting legacy task archive",
            required_prefix=PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix()),
        )
        authorized_archives[str(raw_path)] = str(raw_digest)
        if not archive_path.is_file() or hashlib.sha256(archive_path.read_bytes()).hexdigest() != raw_digest:
            errors.append(f"Preexisting legacy task archive is missing or changed: {raw_path}")
    archive_root = root / DEFAULT_TASK_ARCHIVE
    current_archives = (
        {str(path.relative_to(root)) for path in archive_root.rglob("*") if path.is_file()}
        if archive_root.exists()
        else set()
    )
    unexpected_archives = sorted(current_archives - set(authorized_archives))
    missing_archives = sorted(set(authorized_archives) - current_archives)
    if unexpected_archives:
        errors.append("Finalized migration has unrecorded archive files: " + ", ".join(unexpected_archives))
    if missing_archives:
        errors.append("Finalized migration has missing authorized archive files: " + ", ".join(missing_archives))
    return errors


def finalized_checkpoint_errors(manifest: Mapping[str, Any]) -> list[str]:
    evidence = manifest.get("checkpoint_evidence")
    if not isinstance(evidence, list) or not evidence:
        return [
            "Finalized migration requires durable passed checkpoint evidence; record checkpoint-evidence before "
            "claiming completion"
        ]

    def nonempty_text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def valid_timestamp(value: Any) -> bool:
        if not nonempty_text(value):
            return False
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        return parsed.tzinfo is not None

    valid_passed = any(
        isinstance(item, Mapping)
        and item.get("status") == "passed"
        and nonempty_text(item.get("hook"))
        and nonempty_text(item.get("command"))
        and valid_timestamp(item.get("recorded_at"))
        for item in evidence
    )
    if not valid_passed:
        return [
            "Finalized migration requires at least one durable checkpoint evidence entry with status passed, "
            "hook, command, and recorded_at"
        ]
    return []


def verify_migration(root: Path, manifest: Mapping[str, Any], *, verify_beads: bool) -> tuple[list[str], list[str]]:
    errors = finalized_inventory_errors(root, manifest) if manifest.get("migration_finalized") else []
    recorded_release = manifest.get("release_tooling", {})
    decision = recorded_release.get("decision") if isinstance(recorded_release, Mapping) else None
    current_release = release_tooling_state(root, decision if isinstance(decision, Mapping) else None)
    errors.extend(
        f"Release tooling reconciliation blocked: {issue.get('kind')}: {issue.get('message')}"
        for issue in current_release.get("issues", [])
    )
    if manifest.get("migration_finalized"):
        errors.extend(finalized_checkpoint_errors(manifest))
    features = [feature for feature in manifest.get("features", []) if isinstance(feature, dict)]
    if verify_beads:
        try:
            reconcile_existing_beads_state(
                root,
                copy.deepcopy(features),
                canonicalize=False,
                allow_recovery=False,
            )
        except MigrationError as exc:
            errors.append(f"Cannot verify imported Beads ownership: {exc}")
    candidate_by_slug = {
        str(candidate.get("slug")): candidate
        for candidate in manifest.get("delivered_record_candidates", [])
        if isinstance(candidate, dict)
    }
    completed_slugs = {str(feature["slug"]) for feature in features if feature.get("classification") == "completed"}
    unreviewed_candidates = sorted(
        slug for slug in completed_slugs if not candidate_by_slug.get(slug, {}).get("reviewed")
    )
    if unreviewed_candidates:
        errors.append(
            "Delivered-record candidates require semantic review; completed features are missing reviewed semantic "
            "reconciliation: " + ", ".join(unreviewed_candidates)
        )
    summary_owners: dict[str, str] = {}
    summary_template_owners: dict[str, str] = {}
    evidence_owners: dict[tuple[str, ...], str] = {}
    feature_by_slug = {str(feature["slug"]): feature for feature in features}
    for candidate in manifest.get("delivered_record_candidates", []):
        if not candidate.get("reviewed"):
            continue
        slug = str(candidate.get("slug", ""))
        path = root / str(candidate.get("path", ""))
        if not path.is_file():
            if not manifest.get("migration_finalized"):
                errors.append(f"Reviewed delivered-record candidate is missing: {slug}")
                continue
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != candidate.get("evidence_digest"):
                errors.append(f"Reviewed delivered-record candidate changed after approval: {slug}")
        summary = " ".join(str(candidate.get("semantic_summary", "")).split()).casefold()
        if not summary or not candidate.get("semantic_evidence") or not candidate.get("semantic_commits"):
            errors.append(f"Reviewed semantic reconciliation lacks feature-specific evidence: {slug}")
        elif summary in summary_owners and summary_owners[summary] != slug:
            errors.append(f"Semantic reconciliation summary is reused by {summary_owners[summary]} and {slug}")
        else:
            summary_owners[summary] = slug
            feature = feature_by_slug.get(slug, {})
            summary_template = summary
            identities: set[str] = {slug.casefold(), str(feature.get("title", "")).casefold()}
            for identity in sorted(identities, key=lambda value: len(value), reverse=True):
                if identity:
                    summary_template = re.sub(re.escape(identity), "<feature>", summary_template, flags=re.IGNORECASE)
            previous = summary_template_owners.get(summary_template)
            if previous and previous != slug:
                errors.append(f"Semantic reconciliation template is reused by {previous} and {slug}")
            else:
                summary_template_owners[summary_template] = slug
        evidence_key = tuple(sorted(str(item.get("path", "")) for item in candidate.get("semantic_evidence", [])))
        previous_evidence_owner = evidence_owners.get(evidence_key)
        if evidence_key and previous_evidence_owner and previous_evidence_owner != slug:
            errors.append(f"Semantic evidence set is reused by {previous_evidence_owner} and {slug}")
        elif evidence_key:
            evidence_owners[evidence_key] = slug
        record_path = root / str(candidate.get("record_path", ""))
        if not record_path.is_file() or hashlib.sha256(record_path.read_bytes()).hexdigest() != candidate.get(
            "record_digest"
        ):
            errors.append(f"Reviewed implemented-feature record is missing or changed: {slug}")
        for evidence in candidate.get("semantic_evidence", []):
            evidence_path = root / str(evidence.get("path", ""))
            if not evidence_path.is_file() or hashlib.sha256(evidence_path.read_bytes()).hexdigest() != evidence.get(
                "sha256"
            ):
                errors.append(f"Semantic evidence is missing or changed for {slug}: {evidence.get('path')}")
        evidence_paths = {str(item.get("path", "")) for item in candidate.get("semantic_evidence", [])}
        corroborated_paths: set[str] = set()
        feature = feature_by_slug.get(slug, {})
        feature_prefixes = {
            str(feature.get("target_dir", "")).rstrip("/") + "/",
            str(feature.get("source_dir", "")).rstrip("/") + "/",
        }
        for commit in candidate.get("semantic_commits", []):
            commit_sha = str(commit.get("sha", ""))
            result = subprocess.run(
                ["git", "show", "--format=", "--name-only", commit_sha],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                errors.append(f"Semantic Git evidence is missing for {slug}: {commit_sha}")
                continue
            changed = {line for line in result.stdout.splitlines() if line.strip()}
            corroborated_paths.update(changed & evidence_paths)
            relevant = sorted(
                path
                for path in changed
                if path in evidence_paths
                or any(prefix != "/" and path.startswith(prefix) for prefix in feature_prefixes)
            )
            if relevant != sorted(str(path) for path in commit.get("paths", [])):
                errors.append(f"Semantic Git evidence paths changed or were fabricated for {slug}: {commit_sha}")
        missing_corroboration = sorted(evidence_paths - corroborated_paths)
        if missing_corroboration:
            errors.append(
                f"Semantic commits do not touch corroborating evidence for {slug}: " + ", ".join(missing_corroboration)
            )
    warnings: list[str] = []
    mapping = {Path(feature["source_dir"]).name: feature["slug"] for feature in features}
    stored_hk = manifest.get("hk_reconciliation", {})
    refreshed_hk = hk_reconciliation_state(
        stored_hk.get("baseline", {}),
        capture_hk_inventory(root),
        stored_hk.get("dispositions", []),
    )
    for issue in refreshed_hk.get("issues", []):
        location = "/".join(str(issue.get(key, "")) for key in ("hook", "step") if issue.get(key))
        errors.append(
            f"hk reconciliation {issue.get('kind', 'issue')}{f' at {location}' if location else ''}; "
            "restore the existing step or record an explicit reconcile-hk disposition"
        )
    artifacts = manifest.get("artifacts", {})
    candidate_dir = root / str(artifacts.get("candidate_directory", TEMPLATE_CANDIDATE_DIR))
    backup_dir = root / str(artifacts.get("backup_directory", TEMPLATE_BACKUP_DIR))
    backup_disposition = artifacts.get("backup_disposition", "unresolved" if backup_dir.exists() else "not_applicable")
    if candidate_dir.exists():
        errors.append(f"Temporary migration candidate directory remains: {candidate_dir.relative_to(root)}")
    if backup_disposition == "unresolved":
        errors.append("Template-adoption backup requires an explicit retain or remove disposition")
    if backup_dir.exists() and backup_disposition == "remove":
        errors.append("Template-adoption backup is marked remove but still exists")
    if not backup_dir.exists() and backup_disposition == "retain":
        errors.append("Template-adoption backup is marked retain but is missing")
    if backup_disposition in {"retain", "remove"} and not str(artifacts.get("backup_disposition_reason", "")).strip():
        errors.append("Template-adoption backup disposition requires a nonempty reason")
    if manifest.get("migration_finalized"):
        durable_paths = {
            Path(str(manifest.get("manifest_path", DEFAULT_MANIFEST))),
            DEFAULT_REPORT,
            DEFAULT_BASELINE_JSON,
            DEFAULT_BASELINE_REPORT,
        }
        if git_repository(root):
            durable_paths.add(SESSION_AUTHORITY_PATH)
            durable_paths.update(BEADS_TRACKED_CONTROL_PATHS)
        durable_paths.update(
            Path(str(feature["legacy_tasks_archive"]))
            for feature in features
            if feature.get("legacy_tasks_archive") and not str(feature["legacy_tasks_archive"]).startswith("deleted;")
        )
        durable_paths.update(
            path.relative_to(root) for path in (root / DEFAULT_TASK_ARCHIVE).glob("*.md") if path.is_file()
        )
        for path in sorted(durable_paths):
            target = root / path
            if not target.exists():
                errors.append(f"Required durable migration artifact is missing: {path}")
                continue
            if not (root / ".git").exists():
                continue
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", str(path)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            if tracked.returncode != 0:
                errors.append(f"Durable migration artifact is untracked: {path}")
    for cycle in beads_traversal_cycles(features):
        errors.append(
            "Migration manifest contains a Beads traversal cycle: " + render_relationship_cycle(cycle, features)
        )
    for feature in features:
        source = root / feature["source_dir"]
        target = root / feature["target_dir"]
        if manifest.get("migration_prepared") and not target.exists() and feature.get("has_design"):
            errors.append(f"Missing target feature directory: {target.relative_to(root)}")
        if source != target and source.exists():
            errors.append(f"Legacy numbered directory still exists: {source.relative_to(root)}")
        tasks = root / feature["legacy_tasks_path"]
        if manifest.get("migration_finalized") and tasks.exists():
            errors.append(f"Legacy tasks.md remains after finalization: {tasks.relative_to(root)}")
        open_questions_value = feature.get("legacy_open_questions_path")
        if manifest.get("migration_finalized") and open_questions_value:
            open_questions = root / str(open_questions_value)
            if open_questions.exists():
                errors.append(
                    "Legacy OPEN_QUESTIONS.md remains after finalization: " + str(open_questions.relative_to(root))
                )
        if feature.get("conflicts"):
            warnings.append(f"{feature['slug']} has {len(feature['conflicts'])} reconciliation findings")
        if verify_beads and not feature.get("beads", {}).get("root_id"):
            errors.append(f"{feature['slug']} manifest has no recorded Beads root")

    if verify_beads:
        try:
            remotes = json.loads(run_command(["bd", "dolt", "remote", "list", "--json"], cwd=root))
        except (json.JSONDecodeError, MigrationError) as exc:
            errors.append(f"Cannot inspect native Beads Git-origin synchronization: {exc}")
        else:
            if not isinstance(remotes, list) or not remotes:
                errors.append("Native Beads history has no configured Git-origin remote")
        try:
            graph, relationships = bd_feature_relationship_graph(root, features)
        except MigrationError as exc:
            errors.append(f"Cannot inspect imported Beads relationships: {exc}")
        else:
            for cycle in graph_cycles(graph):
                errors.append(
                    "Imported Beads graph contains a traversal cycle: " + render_typed_cycle(cycle, relationships)
                )

    stale_paths = {
        pattern: slug
        for source_name, slug in mapping.items()
        if source_name != slug
        for pattern in (f"docs/src/features/{source_name}/", f"features/{source_name}/", f"({source_name}/")
    }
    stale_pattern, stale_slugs = _compile_literal_replacements(stale_paths)
    for path in sorted((root / "docs/src").rglob("*.md")) if (root / "docs/src").exists() else []:
        text = read_text(path)
        match = stale_pattern.search(text) if stale_pattern is not None else None
        if match is not None:
            errors.append(f"Stale feature path for {stale_slugs[match.group(0)]} in {path.relative_to(root)}")
    if task_references(root):
        warnings.append("Reader-facing documentation still references legacy tasks.md")
    return errors, warnings


def run_docs_checker(root: Path, *, migration_mode: bool) -> int:
    checker = root / DOCS_CHECKER_PATH
    if not checker.exists():
        return 0
    command = [sys.executable, str(checker)]
    if migration_mode:
        command.append("--migration-mode")
    return subprocess.run(command, cwd=root, check=False).returncode


CAPABILITY_SCAN_LIMIT = 10_000
CAPABILITY_IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "_build",
    "build",
    "deps",
    "dist",
    "migration",
    "node_modules",
    "target",
    "vendor",
}
