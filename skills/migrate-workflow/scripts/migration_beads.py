"""Beads authority, import, and relationship adapters for migration."""

# ruff: noqa: S603

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import textwrap
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from migration_core import (
    _path_has_symlink,
    beads_traversal_cycles,
    dependency_cycles,
    FORMULA_PATH,
    LIFECYCLE_METADATA_KEYS,
    load_json,
    MigrationError,
    read_text,
    render_relationship_cycle,
    save_manifest_and_report,
    shell_command,
    UNPARSED_TASKS_FINDING,
)


def substitute(value: Any, variables: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for name, replacement in variables.items():
            result = result.replace(f"{{{{{name}}}}}", replacement)
            result = result.replace(f"{{{{ {name} }}}}", replacement)
        return result
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    if isinstance(value, dict):
        return {str(key): substitute(item, variables) for key, item in value.items()}
    return value


BD_BATCH_ACTIVE = False
BD_AUTHORITY_SNAPSHOT: dict[str, Any] | None = None


def set_batch_active(active: bool) -> None:
    global BD_BATCH_ACTIVE
    BD_BATCH_ACTIVE = active


def bd_mutates(command: Sequence[str]) -> bool:
    if not command or command[0] != "bd" or len(command) < 2:
        return False
    verb = command[1]
    if verb in {"create", "update", "close", "note"}:
        return True
    if verb == "dep":
        return len(command) > 2 and command[2] in {"add", "remove"}
    return verb == "dolt" and len(command) > 2 and command[2] == "commit"


def assert_beads_snapshot() -> None:
    if BD_AUTHORITY_SNAPSHOT is None:
        return
    beads_dir = Path(BD_AUTHORITY_SNAPSHOT["beads_dir"])
    if _path_has_symlink(beads_dir.parent, beads_dir):
        msg = "Repository-local Beads authority changed to a symlink after validation"
        raise MigrationError(msg)
    for key in ("metadata", "config"):
        path = Path(BD_AUTHORITY_SNAPSHOT[f"{key}_path"])
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != BD_AUTHORITY_SNAPSHOT[f"{key}_sha256"]
        ):
            msg = f"Repository-local Beads {key} changed after authority validation"
            raise MigrationError(msg)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    capture: bool = True,
    allow_existing: bool = False,
) -> str:
    actual_command = list(command)
    if actual_command[0] == "bd":
        if bd_mutates(command):
            assert_beads_snapshot()
        if BD_BATCH_ACTIVE and actual_command[1:2] != ["dolt"]:
            actual_command.insert(1, "--dolt-auto-commit=batch")
    result = subprocess.run(
        actual_command,
        cwd=cwd,
        check=False,
        capture_output=capture,
        text=True,
    )
    if result.returncode != 0:
        combined = ((result.stdout or "") + "\n" + (result.stderr or "")).casefold()
        if allow_existing and any(
            token in combined for token in ("already exists", "duplicate", "already closed", "dependency exists")
        ):
            return (result.stdout or "").strip()
        msg = f"Command failed ({result.returncode}): {shell_command(actual_command)}\n{(result.stderr or '').strip()}"
        raise MigrationError(msg)
    if bd_mutates(command):
        assert_beads_snapshot()
    return (result.stdout or "").strip()


