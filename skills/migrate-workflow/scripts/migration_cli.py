"""Command-line interface for the legacy workflow migration engine."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from migration_core import (
    baseline_repository,
    build_manifest,
    confirm_hk_inventory,
    DEFAULT_BASELINE_JSON,
    DEFAULT_BASELINE_REPORT,
    DEFAULT_MANIFEST,
    DEFAULT_REPORT,
    DEFAULT_TASK_ARCHIVE,
    DELIVERED_CANDIDATE_DIR,
    draft_delivered_records,
    ensure_bd_available,
    FINALIZATION_JOURNAL_PATH,
    FINALIZATION_STAGING_DIR,
    finalize_migration,
    import_beads,
    load_json,
    MigrationError,
    print_scan_summary,
    record_checkpoint_evidence,
    repair_beads_labels,
    repository_root,
    resolve_findings,
    review_delivered_record,
    safe_repository_path,
    save_manifest_and_report,
    SESSION_AUTHORITY_PATH,
    SESSION_RESUME_LOG_PATH,
    set_backup_disposition,
    set_classification,
    set_dependency_relation,
    set_hk_disposition,
    set_release_tool_decision,
    TEMPLATE_BACKUP_DIR,
    TEMPLATE_CANDIDATE_DIR,
    VALID_CLASSIFICATIONS,
)
from migration_filesystem import prepare_filesystem
from migration_git import authorize_session, require_session_authority, validate_manifest_paths
from migration_verification import run_docs_checker, verify_migration


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result")
    parser.add_argument("--root", type=Path, help="Repository root; defaults to git root")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    authority = subparsers.add_parser(
        "authorize-session",
        help="Bind migration execution to an explicitly selected base branch, branch, worktree, and repository",
    )
    authority.add_argument("mode", choices=("fresh", "resume"))
    authority.add_argument("--root", type=Path, help="Repository root; defaults to git root")
    authority.add_argument("--base-branch", required=True)
    authority.add_argument("--migration-branch", required=True)
    authority.add_argument("--approval", default="")
    authority.add_argument("--json", action="store_true", help="Print a machine-readable result")

    beads_authority = subparsers.add_parser(
        "beads-authority",
        help="Initialize if explicitly requested and verify repository-local Beads authority",
    )
    beads_authority.add_argument("--root", type=Path, help="Repository root; defaults to git root")
    beads_authority.add_argument("--init", action="store_true")
    beads_authority.add_argument("--json", action="store_true", help="Print a machine-readable result")

    baseline = subparsers.add_parser("baseline", help="Record pre-adoption documentation and test capabilities")
    baseline.add_argument("--root", type=Path, help="Repository root; defaults to git root")
    baseline.add_argument("--docs-command", help="Explicit documentation validation command")
    baseline.add_argument("--test-command", help="Explicit test command")
    baseline.add_argument(
        "--validation-partition",
        action="append",
        default=[],
        help="Repeatable JSON object with name, kind, argv, working_directory, and provenance",
    )
    baseline.add_argument("--write", action="store_true", help="Write baseline JSON and Markdown reports")
    baseline.add_argument("--baseline-json", type=Path, default=DEFAULT_BASELINE_JSON)
    baseline.add_argument("--baseline-report", type=Path, default=DEFAULT_BASELINE_REPORT)
    baseline.add_argument("--json", action="store_true", help="Print a machine-readable result")

    scan = subparsers.add_parser("scan", help="Inventory the legacy workflow")
    add_common_arguments(scan)
    scan.add_argument("--write", action="store_true", help="Write manifest and report")

    checkpoint = subparsers.add_parser(
        "checkpoint-evidence",
        help="Record verified hook or targeted checkpoint exception evidence",
    )
    add_common_arguments(checkpoint)
    checkpoint.add_argument("--hook", required=True)
    checkpoint.add_argument("--status", choices=("passed", "failed", "exception"), required=True)
    checkpoint.add_argument("--command", dest="checkpoint_command", required=True)
    checkpoint.add_argument("--reason", default="")
    checkpoint.add_argument("--equivalent-result", default="")
    checkpoint.add_argument("--residual-risk", default="")
    checkpoint.add_argument("--approved-step", default="")
    checkpoint.add_argument("--approval", default="")

    backup_disposition = subparsers.add_parser(
        "backup-disposition",
        help="Record whether conditional template-adoption backups are retained or removed",
    )
    add_common_arguments(backup_disposition)
    backup_disposition.add_argument("disposition", choices=("retain", "remove"))
    backup_disposition.add_argument("--reason", required=True)

    hk_confirmation = subparsers.add_parser(
        "confirm-hk-inventory",
        help="Record a manually confirmed pre-adoption hk inventory",
    )
    add_common_arguments(hk_confirmation)
    hk_confirmation.add_argument("--inventory-json", type=Path, required=True)
    hk_confirmation.add_argument("--reason", required=True)

    hk_disposition = subparsers.add_parser(
        "reconcile-hk",
        help="Record an explicit disposition for a removed or replaced legacy hk step",
    )
    add_common_arguments(hk_disposition)
    hk_disposition.add_argument("hook")
    hk_disposition.add_argument("step")
    hk_disposition.add_argument("action", choices=("remove", "replace"))
    hk_disposition.add_argument("--reason", required=True)

    release_decision = subparsers.add_parser(
        "release-tool-decision",
        help="Record whether migration converts, retains, or removes the existing release authority",
    )
    add_common_arguments(release_decision)
    release_decision.add_argument("action", choices=("convert", "retain", "remove"))
    release_decision.add_argument("--tool", required=True)
    release_decision.add_argument("--reason", required=True)

    prepare = subparsers.add_parser("prepare", help="Normalize feature paths and rewrite links")
    add_common_arguments(prepare)
    prepare.add_argument("--apply", action="store_true")
    prepare.add_argument("--allow-dirty", action="store_true")

    classify = subparsers.add_parser(
        "classify",
        help="Set or clear an evidence-backed classification override before Beads import",
    )
    add_common_arguments(classify)
    classify.add_argument("feature", help="Feature slug")
    classify.add_argument(
        "classification",
        choices=("auto", *sorted(VALID_CLASSIFICATIONS)),
        help="Effective migration classification, or auto to clear the override",
    )
    classify.add_argument(
        "--reason",
        default="",
        help="Evidence/rationale for a non-auto override",
    )

    dependency = subparsers.add_parser(
        "dependency",
        help="Record or reconcile a feature dependency relation during migration",
    )
    add_common_arguments(dependency)
    dependency.add_argument("feature", help="Dependent feature slug")
    dependency.add_argument("dependency", help="Prerequisite/related feature slug")
    dependency.add_argument("relation", choices=("blocks", "related", "remove"))
    dependency.add_argument("--reason", required=True)

    resolve = subparsers.add_parser(
        "resolve-findings",
        help="Record evidence-backed resolutions for scanner findings",
    )
    add_common_arguments(resolve)
    resolve.add_argument("feature", help="Feature slug")
    resolve.add_argument(
        "--finding",
        action="append",
        default=[],
        help="Finding ID from the migration report; repeatable",
    )
    resolve.add_argument("--all", action="store_true", help="Resolve every currently open finding for the feature")
    resolve.add_argument("--reason", required=True, help="Evidence and rationale for the resolution")

    import_parser = subparsers.add_parser("import-beads", help="Import feature and task state into Beads")
    add_common_arguments(import_parser)
    import_parser.add_argument("--apply", action="store_true")
    import_parser.add_argument("--init-beads", action="store_true")
    import_parser.add_argument("--feature", action="append", default=[], help="Import only a slug")
    import_parser.add_argument(
        "--batch-size",
        type=int,
        choices=range(1, 15),
        default=2,
        metavar="1..14",
        help="Maximum incomplete features to mutate in one apply pass (default: 2)",
    )

    repair_labels = subparsers.add_parser(
        "repair-beads-labels",
        help="Preview or add deterministic labels missing from exact migrated records",
    )
    add_common_arguments(repair_labels)
    repair_labels.add_argument("--apply", action="store_true")

    draft_records = subparsers.add_parser(
        "draft-delivered-records", help="Draft historical delivered records for required human review"
    )
    add_common_arguments(draft_records)
    draft_records.add_argument("--apply", action="store_true")

    review_record = subparsers.add_parser(
        "review-delivered-record", help="Record human semantic review of a drafted delivered record"
    )
    add_common_arguments(review_record)
    review_record.add_argument("feature")
    review_record.add_argument("--reason", required=True)
    review_record.add_argument("--summary", default="")
    review_record.add_argument("--evidence", action="append", default=[])
    review_record.add_argument("--commit", action="append", default=[])

    finalize = subparsers.add_parser("finalize", help="Archive legacy task files after semantic reconciliation")
    add_common_arguments(finalize)
    finalize.add_argument("--apply", action="store_true")
    finalize.add_argument("--delete-tasks", action="store_true")
    finalize.add_argument("--archive-dir", type=Path, default=DEFAULT_TASK_ARCHIVE)

    verify = subparsers.add_parser("verify", help="Verify migrated paths and state")
    add_common_arguments(verify)
    verify.add_argument("--beads", action="store_true")
    verify.add_argument("--skip-docs-check", action="store_true")

    return parser.parse_args(argv)


def normalize_manifest_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    """Upgrade an interrupted numbered migration in memory before resuming it."""
    for feature in manifest.get("features", []):
        if not isinstance(feature, dict) or not isinstance(feature.get("slug"), str):
            continue
        slug = feature["slug"]
        feature.pop("number", None)
        for key in (
            "target_dir",
            "design_path",
            "implemented_path",
            "legacy_tasks_path",
            "legacy_open_questions_path",
        ):
            value = feature.get(key)
            if not isinstance(value, str):
                continue
            feature[key] = re.sub(
                r"docs/src/features/[0-9]{3,}-" + re.escape(slug),
                f"docs/src/features/{slug}",
                value,
            )
    return manifest


def load_or_scan(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_json(root / args.manifest)
    if manifest is not None:
        normalize_manifest_identity(manifest)
        validate_manifest_paths(root, manifest)
        if manifest.get("migration_finalized"):
            return manifest
    result = build_manifest(root, manifest_path=args.manifest)
    validate_manifest_paths(root, result)
    return result


def validate_cli_artifact_paths(root: Path, args: argparse.Namespace) -> None:
    migration_prefix = PurePosixPath("migration")
    expected_suffixes = {
        "manifest": ".json",
        "report": ".md",
        "baseline_json": ".json",
        "baseline_report": ".md",
    }
    paths: dict[str, Path] = {}
    reserved_directories = (
        DEFAULT_TASK_ARCHIVE,
        FINALIZATION_STAGING_DIR,
        TEMPLATE_CANDIDATE_DIR,
        TEMPLATE_BACKUP_DIR,
        DELIVERED_CANDIDATE_DIR,
    )
    for attribute, suffix in expected_suffixes.items():
        value = getattr(args, attribute, None)
        if value is None:
            continue
        path = safe_repository_path(
            root,
            value,
            description=f"command.{attribute}",
            required_prefix=migration_prefix,
        )
        relative = path.relative_to(root)
        if path.suffix != suffix:
            msg = f"Migration {attribute} must use a {suffix} file: {relative}"
            raise MigrationError(msg)
        if relative in {SESSION_AUTHORITY_PATH, SESSION_RESUME_LOG_PATH, FINALIZATION_JOURNAL_PATH} or any(
            relative.is_relative_to(directory) for directory in reserved_directories
        ):
            msg = f"Migration {attribute} collides with reserved migration evidence: {relative}"
            raise MigrationError(msg)
        paths[attribute] = path
    by_path: dict[Path, list[str]] = {}
    for attribute, path in paths.items():
        by_path.setdefault(path, []).append(attribute)
    collisions = [names for names in by_path.values() if len(names) > 1]
    if collisions:
        msg = "Migration artifact paths must be pairwise distinct: " + "; ".join(
            ", ".join(names) for names in collisions
        )
        raise MigrationError(msg)


def require_hk_reconciliation(manifest: Mapping[str, Any]) -> None:
    issues = manifest.get("hk_reconciliation", {}).get("issues", [])
    if issues:
        kinds = ", ".join(sorted({str(item.get("kind", "issue")) for item in issues}))
        message = f"hk reconciliation must be resolved before migration mutation: {kinds}"
        raise MigrationError(message)


def _main(args: argparse.Namespace) -> int:
    root = repository_root(args.root)
    try:
        if args.command == "authorize-session":
            authorize_session(
                root,
                mode=args.mode,
                base_branch=args.base_branch,
                migration_branch=args.migration_branch,
                approval=args.approval,
            )
            return 0

        require_session_authority(root, require_committed=args.command != "baseline")
        validate_cli_artifact_paths(root, args)

        if args.command == "beads-authority":
            ensure_bd_available(root, init_beads=args.init)
            print("Repository-local Beads authority verified.")
            return 0

        if args.command == "baseline":
            return baseline_repository(
                root,
                docs_command=args.docs_command,
                test_command=args.test_command,
                validation_partition_specs=args.validation_partition,
                write=args.write,
                baseline_json=args.baseline_json,
                baseline_report=args.baseline_report,
                json_output=args.json,
            )

        if args.command == "scan":
            manifest = build_manifest(
                root,
                manifest_path=args.manifest,
            )
            if args.write:
                save_manifest_and_report(root, args.manifest, args.report, manifest)
                print(f"Wrote {args.manifest} and {args.report}")
            if args.json:
                print(json.dumps(manifest, indent=2, sort_keys=True))
            else:
                print_scan_summary(manifest)
            return 0

        manifest = load_or_scan(root, args)

        if args.command == "checkpoint-evidence":
            record_checkpoint_evidence(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                hook=args.hook,
                status=args.status,
                command=args.checkpoint_command,
                reason=args.reason,
                equivalent_result=args.equivalent_result,
                residual_risk=args.residual_risk,
                approved_step=args.approved_step,
                approval=args.approval,
            )
            return 0

        if args.command == "backup-disposition":
            set_backup_disposition(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                disposition=args.disposition,
                reason=args.reason,
            )
            return 0

        if args.command == "confirm-hk-inventory":
            confirm_hk_inventory(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                inventory_path=args.inventory_json,
                reason=args.reason,
            )
            return 0

        if args.command == "reconcile-hk":
            set_hk_disposition(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                hook=args.hook,
                step=args.step,
                action=args.action,
                reason=args.reason,
            )
            return 0

        if args.command == "release-tool-decision":
            set_release_tool_decision(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                action=args.action,
                tool=args.tool,
                reason=args.reason,
            )
            return 0

        if args.command in {
            "prepare",
            "classify",
            "dependency",
            "resolve-findings",
            "import-beads",
            "finalize",
        }:
            require_hk_reconciliation(manifest)

        if args.command == "prepare":
            prepare_filesystem(
                root,
                manifest,
                apply=args.apply,
                allow_dirty=args.allow_dirty,
            )
            if args.apply:
                save_manifest_and_report(root, args.manifest, args.report, manifest)
            return 0

        if args.command == "classify":
            set_classification(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                requested=args.feature,
                classification=args.classification,
                reason=args.reason,
            )
            return 0

        if args.command == "dependency":
            set_dependency_relation(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                requested=args.feature,
                dependency_requested=args.dependency,
                relation=args.relation,
                reason=args.reason,
            )
            return 0

        if args.command == "resolve-findings":
            resolve_findings(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                requested=args.feature,
                finding_ids=args.finding,
                resolve_all=args.all,
                reason=args.reason,
            )
            return 0

        if args.command == "import-beads":
            import_beads(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                apply=args.apply,
                init_beads=args.init_beads,
                requested=args.feature,
                batch_size=args.batch_size,
            )
            return 0

        if args.command == "repair-beads-labels":
            repair_beads_labels(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                apply=args.apply,
            )
            return 0

        if args.command == "draft-delivered-records":
            draft_delivered_records(root, manifest, apply=args.apply)
            if args.apply:
                save_manifest_and_report(root, args.manifest, args.report, manifest)
            return 0

        if args.command == "review-delivered-record":
            review_delivered_record(
                root,
                manifest,
                args.feature,
                args.reason,
                summary=args.summary,
                evidence_paths=args.evidence,
                commits=args.commit,
            )
            save_manifest_and_report(root, args.manifest, args.report, manifest)
            return 0

        if args.command == "finalize":
            finalize_migration(
                root,
                manifest,
                manifest_path=args.manifest,
                report_path=args.report,
                apply=args.apply,
                delete_tasks=args.delete_tasks,
                archive_dir=args.archive_dir,
            )
            if args.apply:
                save_manifest_and_report(root, args.manifest, args.report, manifest)
            return 0

        if args.command == "verify":
            if args.beads:
                ensure_bd_available(root, init_beads=False)
            errors, warnings = verify_migration(root, manifest, verify_beads=args.beads)
            for warning in warnings:
                print("WARNING:", warning)
            for error in errors:
                print("ERROR:", error, file=sys.stderr)
            if errors:
                return 1
            if not args.skip_docs_check:
                migration_mode = not bool(manifest.get("migration_finalized"))
                checker_status = run_docs_checker(root, migration_mode=migration_mode)
                if checker_status != 0:
                    return checker_status
            print("Workflow migration verification passed.")
            if any(feature.get("conflicts") for feature in manifest.get("features", [])):
                print("Migration state: mechanical migration complete; semantic reconciliation pending.")
            else:
                print("Migration state: migration complete.")
            return 0

        msg = f"Unsupported command: {args.command}"
        raise MigrationError(msg)
    except (MigrationError, OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not getattr(args, "json", False):
        return _main(args)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = _main(args)
    payload = {
        "command": args.command,
        "status": "passed" if code == 0 else "failed",
        "exit_code": code,
        "output": [line for line in buffer.getvalue().splitlines() if line],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