def parse_bd_issue_list(output: str, *, command: str = "bd list --json") -> list[dict[str, Any]]:
    if not output.strip():
        return []
    value = json.loads(output)
    if isinstance(value, dict):
        for key in ("issues", "items", "data"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                value = candidate
                break
    if not isinstance(value, list):
        message = f"{command} returned an unexpected payload"
        raise MigrationError(message)
    return [item for item in value if isinstance(item, dict)]


def parse_json_object(output: str, *, command: str) -> dict[str, Any]:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        msg = f"{command} returned invalid JSON: {exc}"
        raise MigrationError(msg) from exc
    if not isinstance(value, dict):
        msg = f"{command} returned an unexpected payload"
        raise MigrationError(msg)
    return value


def canonical_project_slug(root: Path, repository_root: Path | None = None) -> str:
    candidates = [root / ".copier-answers.yml"]
    if repository_root is not None and repository_root.resolve() != root.resolve():
        candidates.append(repository_root / ".copier-answers.yml")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        match = re.search(r"^project_slug:\s*['\"]?([^'\"\s]+)", read_text(candidate), re.MULTILINE)
        if match:
            return match.group(1)
    return (repository_root or root).name


def validate_beads_authority(root: Path) -> dict[str, Any]:
    global BD_AUTHORITY_SNAPSHOT
    BD_AUTHORITY_SNAPSHOT = None
    context = parse_json_object(run_command(["bd", "context", "--json"], cwd=root), command="bd context --json")
    location = parse_json_object(run_command(["bd", "where", "--json"], cwd=root), command="bd where --json")

    repository_root = Path(str(context.get("repo_root", ""))).expanduser().resolve()
    expected_beads = repository_root / ".beads"
    metadata_path = expected_beads / "metadata.json"
    config_path = expected_beads / "config.yaml"
    metadata = load_json(metadata_path) if metadata_path.is_file() else None
    project_slug = canonical_project_slug(root, repository_root)
    expected_database = project_slug.replace("-", "_")
    problems: list[str] = []

    def same_path(value: Any, expected: Path) -> bool:
        try:
            return Path(str(value)).expanduser().resolve() == expected
        except (OSError, RuntimeError, ValueError):
            return False

    if expected_beads.is_symlink() or _path_has_symlink(repository_root, expected_beads):
        problems.append("Repository-local .beads authority must not be a symlink")
    if not isinstance(metadata, dict) or not config_path.is_file():
        problems.append("Native Beads authority requires repository-local metadata.json and config.yaml")
    if not same_path(context.get("cwd_repo_root"), root.resolve()):
        problems.append(f"bd context cwd_repo_root does not match {root.resolve()}")
    if not same_path(context.get("beads_dir"), expected_beads):
        problems.append("bd context does not use the repository-local .beads directory")
    if not same_path(location.get("path"), expected_beads):
        problems.append("bd where does not use the repository-local .beads directory")
    try:
        database_path = Path(str(location.get("database_path", ""))).expanduser().resolve()
        if not database_path.is_relative_to(expected_beads):
            problems.append("bd where database_path is outside the repository-local .beads directory")
    except (OSError, RuntimeError, ValueError):
        problems.append("bd where returned an invalid database_path")
    if (
        context.get("database") != expected_database
        or not isinstance(metadata, dict)
        or metadata.get("dolt_database") != expected_database
    ):
        problems.append(f"Beads database identity must be {expected_database!r}")
    if location.get("prefix") != project_slug:
        problems.append(f"Beads issue prefix must be {project_slug!r}")
    if (
        not isinstance(metadata, dict)
        or not metadata.get("project_id")
        or context.get("project_id") != metadata.get("project_id")
    ):
        problems.append("Beads project_id is missing or disagrees with repository-local metadata")
    if (
        context.get("backend") != "dolt"
        or context.get("dolt_mode") != "embedded"
        or context.get("is_redirected") is True
    ):
        problems.append("Migration requires native, non-redirected, repository-local embedded Dolt")
    if problems:
        message = "Beads authority mismatch; refusing global/shared fallback:\n  - " + "\n  - ".join(problems)
        raise MigrationError(message)

    assert isinstance(metadata, dict)
    BD_AUTHORITY_SNAPSHOT = {
        "beads_dir": str(expected_beads),
        "metadata_path": str(metadata_path),
        "metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "config_path": str(config_path),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "project_id": str(metadata["project_id"]),
    }
    return {"context": context, "location": location, "metadata": metadata}


def issue_metadata(issue: Mapping[str, Any]) -> dict[str, Any]:
    raw = issue.get("metadata")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def discover_migrated_issues(
    root: Path,
    label: str,
    *,
    issue_type: str | None = None,
) -> list[dict[str, Any]]:
    command = ["bd", "list", "--all", "--label", label]
    if issue_type is not None:
        command.extend(("--type", issue_type))
    command.extend(("--json", "--limit", "0"))
    output = run_command(command, cwd=root)
    return parse_bd_issue_list(output)


def metadata_feature_key(metadata: Mapping[str, Any]) -> str | None:
    """Read slug identity, accepting old metadata only to resume an import."""
    slug = str(metadata.get("feature_slug", ""))
    if slug:
        return slug
    legacy_path = str(metadata.get("legacy_tasks_path", ""))
    match = re.search(r"docs/src/features/(?:[0-9]{3,}-)?(?P<slug>[a-z0-9-]+)/tasks\.md$", legacy_path)
    return match.group("slug") if match else None


def index_discovered_issues(
    issues: Iterable[Mapping[str, Any]],
    *,
    discriminator: str | None = None,
    default_discriminator: str = "",
) -> dict[tuple[str, str], list[str]]:
    discovered: dict[tuple[str, str], list[str]] = {}
    for issue in issues:
        metadata = issue_metadata(issue)
        feature_key = metadata_feature_key(metadata)
        issue_id = str(issue.get("id", ""))
        if feature_key is None or not issue_id:
            continue
        value = "root" if discriminator is None else str(metadata.get(discriminator, default_discriminator))
        if not value:
            continue
        discovered.setdefault((feature_key, value), []).append(issue_id)
    return discovered


def reconcile_recorded_issue(
    *,
    feature: Mapping[str, Any],
    recorded: str,
    candidates: Sequence[str],
    description: str,
) -> tuple[str, bool, str | None]:
    unique = sorted(set(candidates))
    prefix = feature["slug"]
    if len(unique) > 1:
        return recorded, False, f"{prefix} has duplicate {description}: {', '.join(unique)}"
    if recorded and unique and recorded != unique[0]:
        return (
            recorded,
            False,
            f"{prefix} records {description} {recorded}, but Beads contains {unique[0]}",
        )
    if recorded and not unique:
        return (
            recorded,
            False,
            f"{prefix} records {description} {recorded}, but no matching Beads issue was found",
        )
    if not recorded and unique:
        return unique[0], True, None
    return recorded, False, None


def expected_migrated_statuses(feature: Mapping[str, Any]) -> tuple[str, dict[str, str], dict[str, str]]:
    classification = str(feature.get("classification", "planned"))
    root_status = "open"
    lifecycle = {step_id: "open" for step_id in LIFECYCLE_METADATA_KEYS}
    tasks: dict[str, str] = {}
    for task in feature.get("tasks", []):
        label = str(task.get("label", ""))
        if not label or label in {"T000", "T999"}:
            continue
        status = str(task.get("status", "open"))
        tasks[label] = "closed" if status in {"closed", "skipped"} else status
        if tasks[label] not in {"open", "closed", "in_progress", "blocked", "deferred"}:
            tasks[label] = "open"
    if classification == "completed":
        root_status = "closed"
        lifecycle = dict.fromkeys(lifecycle, "closed")
    elif classification == "needs_review":
        root_status = "in_progress"
        lifecycle["design"] = "closed"

    elif classification == "in_progress":
        root_status = "in_progress"
        lifecycle["design"] = "closed" if feature.get("evidence", {}).get("t000_closed") else "in_progress"
    elif classification == "designing":
        root_status = "in_progress"
        lifecycle["design"] = "in_progress"
    elif classification == "deferred":
        root_status = "deferred"
        lifecycle = dict.fromkeys(lifecycle, "deferred")
        tasks = dict.fromkeys(tasks, "deferred")
    return root_status, lifecycle, tasks


def validate_expected_issue(
    *,
    problems: list[str],
    issue: Mapping[str, Any] | None,
    issue_id: str,
    description: str,
    expected_status: str | None,
    expected_parent: str = "",
    required_labels: Iterable[str] = (),
    expected_owned_labels: Iterable[str] = (),
    expected_labels: Iterable[str] = (),
    allow_missing_labels: bool = False,
    required_metadata: Mapping[str, str] | None = None,
    expected_type: str | None = None,
) -> None:
    if issue is None:
        return
    actual_type = str(issue.get("issue_type") or issue.get("type") or "")
    if expected_type and actual_type != expected_type:
        problems.append(f"{description} {issue_id} has type {actual_type!r}; expected {expected_type!r}")
    actual_status = str(issue.get("status") or "")
    if expected_status is not None and actual_status != expected_status:
        problems.append(f"{description} {issue_id} has status {actual_status!r}; expected status {expected_status!r}")
    if expected_parent and str(issue.get("parent") or "") != expected_parent:
        problems.append(f"{description} {issue_id} is not parented by {expected_parent}")
    labels = {str(label) for label in issue.get("labels", [])}
    complete_expected_labels = set(expected_labels)
    missing_labels = sorted((complete_expected_labels or set(required_labels)) - labels)
    if missing_labels and not allow_missing_labels:
        problems.append(f"{description} {issue_id} is missing required labels: {', '.join(missing_labels)}")
    unexpected_labels = sorted(labels - complete_expected_labels) if complete_expected_labels else []
    if unexpected_labels:
        problems.append(f"{description} {issue_id} has unexpected labels: {', '.join(unexpected_labels)}")
    owned_labels = {
        label
        for label in labels
        if label == "workflow:feature" or label.startswith(("migration:", "formula-step:", "legacy-task:"))
    }
    allowed_owned = set(expected_owned_labels)
    unexpected_owned = owned_labels - allowed_owned
    if allowed_owned and unexpected_owned:
        problems.append(
            f"{description} {issue_id} has unexpected migration-owned labels: "
            f"allowed {sorted(allowed_owned)}, found {sorted(owned_labels)}"
        )
    metadata = issue_metadata(issue)
    for key, value in (required_metadata or {}).items():
        if str(metadata.get(key, "")) != value:
            problems.append(f"{description} {issue_id} has invalid metadata {key!r}; expected {value!r}")


def root_migration_labels(feature: Mapping[str, Any]) -> set[str]:
    labels = {"workflow:feature", "migration:legacy-markdown"}
    if feature.get("classification") == "needs_review":
        labels.add("migration:needs-reconciliation")
    return labels


def expected_beads_labels(
    feature: Mapping[str, Any],
    formula_steps: Mapping[str, Mapping[str, Any]],
) -> dict[str, set[str]]:
    beads = feature.get("beads", {})
    root_labels = root_migration_labels(feature)
    expected: dict[str, set[str]] = {}
    root_id = str(beads.get("root_id") or "")
    if root_id:
        expected[root_id] = set(root_labels)
    lifecycle_labels: dict[str, set[str]] = {}
    for step_id, issue_id_value in beads.get("lifecycle", {}).items():
        issue_id = str(issue_id_value or "")
        step = formula_steps.get(str(step_id), {})
        labels = root_labels | {str(label) for label in step.get("labels", [])}
        labels.update(("migration:legacy-workflow", f"formula-step:{step_id}"))
        if step.get("type") == "human":
            labels.add("requires-human")
        lifecycle_labels[str(step_id)] = labels
        if issue_id:
            expected[issue_id] = labels
    implementation_ancestry = lifecycle_labels.get("implementation", root_labels)
    for task_label, issue_id_value in beads.get("implementation_tasks", {}).items():
        issue_id = str(issue_id_value or "")
        if issue_id:
            expected[issue_id] = implementation_ancestry | {
                "migration:legacy-task",
                f"legacy-task:{str(task_label).casefold()}",
            }
    reconciliation_id = str(beads.get("migration_reconciliation_id") or "")
    if reconciliation_id:
        expected[reconciliation_id] = root_labels | {"migration:reconciliation", "review:drift"}
    return expected


def reconcile_existing_beads_state(
    root: Path,
    features: Sequence[dict[str, Any]],
    *,
    canonicalize: bool,
    allow_recovery: bool = True,
    allow_missing_labels: bool = False,
) -> int:
    root_issues = discover_migrated_issues(root, "migration:legacy-markdown", issue_type="epic")
    inherited_lifecycle_issues = discover_migrated_issues(root, "migration:legacy-workflow")
    lifecycle_issues = [issue for issue in inherited_lifecycle_issues if issue_metadata(issue).get("formula_step_id")]
    implementation_issues = discover_migrated_issues(root, "migration:legacy-task")
    reconciliation_issues = discover_migrated_issues(root, "migration:reconciliation")
    roots = index_discovered_issues(root_issues)
    lifecycle = index_discovered_issues(lifecycle_issues, discriminator="formula_step_id")
    implementation_tasks = index_discovered_issues(implementation_issues, discriminator="legacy_task_id")
    reconciliation = index_discovered_issues(
        reconciliation_issues,
        discriminator="migration_role",
        default_discriminator="status-reconciliation",
    )
    all_discovered = (*root_issues, *inherited_lifecycle_issues, *implementation_issues, *reconciliation_issues)
    discovered_by_id = {str(issue.get("id")): issue for issue in all_discovered if issue.get("id")}
    discovered_metadata = {issue_id: issue_metadata(issue) for issue_id, issue in discovered_by_id.items()}

    formula_steps = {
        str(step["id"]): step
        for step in load_formula(root).get("steps", [])
        if isinstance(step, dict) and step.get("id")
    }
    recovered_features: set[str] = set()
    problems: list[str] = []
    features_by_slug = {str(feature["slug"]): feature for feature in features}
    expected_lifecycle_keys = {
        (slug, step_id)
        for slug, feature in features_by_slug.items()
        if feature.get("has_design")
        for step_id in LIFECYCLE_METADATA_KEYS
    }
    expected_task_keys = {
        (slug, str(task.get("label")))
        for slug, feature in features_by_slug.items()
        if feature.get("has_design")
        for task in feature.get("tasks", [])
        if task.get("label") not in {"T000", "T999"}
    }
    expected_reconciliation_keys = {
        (slug, "status-reconciliation")
        for slug, feature in features_by_slug.items()
        if feature.get("has_design") and feature.get("classification") == "needs_review"
    }
    for issue in inherited_lifecycle_issues:
        metadata = issue_metadata(issue)
        if not metadata.get("formula_step_id") and not metadata.get("legacy_task_id"):
            problems.append(
                f"Unindexable migration-owned lifecycle record {issue.get('id', '<unknown>')}: "
                "metadata is malformed or formula_step_id is missing"
            )
    discovery_contracts = (
        (root_issues, None, {slug for slug in features_by_slug}, "root"),
        (lifecycle_issues, "formula_step_id", expected_lifecycle_keys, "lifecycle"),
        (implementation_issues, "legacy_task_id", expected_task_keys, "legacy task"),
        (reconciliation_issues, "migration_role", expected_reconciliation_keys, "reconciliation"),
    )
    for issues, discriminator, expected_keys, description in discovery_contracts:
        for issue in issues:
            metadata = issue_metadata(issue)
            slug = metadata_feature_key(metadata)
            discriminator_value = (
                None
                if discriminator is None
                else str(
                    metadata.get(discriminator, "status-reconciliation" if discriminator == "migration_role" else "")
                )
            )
            key: Any = slug if discriminator is None else (slug, discriminator_value)
            if metadata.get("migration_source") != "legacy-markdown-workflow":
                problems.append(
                    f"Unindexable migration-owned {description} record {issue.get('id', '<unknown>')}: "
                    "metadata is malformed or migration_source is missing/wrong"
                )
            elif not slug or key not in expected_keys:
                problems.append(
                    f"Unexpected migrated {description} record {issue.get('id', '<unknown>')} with identity {key!r}"
                )
    for feature in features:
        slug = str(feature["slug"])
        beads = feature.setdefault("beads", {})
        import_complete = beads.get("import_phase") == "completed" or bool(beads.get("state_applied"))
        require_complete = not allow_recovery or import_complete

        root_id, did_recover, problem = reconcile_recorded_issue(
            feature=feature,
            recorded=str(beads.get("root_id") or ""),
            candidates=roots.get((slug, "root"), []),
            description="Beads roots",
        )
        if problem:
            problems.append(problem)
        elif did_recover and not allow_recovery:
            problems.append(f"{slug} manifest has no recorded Beads root; recovery is not verification")
        elif did_recover:
            beads["root_id"] = root_id
            recovered_features.add(slug)
        elif require_complete and not root_id:
            problems.append(f"{slug} is missing required Beads root")

        lifecycle_state = beads.setdefault("lifecycle", {})
        for step_id in LIFECYCLE_METADATA_KEYS:
            issue_id, did_recover, problem = reconcile_recorded_issue(
                feature=feature,
                recorded=str(lifecycle_state.get(step_id) or ""),
                candidates=lifecycle.get((slug, step_id), []),
                description=f"lifecycle step {step_id!r}",
            )
            if problem:
                problems.append(problem)
            elif did_recover and not allow_recovery:
                problems.append(f"{slug} manifest has no recorded lifecycle step {step_id!r}")
            elif did_recover:
                lifecycle_state[step_id] = issue_id
                recovered_features.add(slug)
            elif require_complete and feature.get("has_design") and not issue_id:
                problems.append(f"{slug} is missing required lifecycle step {step_id!r}")

        task_state = beads.setdefault("implementation_tasks", {})
        for task in feature.get("tasks", []):
            label = str(task.get("label", ""))
            if not label or label in {"T000", "T999"}:
                continue
            issue_id, did_recover, problem = reconcile_recorded_issue(
                feature=feature,
                recorded=str(task_state.get(label) or ""),
                candidates=implementation_tasks.get((slug, label), []),
                description=f"legacy task {label}",
            )
            if problem:
                problems.append(problem)
            elif did_recover and not allow_recovery:
                problems.append(f"{slug} manifest has no recorded legacy task {label}")
            elif did_recover:
                task_state[label] = issue_id
                recovered_features.add(slug)
            elif require_complete and feature.get("has_design") and not issue_id:
                problems.append(f"{slug} is missing required legacy task {label}")

        reconciliation_id, did_recover, problem = reconcile_recorded_issue(
            feature=feature,
            recorded=str(beads.get("migration_reconciliation_id") or ""),
            candidates=reconciliation.get((slug, "status-reconciliation"), []),
            description="migration reconciliation tasks",
        )
        if problem:
            problems.append(problem)
        elif did_recover and not allow_recovery:
            problems.append(f"{slug} manifest has no recorded migration reconciliation task")
        elif did_recover:
            beads["migration_reconciliation_id"] = reconciliation_id
            recovered_features.add(slug)
        elif (
            require_complete
            and feature.get("has_design")
            and feature.get("classification") == "needs_review"
            and not reconciliation_id
        ):
            problems.append(f"{slug} is missing required migration reconciliation task")

    roots_by_slug = {str(feature["slug"]): str(feature.get("beads", {}).get("root_id") or "") for feature in features}
    relationship_issue_ids = [
        str(feature.get("beads", {}).get("root_id") or "")
        for feature in features
        if feature.get("beads", {}).get("root_id")
    ]
    relationships_by_root = bd_dependency_types_batch(root, relationship_issue_ids)
    for feature in features:
        slug = str(feature["slug"])
        beads = feature.get("beads", {})
        root_id = str(beads.get("root_id") or "")
        root_issue = discovered_by_id.get(root_id)
        root_status, lifecycle_statuses, task_statuses = expected_migrated_statuses(feature)
        state_complete = bool(beads.get("state_applied"))
        complete_labels = expected_beads_labels(feature, formula_steps)
        root_owned_labels = (
            "workflow:feature",
            "migration:legacy-markdown",
            *(("migration:needs-reconciliation",) if feature.get("classification") == "needs_review" else ()),
        )
        validate_expected_issue(
            problems=problems,
            issue=root_issue,
            issue_id=root_id,
            description=f"{slug} recorded root",
            expected_status=root_status if state_complete else None,
            required_labels=root_owned_labels,
            expected_owned_labels=root_owned_labels,
            expected_labels=complete_labels.get(root_id, ()),
            allow_missing_labels=allow_missing_labels,
            required_metadata={
                "migration_source": "legacy-markdown-workflow",
                "migration_key": f"legacy-feature:{slug}",
                "feature_slug": slug,
            },
            expected_type="epic",
        )
        expected_lifecycle = set(LIFECYCLE_METADATA_KEYS) if feature.get("has_design") else set()
        unexpected_lifecycle = sorted(set(beads.get("lifecycle", {})) - expected_lifecycle)
        if unexpected_lifecycle:
            problems.append(f"{slug} records unexpected lifecycle steps: {', '.join(unexpected_lifecycle)}")
        for step_id in sorted(expected_lifecycle):
            issue_id = str(beads.get("lifecycle", {}).get(step_id) or "")
            validate_expected_issue(
                problems=problems,
                issue=discovered_by_id.get(issue_id),
                issue_id=issue_id,
                description=f"{slug} lifecycle step {step_id!r}",
                expected_status=lifecycle_statuses[step_id] if state_complete else None,
                expected_parent=root_id,
                required_labels=("migration:legacy-workflow", f"formula-step:{step_id}"),
                expected_owned_labels=(
                    *root_owned_labels,
                    "migration:legacy-workflow",
                    f"formula-step:{step_id}",
                ),
                expected_labels=complete_labels.get(issue_id, ()),
                allow_missing_labels=allow_missing_labels,
                required_metadata={
                    "migration_source": "legacy-markdown-workflow",
                    "migration_key": f"legacy-feature:{slug}:lifecycle:{step_id}",
                    "formula_step_id": step_id,
                    "feature_slug": slug,
                },
                expected_type="task",
            )
        implementation_parent = str(beads.get("lifecycle", {}).get("implementation") or "")
        expected_task_labels = set(task_statuses)
        unexpected_tasks = sorted(set(beads.get("implementation_tasks", {})) - expected_task_labels)
        if unexpected_tasks:
            problems.append(f"{slug} records unexpected legacy tasks: {', '.join(unexpected_tasks)}")
        for label in sorted(expected_task_labels):
            issue_id = str(beads.get("implementation_tasks", {}).get(label) or "")
            validate_expected_issue(
                problems=problems,
                issue=discovered_by_id.get(issue_id),
                issue_id=issue_id,
                description=f"{slug} legacy task {label}",
                expected_status=task_statuses[label] if state_complete else None,
                expected_parent=implementation_parent,
                required_labels=("migration:legacy-task", f"legacy-task:{label.casefold()}"),
                expected_owned_labels=(
                    *root_owned_labels,
                    "migration:legacy-workflow",
                    "formula-step:implementation",
                    "migration:legacy-task",
                    f"legacy-task:{label.casefold()}",
                ),
                expected_labels=complete_labels.get(issue_id, ()),
                allow_missing_labels=allow_missing_labels,
                required_metadata={
                    "migration_source": "legacy-markdown-workflow",
                    "migration_key": f"legacy-feature:{slug}:task:{label}",
                    "legacy_task_id": label,
                    "feature_slug": slug,
                },
                expected_type="task",
            )
        reconciliation_id = str(beads.get("migration_reconciliation_id") or "")
        reconciliation_issue = discovered_by_id.get(reconciliation_id)
        if reconciliation_id:
            validate_expected_issue(
                problems=problems,
                issue=reconciliation_issue,
                issue_id=reconciliation_id,
                description=f"{slug} migration reconciliation task",
                expected_status="open",
                expected_parent=root_id,
                required_labels=("migration:reconciliation", "review:drift"),
                expected_owned_labels=(*root_owned_labels, "migration:reconciliation"),
                expected_labels=complete_labels.get(reconciliation_id, ()),
                allow_missing_labels=allow_missing_labels,
                required_metadata={
                    "migration_source": "legacy-markdown-workflow",
                    "migration_key": f"legacy-feature:{slug}:reconciliation",
                    "migration_role": "status-reconciliation",
                    "feature_slug": slug,
                },
                expected_type="task",
            )
        if root_id and root_issue is not None:
            expected_relationships = {
                roots_by_slug[dependency]: "blocks"
                for dependency in feature.get("dependencies", [])
                if roots_by_slug.get(str(dependency))
            }
            expected_relationships.update(
                {
                    roots_by_slug[dependency]: "related"
                    for dependency in feature.get("related_dependencies", [])
                    if roots_by_slug.get(str(dependency))
                }
            )
            parent_slug = feature.get("parent_feature")
            if parent_slug and roots_by_slug.get(str(parent_slug)):
                expected_relationships[roots_by_slug[str(parent_slug)]] = "related"
            actual_relationships = relationships_by_root.get(root_id, {})
            relationship_complete = not allow_recovery or beads.get("import_phase") == "completed"
            has_conflicting_relationship = any(
                expected_relationships.get(issue_id) != relationship
                for issue_id, relationship in actual_relationships.items()
            )
            if (
                relationship_complete and actual_relationships != expected_relationships
            ) or has_conflicting_relationship:
                problems.append(
                    f"{slug} root relationships differ from the deterministic manifest: "
                    f"expected {expected_relationships}, found {actual_relationships}"
                )

    if problems:
        raise MigrationError(
            "Existing migrated Beads state must be reconciled before import:\n  - " + "\n  - ".join(problems)
        )
    # Old interrupted imports used number-bearing metadata. Recovery is keyed
    # by the slug fallback above. Canonicalization is a separate apply-only
    # mutation; dry-run and verification never update Beads.
    if canonicalize:
        for feature in features:
            beads = feature.get("beads", {})
            issue_ids = [beads.get("root_id"), beads.get("migration_reconciliation_id")]
            issue_ids.extend(beads.get("lifecycle", {}).values())
            issue_ids.extend(beads.get("implementation_tasks", {}).values())
            for issue_id in {str(value) for value in issue_ids if value}:
                metadata = discovered_metadata.get(issue_id, {})
                expected = {"feature_slug": feature["slug"], "feature_name": feature["title"]}
                if any(metadata.get(key) != value for key, value in expected.items()):
                    bd_set_metadata(root, issue_id, expected)
                if "feature_number" in metadata:
                    bd_unset_metadata(root, issue_id, "feature_number")
    return len(recovered_features)


def bd_create(
    root: Path,
    *,
    title: str,
    issue_type: str,
    parent: str | None = None,
    labels: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
    description: str = "",
    acceptance: str = "",
    spec_id: str | None = None,
    status: str | None = None,
    priority: int = 2,
) -> str:
    command = ["bd", "create", title, "--type", issue_type, "--priority", str(priority), "--silent"]
    if parent:
        command.extend(("--parent", parent))
    label_values = sorted(set(label for label in labels if label))
    if label_values:
        command.extend(("--labels", ",".join(label_values)))
    if metadata:
        command.extend(("--metadata", json.dumps(metadata, sort_keys=True, separators=(",", ":"))))
    if description:
        command.extend(("--description", description))
    if acceptance:
        command.extend(("--acceptance", acceptance))
    if spec_id:
        command.extend(("--spec-id", spec_id))
    output = run_command(command, cwd=root)
    issue_id = output.splitlines()[-1].strip() if output else ""
    if not issue_id or any(character.isspace() for character in issue_id):
        msg = f"Could not parse Beads issue ID from: {output!r}"
        raise MigrationError(msg)
    if status:
        # Beads 1.1 does not support `bd create --status`. Creation and state
        # transition are intentionally separate supported operations.
        bd_update_status(root, issue_id, status)
    return issue_id


def bd_update_status(root: Path, issue_id: str, status: str) -> None:
    run_command(["bd", "update", issue_id, "--status", status], cwd=root, allow_existing=True)


def bd_set_metadata(root: Path, issue_id: str, values: Mapping[str, Any]) -> None:
    command = ["bd", "update", issue_id]
    for key, value in sorted(values.items()):
        if value is None:
            continue
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            rendered = str(value)
        command.extend(("--set-metadata", f"{key}={rendered}"))
    if len(command) > 3:
        run_command(command, cwd=root, allow_existing=True)


def bd_unset_metadata(root: Path, issue_id: str, *keys: str) -> None:
    if keys:
        run_command(["bd", "update", issue_id, "--unset-metadata", *keys], cwd=root, allow_existing=True)


def bd_note(root: Path, issue_id: str, note: str) -> None:
    if not note:
        return
    try:
        existing = json.loads(run_command(["bd", "show", issue_id, "--json"], cwd=root, allow_existing=True) or "{}")
    except (json.JSONDecodeError, MigrationError):
        existing = {}
    notes = existing.get("notes", "") if isinstance(existing, dict) else ""
    if note in str(notes):
        return
    run_command(["bd", "update", issue_id, "--append-notes", note], cwd=root, allow_existing=True)


def bd_close(root: Path, issue_id: str, reason: str) -> None:
    run_command(["bd", "close", issue_id, "--reason", reason], cwd=root, allow_existing=True)


def bd_dep(root: Path, issue_id: str, depends_on: str, dep_type: str = "blocks") -> None:
    run_command(
        ["bd", "dep", "add", issue_id, depends_on, "--type", dep_type],
        cwd=root,
        allow_existing=True,
    )


def _dependency_records_by_target(records: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    dependencies: dict[str, str] = {}
    for item in records:
        target = item.get("depends_on_id") or item.get("id")
        if target:
            dependencies[str(target)] = str(item.get("dependency_type") or item.get("type") or "blocks")
    return dependencies


def _bd_dependency_types_single(root: Path, issue_id: str) -> dict[str, str]:
    output = run_command(["bd", "dep", "list", issue_id, "--json"], cwd=root)
    dependencies = parse_bd_issue_list(output, command="bd dep list --json")
    return _dependency_records_by_target(dependencies)


def bd_dependency_types_batch(root: Path, issue_ids: Sequence[str]) -> dict[str, dict[str, str]]:
    normalized_ids = tuple(dict.fromkeys(str(issue_id) for issue_id in issue_ids if issue_id))
    grouped = {issue_id: {} for issue_id in normalized_ids}
    if not normalized_ids:
        return grouped

    output = run_command(["bd", "dep", "list", *normalized_ids, "--json"], cwd=root)
    dependencies = parse_bd_issue_list(output, command="bd dep list --json")
    if not dependencies:
        if len(normalized_ids) == 1:
            return grouped
        # An older Beads response can omit source IDs and silently return only
        # the first requested issue. Probe individually before accepting an
        # empty multi-issue result as complete.
        return {issue_id: _bd_dependency_types_single(root, issue_id) for issue_id in normalized_ids}

    batch_records = all(
        item.get("issue_id") in grouped and (item.get("depends_on_id") or item.get("id")) for item in dependencies
    )
    if batch_records:
        for issue_id in normalized_ids:
            grouped[issue_id] = _dependency_records_by_target(
                item for item in dependencies if item.get("issue_id") == issue_id
            )
        return grouped

    if len(normalized_ids) == 1:
        grouped[normalized_ids[0]] = _dependency_records_by_target(dependencies)
        return grouped

    # Older Beads versions return dependency records without their source ID.
    # Preserve compatibility with one bounded fallback call per issue only when
    # the batch response cannot be attributed safely.
    return {issue_id: _bd_dependency_types_single(root, issue_id) for issue_id in normalized_ids}


def bd_dependency_types(root: Path, issue_id: str) -> dict[str, str]:
    return bd_dependency_types_batch(root, [issue_id]).get(issue_id, {})


def bd_remove_dep(root: Path, issue_id: str, depends_on: str) -> None:
    run_command(["bd", "dep", "remove", issue_id, depends_on], cwd=root)


def reconcile_bd_relation(
    root: Path,
    *,
    issue_id: str,
    depends_on: str,
    relation: str,
) -> None:
    existing = bd_dependency_types(root, issue_id).get(depends_on)
    desired = None if relation == "remove" else relation
    if existing == desired:
        return
    if existing is not None:
        bd_remove_dep(root, issue_id, depends_on)
    if desired is not None:
        bd_dep(root, issue_id, depends_on, desired)


def bd_feature_relationship_graph(
    root: Path,
    features: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[str]], dict[tuple[str, str], str]]:
    slug_by_id = {
        str(feature.get("beads", {}).get("root_id")): str(feature["slug"])
        for feature in features
        if feature.get("beads", {}).get("root_id")
    }
    graph = {str(feature["slug"]): [] for feature in features}
    relationships: dict[tuple[str, str], str] = {}
    issue_ids = [
        str(feature.get("beads", {}).get("root_id") or "")
        for feature in features
        if feature.get("beads", {}).get("root_id")
    ]
    dependencies_by_issue = bd_dependency_types_batch(root, issue_ids)
    for feature in features:
        source = str(feature["slug"])
        issue_id = str(feature.get("beads", {}).get("root_id") or "")
        if not issue_id:
            continue
        for dependency_id, relation in dependencies_by_issue.get(issue_id, {}).items():
            target = slug_by_id.get(dependency_id)
            if target is None:
                continue
            graph[source].append(target)
            relationships[(source, target)] = relation
        graph[source] = sorted(set(graph[source]))
    return graph, relationships


def load_formula(root: Path) -> dict[str, Any]:
    path = root / FORMULA_PATH
    if not path.exists():
        msg = f"Missing lifecycle formula: {FORMULA_PATH}"
        raise MigrationError(msg)
    formula = tomllib.loads(read_text(path))
    steps = formula.get("steps")
    if not isinstance(steps, list) or not steps:
        msg = f"Formula has no steps: {FORMULA_PATH}"
        raise MigrationError(msg)
    return formula


def validate_formula(formula: Mapping[str, Any]) -> None:
    raw_steps = formula.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        msg = "Feature lifecycle formula contains no steps"
        raise MigrationError(msg)
    steps: dict[str, Mapping[str, Any]] = {}
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict) or not raw_step.get("id"):
            msg = "Feature lifecycle formula has a step without an ID"
            raise MigrationError(msg)
        step_id = str(raw_step["id"])
        if step_id in steps:
            msg = f"Feature lifecycle formula has duplicate step ID {step_id!r}"
            raise MigrationError(msg)
        steps[step_id] = raw_step

    for step_id, step in steps.items():
        current_type = str(step.get("type", "task"))
        for prerequisite in step.get("needs", step.get("depends_on", [])):
            prerequisite_id = str(prerequisite)
            if prerequisite_id not in steps:
                msg = f"Formula step {step_id!r} depends on unknown step {prerequisite_id!r}"
                raise MigrationError(msg)
            prerequisite_type = str(steps[prerequisite_id].get("type", "task"))
            if prerequisite_type == "epic" and current_type != "epic":
                msg = (
                    "Beads forbids an epic blocking a non-epic formula step: "
                    f"{prerequisite_id!r} -> {step_id!r}. Use a task coordinator instead."
                )
                raise MigrationError(msg)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            msg = f"Feature lifecycle formula contains a cycle at {step_id!r}"
            raise MigrationError(msg)
        if step_id in visited:
            return
        visiting.add(step_id)
        step = steps[step_id]
        for prerequisite in step.get("needs", step.get("depends_on", [])):
            visit(str(prerequisite))
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in sorted(steps):
        visit(step_id)


def preflight_import(manifest: Mapping[str, Any], formula: Mapping[str, Any]) -> None:
    validate_formula(formula)
    unparsed = [
        feature["slug"]
        for feature in manifest.get("features", [])
        if isinstance(feature, dict)
        and feature.get("has_tasks")
        and not feature.get("tasks")
        and UNPARSED_TASKS_FINDING in feature.get("conflicts", [])
    ]
    if unparsed:
        raise MigrationError(
            "Legacy task parser coverage must be resolved before Beads import: "
            + ", ".join(unparsed)
            + ". Extend the parser or resolve the finding after manually mapping the task state."
        )
    features = [feature for feature in manifest.get("features", []) if isinstance(feature, dict)]
    blocking_cycles = dependency_cycles(features)
    if blocking_cycles:
        rendered = "; ".join(" -> ".join(cycle) for cycle in blocking_cycles)
        raise MigrationError(
            "Feature blocking dependency cycles must be resolved before Beads import: "
            + rendered
            + ". Remove or correct one inferred edge. Do not downgrade it to related: "
            "bd list traverses related edges too."
        )
    traversal_cycles = beads_traversal_cycles(features)
    if traversal_cycles:
        rendered = "; ".join(render_relationship_cycle(cycle, features) for cycle in traversal_cycles)
        raise MigrationError(
            "Feature relationships would create recursive Beads traversal: "
            + rendered
            + ". Remove or correct one inferred edge; related is only valid when the complete traversal graph remains "
            "acyclic."
        )


def create_feature_root(root: Path, feature: dict[str, Any]) -> str:
    metadata = {
        "feature_slug": feature["slug"],
        "feature_name": feature["title"],
        "design_path": feature["design_path"],
        "implemented_path": feature["implemented_path"],
        "base_branch": "main",
        "migration_source": "legacy-markdown-workflow",
        "migration_key": f"legacy-feature:{feature['slug']}",
        "migration_classification": feature["classification"],
        "legacy_roadmap_status": feature.get("roadmap_status", ""),
    }
    description = textwrap.dedent(
        f"""
        Migrated feature from the legacy Markdown workflow.

        Legacy roadmap status: {feature.get("roadmap_status") or "not recorded"}
        Legacy design status: {feature.get("design_status") or "not recorded"}
        Design: {feature["design_path"]}
        Implemented record: {feature["implemented_path"]}
        Migration classification: {feature["classification"]}
        """
    ).strip()
    labels = ["workflow:feature", "migration:legacy-markdown"]
    if feature["classification"] == "needs_review":
        labels.append("migration:needs-reconciliation")
    status = "deferred" if feature["classification"] == "deferred" else None
    spec_id = feature["design_path"] if feature.get("has_design") else None
    return bd_create(
        root,
        title=feature["title"],
        issue_type="epic",
        labels=labels,
        metadata=metadata,
        description=description,
        spec_id=spec_id,
        status=status,
        priority=1 if feature["classification"] in {"in_progress", "needs_review"} else 2,
    )


def create_lifecycle_steps(
    root: Path,
    feature: dict[str, Any],
    root_id: str,
    formula: Mapping[str, Any],
    manifest_path: Path,
    report_path: Path,
    manifest: dict[str, Any],
) -> dict[str, str]:
    existing = feature.setdefault("beads", {}).setdefault("lifecycle", {})
    variables = {
        "feature_name": feature["title"],
        "feature_slug": feature["slug"],
        "design_path": feature["design_path"],
        "implemented_path": feature["implemented_path"],
        "base_branch": "main",
    }
    steps = formula["steps"]
    for raw_step in steps:
        step = substitute(raw_step, variables)
        step_id = str(step["id"])
        if existing.get(step_id):
            continue
        raw_type = str(step.get("type", "task"))
        issue_type = "task" if raw_type in {"human", "gate"} else raw_type
        if issue_type not in {"task", "epic", "feature", "chore", "decision", "spike", "story", "milestone"}:
            issue_type = "task"
        labels = list(step.get("labels", []))
        labels.extend(("migration:legacy-workflow", f"formula-step:{step_id}"))
        if raw_type == "human":
            labels.append("requires-human")
        metadata = dict(step.get("metadata", {}))
        metadata.update(
            {
                "formula_step_id": step_id,
                "migration_source": "legacy-markdown-workflow",
                "migration_key": (f"legacy-feature:{feature['slug']}:lifecycle:{step_id}"),
                "feature_slug": feature["slug"],
                "feature_name": feature["title"],
            }
        )
        issue_id = bd_create(
            root,
            title=str(step["title"]),
            issue_type=issue_type,
            parent=root_id,
            labels=labels,
            metadata=metadata,
            description=str(step.get("description", "")).strip(),
            priority=int(step.get("priority", 2)),
        )
        existing[step_id] = issue_id
        save_manifest_and_report(root, manifest_path, report_path, manifest)

    for raw_step in steps:
        step_id = str(raw_step["id"])
        issue_id = existing[step_id]
        for prerequisite in raw_step.get("needs", raw_step.get("depends_on", [])):
            bd_dep(root, issue_id, existing[str(prerequisite)])

    # Persist the resolved child IDs on the root. Downstream skills can then
    # load one compact `bd show <root> --json` payload instead of scanning the
    # full child graph every session.
    root_metadata = {
        metadata_key: existing[step_id]
        for step_id, metadata_key in LIFECYCLE_METADATA_KEYS.items()
        if step_id in existing
    }
    root_metadata.update(
        {
            "workflow_kind": "legacy-parent-child",
            "migration_manifest": str(manifest_path),
        }
    )
    bd_set_metadata(root, root_id, root_metadata)
    return {str(key): str(value) for key, value in existing.items()}


def create_legacy_implementation_tasks(
    root: Path,
    feature: dict[str, Any],
    implementation_id: str,
    spec_reconcile_id: str,
    manifest_path: Path,
    report_path: Path,
    manifest: dict[str, Any],
) -> dict[str, str]:
    existing = feature.setdefault("beads", {}).setdefault("implementation_tasks", {})
    tasks = [task for task in feature.get("tasks", []) if task["label"] not in {"T000", "T999"}]
    for task in tasks:
        label = task["label"]
        if existing.get(label):
            continue
        metadata = {
            "legacy_task_id": label,
            "legacy_status": task["status"],
            "legacy_tasks_path": feature["legacy_tasks_path"],
            "parallel_safe": task.get("parallel"),
            "design_path": feature["design_path"],
            "migration_source": "legacy-markdown-workflow",
            "migration_key": f"legacy-feature:{feature['slug']}:task:{label}",
            "feature_slug": feature["slug"],
            "feature_name": feature["title"],
        }
        description_parts = [
            f"Imported from `{feature['legacy_tasks_path']}`.",
            f"Legacy task: {label}",
        ]
        if task.get("parallel") is not None:
            description_parts.append(f"Legacy parallel flag: {'yes' if task['parallel'] else 'no'}")
        if task.get("body"):
            description_parts.extend(("", "Legacy task details:", str(task["body"])))
        acceptance_parts = []
        if task.get("validation"):
            acceptance_parts.append("Validation: " + task["validation"])
        if task.get("completion_constraint"):
            acceptance_parts.append("Completion constraint: " + task["completion_constraint"])
        issue_id = bd_create(
            root,
            title=f"{feature['slug']} {label} — {task['title']}",
            issue_type="task",
            parent=implementation_id,
            labels=("migration:legacy-task", f"legacy-task:{label.casefold()}"),
            metadata=metadata,
            description="\n".join(description_parts),
            acceptance="\n".join(acceptance_parts),
            priority=2,
        )
        existing[label] = issue_id
        save_manifest_and_report(root, manifest_path, report_path, manifest)

    for task in tasks:
        issue_id = existing[task["label"]]
        for dependency in task.get("depends_on", []):
            dependency_id = existing.get(dependency)
            if dependency_id:
                bd_dep(root, issue_id, dependency_id)
        if task["status"] != "closed" and feature["classification"] not in {"completed", "deferred"}:
            bd_dep(root, issue_id, spec_reconcile_id)
    return {str(key): str(value) for key, value in existing.items()}


def apply_imported_states(
    root: Path,
    feature: dict[str, Any],
    root_id: str,
    lifecycle: Mapping[str, str],
    implementation_tasks: Mapping[str, str],
) -> None:
    if feature.setdefault("beads", {}).get("state_applied"):
        return
    task_by_label = {task["label"]: task for task in feature.get("tasks", [])}
    classification = feature["classification"]

    for label, issue_id in implementation_tasks.items():
        state = task_by_label[label]["status"]
        if state == "closed":
            bd_close(root, issue_id, f"Migrated as completed from {feature['legacy_tasks_path']} ({label})")
        elif state == "skipped":
            bd_close(root, issue_id, f"Migrated as skipped from {feature['legacy_tasks_path']} ({label})")
        elif state in {"in_progress", "blocked", "deferred"}:
            bd_update_status(root, issue_id, state)

    if classification == "completed":
        for step_id in (
            "design",
            "review-specification-clarity",
            "review-execution-readiness",
            "spec-reconcile",
            "implementation",
            "docs-reconcile",
            "validate",
            "review-implementation",
            "review-delivery-integrity",
            "delivery",
        ):
            bd_close(root, lifecycle[step_id], "Migrated completed legacy feature evidence")
        bd_close(root, root_id, "Migrated completed legacy feature")
    elif classification == "needs_review":
        bd_close(root, lifecycle["design"], "Legacy design evidence imported; fresh specification reviews remain")

        open_implementation_ids = [
            implementation_tasks[label]
            for label, task in task_by_label.items()
            if label in implementation_tasks and task["status"] != "closed"
        ]

        reconciliation_id = feature["beads"].get("migration_reconciliation_id")
        if not reconciliation_id:
            conflict_text = (
                "\n".join(f"- {item}" for item in feature.get("conflicts", []))
                or "- Confirm migrated status and documentation evidence."
            )
            reconciliation_id = bd_create(
                root,
                title=f"Reconcile migrated status: {feature['title']}",
                issue_type="task",
                parent=root_id,
                labels=("migration:reconciliation", "review:drift"),
                metadata={
                    "migration_source": "legacy-markdown-workflow",
                    "migration_key": (f"legacy-feature:{feature['slug']}:reconciliation"),
                    "migration_role": "status-reconciliation",
                    "feature_slug": feature["slug"],
                    "feature_name": feature["title"],
                },
                description="Resolve contradictory legacy roadmap, design, task, and implemented-record evidence.\n\n"
                + conflict_text,
                acceptance=(
                    "The final Beads state, design status, implemented record, roadmap, "
                    "and current documentation agree."
                ),
                priority=1,
            )
            feature["beads"]["migration_reconciliation_id"] = reconciliation_id
        for issue_id in open_implementation_ids:
            bd_dep(root, issue_id, reconciliation_id)
        bd_dep(root, lifecycle["docs-reconcile"], reconciliation_id)
        bd_dep(root, lifecycle["validate"], reconciliation_id)
        bd_update_status(root, root_id, "in_progress")
        bd_note(root, root_id, "Migration requires status/documentation reconciliation before close-out.")
    elif classification == "in_progress":
        if feature.get("evidence", {}).get("t000_closed"):
            bd_close(root, lifecycle["design"], "Legacy T000 indicates a completed design/spec readiness gate")
        else:
            bd_update_status(root, lifecycle["design"], "in_progress")
        bd_update_status(root, root_id, "in_progress")
        bd_note(
            root,
            root_id,
            (
                "Run /start-feature to execute the new isolated specification reviews before "
                "claiming remaining imported work."
            ),
        )
    elif classification == "designing":
        bd_update_status(root, lifecycle["design"], "in_progress")
        bd_update_status(root, root_id, "in_progress")
    elif classification == "deferred":
        for issue_id in implementation_tasks.values():
            bd_update_status(root, issue_id, "deferred")
        for issue_id in lifecycle.values():
            bd_update_status(root, issue_id, "deferred")
        bd_update_status(root, root_id, "deferred")

    feature["beads"]["state_applied"] = True
