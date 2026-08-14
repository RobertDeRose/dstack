#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: S603, S607
"""Migrate the legacy Markdown feature workflow to the Beads workflow.

The migration is intentionally staged:

``baseline``
    Record pre-adoption documentation and test capabilities without assuming
    dstack-owned scripts exist. Missing checkers and repositories with no tests
    are recorded as limitations rather than failures.

``scan``
    Inventory legacy roadmap entries, feature folders, task files, status
    evidence, dependencies, and contradictions. Writes no project files unless
    ``--write`` is supplied.

``prepare``
    Normalize feature directories to slug-only paths, rewrite links,
    and add stable feature slugs to the roadmap and implemented-feature markers.
    Dry-run by default; pass ``--apply`` to change files.

``classify``
    Record or clear an evidence-backed classification override before Beads
    import. The decision and reason remain in the migration manifest.

``import-beads``
    Create Beads feature roots, lifecycle steps derived from the repository's
    dstack-feature formula, imported implementation tasks, dependencies, and
    conservative workflow state. Dry-run by default; pass ``--apply``.

``finalize``
    Archive legacy ``tasks.md`` files only after no documentation file includes
    or links to them. This intentionally refuses to guess how historical
    feature pages should be rewritten.

``verify``
    Validate the filesystem migration and, optionally, the imported Beads IDs.

The script handles mechanical migration. The ``/migrate-workflow`` skill owns
semantic reconciliation of feature designs, implemented-feature records,
reader-facing documentation, and contradictory historical status evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MANIFEST = Path("migration/workflow-migration.json")
DEFAULT_REPORT = Path("migration/workflow-migration.md")
DEFAULT_TASK_ARCHIVE = Path("migration/legacy-tasks")
DEFAULT_BASELINE_JSON = Path("migration/baseline.json")
DEFAULT_BASELINE_REPORT = Path("migration/baseline.md")
SESSION_AUTHORITY_PATH = Path("migration/session-authority.json")
SESSION_RESUME_LOG_PATH = Path("migration/session-resume-approvals.json")
FINALIZATION_JOURNAL_PATH = Path("migration/finalization-journal.json")
FINALIZATION_STAGING_DIR = Path("migration/.finalization-staging")
TEMPLATE_CANDIDATE_DIR = Path("migration/template-adoption-candidates")
TEMPLATE_BACKUP_DIR = Path("migration/template-adoption-backup")
DELIVERED_CANDIDATE_DIR = Path("migration/delivered-record-candidates")
FORMULA_PATH = Path(".beads/formulas/dstack-feature.formula.toml")
BEADS_TRACKED_CONTROL_PATHS = {
    Path(".beads/.gitignore"),
    Path(".beads/README.md"),
    Path(".beads/config.yaml"),
    Path(".beads/interactions.jsonl"),
    Path(".beads/metadata.json"),
    FORMULA_PATH,
}
FEATURES_PATH = Path("docs/src/features")
ROADMAP_PATH = Path("docs/src/planned-features.md")
SUMMARY_PATH = Path("docs/src/SUMMARY.md")
FEATURE_INDEX_PATH = Path("docs/src/features/index.md")
DOCS_CHECKER_PATH = Path("scripts/check-docs.py")

FEATURE_DIR_RE = re.compile(r"^(?:(?P<number>[0-9]{3,})-)?(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
ROADMAP_HEADING_RE = re.compile(
    r"^###\s+(?:F(?P<number>[0-9]{3,})\s+[—-]\s+)?"
    r"(?:(?P<title>[^`\n]+?)\s*\(\s*)?"
    r"`(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)`\s*\)?\s*$",
    re.MULTILINE,
)
CHECKBOX_TASK_HEADING_RE = re.compile(
    r"^-\s+\[(?P<mark>[^\]])\]\s+`?(?P<label>T[0-9]+)`?(?:\s+(?P<title>.*?))?\s*$",
    re.MULTILINE,
)
SECTION_TASK_HEADING_RE = re.compile(
    r"^#{2,6}\s+`?(?P<label>T[0-9]+)`?(?:(?:\s*[:—-]\s*|\s+)(?P<title>.*?))?\s*$",
    re.MULTILINE,
)
FIELD_RE = re.compile(r"^(?P<indent>\s*)(?:[-*]\s+)?(?P<name>[A-Za-z][A-Za-z -]+):\s*(?P<value>.*)$")
MARKER_START = "<!-- BEGIN IMPLEMENTED FEATURES -->"
MARKER_END = "<!-- END IMPLEMENTED FEATURES -->"
MIGRATION_MARKER = "<!-- workflow-migration:legacy-markdown-to-beads -->"
UNPARSED_TASKS_FINDING = (
    "Legacy tasks.md exists but no recognizable T### tasks were parsed; "
    "extend the parser or resolve this finding after manually mapping the task state"
)
VALID_CLASSIFICATIONS = {
    "planned",
    "designing",
    "in_progress",
    "completed",
    "deferred",
    "needs_review",
}
CYCLE_CONFLICT_PREFIXES = (
    "Feature dependency cycle:",
    "Feature Beads traversal cycle:",
)

LIFECYCLE_METADATA_KEYS = {
    "design": "design_id",
    "review-specification-clarity": "review_specification_clarity_id",
    "review-execution-readiness": "review_execution_readiness_id",
    "spec-reconcile": "spec_reconcile_id",
    "implementation": "implementation_id",
    "docs-reconcile": "docs_reconcile_id",
    "validate": "validation_id",
    "review-implementation": "review_implementation_integrity_id",
    "review-delivery-integrity": "review_delivery_integrity_id",
    "delivery": "delivery_id",
}


@dataclass(slots=True)
class LegacyTask:
    label: str
    title: str
    status: str
    depends_on: list[str] = field(default_factory=list)
    parallel: bool | None = None
    validation: str = ""
    completion_constraint: str = ""
    body: str = ""
    fields: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "title": self.title,
            "status": self.status,
            "depends_on": self.depends_on,
            "parallel": self.parallel,
            "validation": self.validation,
            "completion_constraint": self.completion_constraint,
            "body": self.body,
            "fields": self.fields,
        }


@dataclass(slots=True)
class RoadmapEntry:
    slug: str
    title: str
    order: int
    legacy_number: str | None
    status: str
    parent_feature: str | None
    dependency_tokens: list[str]
    raw_dependencies: str


class MigrationError(RuntimeError):
    """Raised when migration cannot continue safely."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def repository_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.rstrip() + "\n"
    path.write_text(normalized, encoding="utf-8", newline="\n")


def shell_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(read_text(path))
    if not isinstance(value, dict):
        msg = f"Expected object in {path}"
        raise MigrationError(msg)
    return value


def dump_json(path: Path, value: Mapping[str, Any]) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def dump_compact_json(path: Path, value: Mapping[str, Any]) -> None:
    write_text(path, json.dumps(value, sort_keys=True, separators=(",", ":")))


def finding_id(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]


def slug_title(slug: str) -> str:
    acronyms = {"api", "cli", "ci", "cd", "git", "hk", "http", "https", "mqtt", "sdk", "ui", "url"}
    words = [word.upper() if word in acronyms else word for word in slug.split("-")]
    title = " ".join(words)
    return title[:1].upper() + title[1:]


def strip_number(name: str) -> tuple[str | None, str]:
    match = FEATURE_DIR_RE.fullmatch(name)
    if match is None:
        msg = f"Invalid feature directory name: {name}"
        raise MigrationError(msg)
    return match.group("number"), match.group("slug")


def normalize_roadmap_status(value: str) -> str:
    lowered = value.casefold().strip()
    if any(token in lowered for token in ("future", "deferred", "when needed", "postponed")):
        return "deferred"
    if any(token in lowered for token in ("partial", "in progress", "in-progress", "implementing")):
        return "in_progress"
    if any(token in lowered for token in ("implemented", "completed", "complete", "delivered", "done")):
        return "completed"
    if any(token in lowered for token in ("in spec", "in-spec", "review", "design")):
        return "designing"
    return "planned"


def parse_roadmap(path: Path) -> tuple[list[RoadmapEntry], str]:
    if not path.exists():
        return [], ""
    text = read_text(path)
    matches = list(ROADMAP_HEADING_RE.finditer(text))
    entries: list[RoadmapEntry] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        status_match = re.search(r"^-\s+Status:\s*(.+?)\s*$", body, re.MULTILINE)
        parent_match = re.search(r"^-\s+Parent feature:\s*(.+?)\s*$", body, re.MULTILINE)
        dependencies_match = re.search(
            r"^-\s+Dependencies:\s*(.*?)(?=^-\s+[A-Z][A-Za-z /-]+:|^####|^###|^##|\Z)",
            body,
            re.MULTILINE | re.DOTALL,
        )
        dependency_text = dependencies_match.group(1).strip() if dependencies_match else ""
        dependency_tokens = re.findall(r"`((?:F)?[0-9]{3,}|[a-z0-9]+(?:-[a-z0-9]+)*)`", dependency_text)
        parent_raw = parent_match.group(1).strip() if parent_match else ""
        parent_token = re.search(r"`((?:F)?[0-9]{3,}|[a-z0-9]+(?:-[a-z0-9]+)*)`", parent_raw)
        entries.append(
            RoadmapEntry(
                slug=match.group("slug"),
                title=(match.group("title") or "").strip(),
                order=index,
                legacy_number=match.group("number"),
                status=status_match.group(1).strip() if status_match else "",
                parent_feature=parent_token.group(1) if parent_token else None,
                dependency_tokens=dependency_tokens,
                raw_dependencies=dependency_text,
            )
        )
    legacy_numbers = {entry.legacy_number: entry.slug for entry in entries if entry.legacy_number}
    for entry in entries:
        entry.dependency_tokens = sorted(
            set(legacy_numbers.get(token.removeprefix("F"), token) for token in entry.dependency_tokens)
        )
        if entry.parent_feature:
            entry.parent_feature = legacy_numbers.get(entry.parent_feature.removeprefix("F"), entry.parent_feature)
    return entries, text


def parse_summary_feature_order(path: Path) -> list[str]:
    if not path.exists():
        return []
    order: list[str] = []
    for raw in re.findall(r"\]\((?:\./)?features/([^/]+)/index\.md(?:#[^)]+)?\)", read_text(path)):
        try:
            _, slug = strip_number(raw)
        except MigrationError:
            continue
        if slug not in order:
            order.append(slug)
    return order


def parse_design_status(path: Path) -> str:
    if not path.exists():
        return ""
    text = read_text(path)
    match = re.search(r"^##\s+Status\s*$\n(?P<body>.*?)(?=^##\s+|\Z)", text, re.MULTILINE | re.DOTALL)
    if match is None:
        return ""
    for line in match.group("body").splitlines():
        value = line.strip().lstrip("- ")
        if value:
            return value
    return ""


def normalize_task_status(value: str, *, fallback: str = "open") -> str:
    normalized = re.sub(r"[\s_-]+", " ", value.casefold().strip())
    if not normalized:
        return fallback
    if normalized in {"x", "done", "complete", "completed", "closed", "passed"}:
        return "closed"
    if normalized in {"-", "~", ">", "in progress", "active", "started", "doing"}:
        return "in_progress"
    if normalized in {"blocked", "waiting", "stalled"}:
        return "blocked"
    if normalized in {"deferred", "postponed"}:
        return "deferred"
    if normalized in {"skipped", "cancelled", "canceled", "not applicable", "n/a", "na"}:
        return "skipped"
    if normalized in {"todo", "open", "pending", "planned", "not started"}:
        return "open"
    return fallback


def checkbox_status(mark: str) -> str:
    normalized = mark.casefold().strip()
    if normalized == "x":
        return "closed"
    if normalized in {"-", "~", ">"}:
        return "in_progress"
    return "open"


def parse_task_fields(lines: list[str]) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    current: str | None = None
    current_indent = -1
    for line in lines:
        match = FIELD_RE.match(line)
        if match is not None:
            current = match.group("name").strip().casefold().replace(" ", "_")
            current_indent = len(match.group("indent"))
            values[current] = [match.group("value").strip()]
            continue
        if current is None or not line.strip():
            continue
        indentation = len(line) - len(line.lstrip())
        stripped = line.lstrip()
        if indentation > current_indent and not stripped.startswith(("- ", "* ")):
            values[current].append(stripped)
        else:
            current = None
            current_indent = -1
    return {name: " ".join(part for part in parts if part).strip() for name, parts in values.items()}


def parse_tasks(path: Path) -> list[LegacyTask]:
    if not path.exists():
        return []
    text = read_text(path)
    raw_matches: list[tuple[int, int, str, str, str | None]] = []
    for match in CHECKBOX_TASK_HEADING_RE.finditer(text):
        raw_matches.append(
            (
                match.start(),
                match.end(),
                match.group("label"),
                (match.group("title") or "").strip(),
                match.group("mark"),
            )
        )
    for match in SECTION_TASK_HEADING_RE.finditer(text):
        raw_matches.append(
            (
                match.start(),
                match.end(),
                match.group("label"),
                (match.group("title") or "").strip(),
                None,
            )
        )
    matches = sorted(raw_matches, key=lambda item: item[0])
    tasks: list[LegacyTask] = []
    seen_labels: set[str] = set()
    for index, (_start, heading_end, label, raw_title, mark) in enumerate(matches):
        if label in seen_labels:
            continue
        seen_labels.add(label)
        section_end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        body = text[heading_end:section_end].strip()
        fields = parse_task_fields(body.splitlines())
        dependency_text = fields.get("depends_on", fields.get("dependencies", ""))
        depends_on = (
            []
            if dependency_text.casefold() in {"", "none", "n/a", "na", "-"}
            else list(dict.fromkeys(re.findall(r"T[0-9]+", dependency_text, re.IGNORECASE)))
        )
        depends_on = [dependency.upper() for dependency in depends_on]
        parallel_raw = fields.get("parallel", "").casefold()
        parallel: bool | None
        if parallel_raw.startswith(("yes", "true", "safe")):
            parallel = True
        elif parallel_raw.startswith(("no", "false", "unsafe")):
            parallel = False
        else:
            parallel = None
        fallback = checkbox_status(mark) if mark is not None else "open"
        status = normalize_task_status(fields.get("status", ""), fallback=fallback)
        tasks.append(
            LegacyTask(
                label=label.upper(),
                title=raw_title or label.upper(),
                status=status,
                depends_on=depends_on,
                parallel=parallel,
                validation=fields.get("validation", ""),
                completion_constraint=fields.get("completion_constraint", ""),
                body=body,
                fields=fields,
            )
        )
    return tasks


def existing_feature_dirs(features_dir: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not features_dir.exists():
        return result
    for path in sorted(features_dir.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        match = FEATURE_DIR_RE.fullmatch(path.name)
        if match is None:
            continue
        slug = match.group("slug")
        if slug in result:
            first = result[slug]["path"]
            message = f"Feature directories {first.name!r} and {path.name!r} normalize to duplicate slug {slug!r}"
            raise MigrationError(message)
        result[slug] = {
            "number": match.group("number"),
            "path": path,
        }
    return result


def status_conflicts(
    *,
    roadmap_state: str,
    design_status: str,
    tasks: list[LegacyTask],
    has_tasks_file: bool,
    has_index: bool,
    index_text: str,
) -> tuple[str, list[str], dict[str, bool]]:
    by_label = {task.label: task for task in tasks}
    implementation_tasks = [task for task in tasks if task.label not in {"T000", "T999"}]
    t000_done = by_label.get("T000") is not None and by_label["T000"].status == "closed"
    t999_done = by_label.get("T999") is not None and by_label["T999"].status == "closed"
    any_started = any(task.status in {"closed", "in_progress", "blocked"} for task in implementation_tasks)
    all_done = bool(implementation_tasks) and all(
        task.status in {"closed", "skipped", "deferred"} for task in implementation_tasks
    )
    completed_evidence = all_done and t999_done and has_index

    conflicts: list[str] = []
    if roadmap_state == "completed" and not completed_evidence:
        missing: list[str] = []
        if not all_done:
            missing.append("all implementation tasks closed")
        if not t999_done:
            missing.append("T999 closed")
        if not has_index:
            missing.append("implemented-feature index.md")
        conflicts.append("Roadmap says completed/implemented but completion evidence is missing: " + ", ".join(missing))
    if roadmap_state == "in_progress" and completed_evidence:
        conflicts.append(
            "Roadmap says partially implemented while tasks, T999, and index.md indicate completed delivery"
        )
    if has_index and "{{#include tasks.md}}" in index_text:
        conflicts.append(
            "Implemented-feature index.md embeds legacy tasks.md and must be rewritten before task archival"
        )
    if has_index and "{{#include design.md}}" in index_text:
        conflicts.append("Implemented-feature index.md embeds the internal design instead of standing alone")
    design_lower = design_status.casefold()
    if completed_evidence and any(
        token in design_lower for token in ("draft", "ready for implementation", "in implementation")
    ):
        conflicts.append(f"Design status appears stale for delivered evidence: {design_status!r}")
    if tasks:
        known = set(by_label)
        for task in tasks:
            unknown = [dependency for dependency in task.depends_on if dependency not in known]
            if unknown:
                conflicts.append(f"{task.label} depends on missing legacy tasks: {', '.join(unknown)}")
    if not tasks and has_tasks_file:
        conflicts.append(UNPARSED_TASKS_FINDING)
    elif not tasks and (roadmap_state in {"completed", "in_progress"} or design_status or has_index):
        conflicts.append("No legacy tasks.md was found; implementation state requires manual reconciliation")

    if roadmap_state == "deferred" and not any_started:
        classification = "deferred"
    elif roadmap_state == "completed" and completed_evidence and not conflicts:
        classification = "completed"
    elif completed_evidence or roadmap_state == "completed":
        classification = "needs_review"
    elif any_started or roadmap_state == "in_progress":
        classification = "in_progress"
    elif t000_done or design_status:
        classification = "designing"
    else:
        classification = "planned"

    evidence = {
        "t000_closed": t000_done,
        "t999_closed": t999_done,
        "any_implementation_started": any_started,
        "all_implementation_closed": all_done,
        "completed_evidence": completed_evidence,
    }
    return classification, conflicts, evidence


def canonical_cycle(nodes: Sequence[str]) -> tuple[str, ...]:
    cycle = list(nodes)
    if cycle and cycle[0] == cycle[-1]:
        cycle.pop()
    if not cycle:
        return ()
    rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
    return min(rotations)


def graph_cycles(graph: Mapping[str, Sequence[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(slug: str) -> None:
        state[slug] = 1
        stack.append(slug)
        for dependency in graph.get(slug, []):
            if dependency not in graph:
                continue
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                cycles.add(canonical_cycle([*stack[start:], dependency]))
        stack.pop()
        state[slug] = 2

    for slug in sorted(graph):
        if state.get(slug, 0) == 0:
            visit(slug)
    return [[*list(cycle), cycle[0]] for cycle in sorted(cycles) if cycle]


def feature_relationships(feature: Mapping[str, Any], *, include_related: bool) -> dict[str, str]:
    relationships = {str(value): "blocks" for value in feature.get("dependencies", [])}
    if not include_related:
        return relationships
    for value in feature.get("related_dependencies", []):
        relationships.setdefault(str(value), "related")
    parent = feature.get("parent_feature")
    if parent:
        relationships.setdefault(str(parent), "related(parent)")
    return relationships


def feature_relationship_graph(
    features: Sequence[Mapping[str, Any]],
    *,
    include_related: bool,
) -> dict[str, list[str]]:
    return {
        str(feature["slug"]): sorted(feature_relationships(feature, include_related=include_related))
        for feature in features
    }


def dependency_cycles(features: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return graph_cycles(feature_relationship_graph(features, include_related=False))


def beads_traversal_cycles(features: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Return cycles across every feature relationship traversed by ``bd list``."""
    return graph_cycles(feature_relationship_graph(features, include_related=True))


def render_typed_cycle(cycle: Sequence[str], relationships: Mapping[tuple[str, str], str]) -> str:
    if not cycle:
        return ""
    rendered = [str(cycle[0])]
    for index in range(len(cycle) - 1):
        source = str(cycle[index])
        target = str(cycle[index + 1])
        rendered.append(f"-[{relationships.get((source, target), 'unknown')}]-> {target}")
    return " ".join(rendered)


def render_relationship_cycle(cycle: Sequence[str], features: Sequence[Mapping[str, Any]]) -> str:
    by_slug = {str(feature["slug"]): feature for feature in features}
    relationships = {
        (source, target): relation
        for source, feature in by_slug.items()
        for target, relation in feature_relationships(feature, include_related=True).items()
    }
    return render_typed_cycle(cycle, relationships)


def cycle_contains_edge(cycle: Sequence[str], source: str, target: str) -> bool:
    return any(cycle[index] == source and cycle[index + 1] == target for index in range(len(cycle) - 1))


def add_global_dependency_findings(features: list[dict[str, Any]]) -> list[list[str]]:
    blocking_cycles = dependency_cycles(features)
    traversal_cycles = beads_traversal_cycles(features)
    blocking_keys = {canonical_cycle(cycle) for cycle in blocking_cycles}
    findings = [(cycle, "Feature dependency cycle: " + " -> ".join(cycle)) for cycle in blocking_cycles]
    findings.extend(
        (
            cycle,
            "Feature Beads traversal cycle: " + render_relationship_cycle(cycle, features),
        )
        for cycle in traversal_cycles
        if canonical_cycle(cycle) not in blocking_keys
    )
    by_slug = {str(feature["slug"]): feature for feature in features}
    for cycle, message in findings:
        conflict_id = finding_id(message)
        for slug in cycle[:-1]:
            feature = by_slug[slug]
            resolution = feature.get("finding_resolutions", {}).get(conflict_id)
            if resolution is not None:
                feature.setdefault("resolved_conflicts", []).append(
                    {"id": conflict_id, "message": message, **resolution}
                )
                continue
            if message not in feature.setdefault("conflicts", []):
                feature["conflicts"].append(message)
            if feature.get("computed_classification") == "completed":
                feature["computed_classification"] = "needs_review"
                if not feature.get("classification_override"):
                    feature["classification"] = "needs_review"
    return traversal_cycles


def capture_hk_inventory(root: Path) -> dict[str, Any]:
    config = root / "hk.pkl"
    command = "pkl eval hk.pkl"
    if not config.is_file():
        return {"status": "absent", "command": command, "hooks": {}, "note": "No pre-adoption hk.pkl exists."}
    if shutil.which("pkl") is None:
        return {
            "status": "manual_confirmation_required",
            "command": command,
            "hooks": {},
            "note": "pkl is unavailable; manually confirm the hook and step inventory before mutation.",
        }
    try:
        result = subprocess.run(
            ["pkl", "eval", "-f", "json", "hk.pkl"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip())
        evaluated = json.loads(result.stdout)
        hooks: dict[str, dict[str, Any]] = {}
        for hook_name, hook in sorted(evaluated.get("hooks", {}).items()):
            steps = hook.get("steps", {}) if isinstance(hook, dict) else {}
            captured: dict[str, Any] = {}
            for step_name, step in sorted(steps.items()):
                semantic_step = {key: value for key, value in step.items() if key != "tests"}
                definition = json.dumps(semantic_step, sort_keys=True, separators=(",", ":"))
                captured[step_name] = {
                    "fingerprint": hashlib.sha256(definition.encode()).hexdigest(),
                    "definition": definition,
                }
            hooks[hook_name] = captured
        return {"status": "evaluable", "command": command, "hooks": hooks, "note": "Pkl evaluation passed."}
    except (json.JSONDecodeError, OSError, RuntimeError) as error:
        return {
            "status": "manual_confirmation_required",
            "command": command,
            "hooks": {},
            "note": f"hk.pkl could not be evaluated; manually confirm inventory before mutation: {error}",
        }


def hk_reconciliation_state(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    dispositions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    approved = {
        (str(item.get("hook")), str(item.get("step"))): item
        for item in dispositions
        if item.get("action") in {"remove", "replace"} and item.get("reason")
    }
    issues: list[dict[str, str]] = []
    if not baseline.get("status"):
        issues.append(
            {
                "kind": "missing_baseline_inventory",
                "message": "Pre-adoption hk inventory is missing; capture or manually confirm it before mutation.",
            }
        )
    elif baseline.get("status") == "manual_confirmation_required":
        issues.append({"kind": "manual_inventory_required", "message": str(baseline.get("note", ""))})
    elif baseline.get("status") in {"evaluable", "manually_confirmed"} and current.get("status") != "evaluable":
        issues.append({"kind": "current_inventory_unevaluable", "message": str(current.get("note", ""))})
    if baseline.get("status") in {"evaluable", "manually_confirmed"} and current.get("status") == "evaluable":
        for hook, old_steps in baseline.get("hooks", {}).items():
            new_steps = current.get("hooks", {}).get(hook, {})
            for step, old in old_steps.items():
                key = (str(hook), str(step))
                disposition = approved.get(key, {})
                if step not in new_steps and disposition.get("action") != "remove":
                    issues.append({"kind": "unapproved_step_loss", "hook": str(hook), "step": str(step)})
                elif (
                    step in new_steps
                    and old.get("fingerprint") != new_steps[step].get("fingerprint")
                    and not (
                        disposition.get("action") == "replace"
                        and disposition.get("candidate_fingerprint") == new_steps[step].get("fingerprint")
                    )
                ):
                    issues.append({"kind": "unresolved_step_collision", "hook": str(hook), "step": str(step)})
    return {
        "baseline": baseline,
        "current": current,
        "dispositions": list(dispositions),
        "issues": issues,
    }


RELEASE_TOOL_TOKENS = {
    "cog": ("cocogitto", "cog ", "cog.toml"),
    "semantic-release": ("semantic-release", "@semantic-release/"),
    "release-it": ("release-it",),
    "changesets": ("@changesets/", "changeset"),
    "goreleaser": ("goreleaser", ".goreleaser"),
}
RELEASE_SCAN_IGNORED_DIRS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "migration",
    "node_modules",
    "target",
    "vendor",
}


def _release_tool_for_text(text: str) -> set[str]:
    lowered = text.casefold()
    return {tool for tool, tokens in RELEASE_TOOL_TOKENS.items() if any(token in lowered for token in tokens)}


def detect_release_authorities(root: Path) -> list[dict[str, str]]:
    """Return bounded project-owned release configuration, execution, and documentation evidence."""
    authorities: dict[tuple[str, str, str], dict[str, str]] = {}

    def add(tool: str, kind: str, path: Path, detail: str) -> None:
        relative = path.relative_to(root).as_posix()
        key = (tool, kind, relative)
        authorities[key] = {
            "tool": tool,
            "kind": kind,
            "path": relative,
            "ownership": "project",
            "detail": detail,
        }

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in RELEASE_SCAN_IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and not path.is_symlink():
            files.append(path)
        if len(files) > 10_000:
            message = "Release-tool authority scan exceeded 10000 files"
            raise MigrationError(message)

    for path in files:
        relative = path.relative_to(root).as_posix()
        name = path.name.casefold()
        config_tool: str | None = None
        if name == "cog.toml":
            config_tool = "cog"
        elif name.startswith((".releaserc", "release.config.")):
            config_tool = "semantic-release"
        elif name.startswith(".release-it"):
            config_tool = "release-it"
        elif name.startswith(".goreleaser"):
            config_tool = "goreleaser"
        elif relative == ".changeset/config.json":
            config_tool = "changesets"
        if config_tool:
            add(config_tool, "config", path, "release configuration")

        if name == "package.json":
            try:
                package = json.loads(read_text(path))
            except (json.JSONDecodeError, OSError) as exc:
                message = f"Cannot inspect release dependencies in {relative}: {exc}"
                raise MigrationError(message) from exc
            for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                dependencies = package.get(section) if isinstance(package, dict) else None
                if not isinstance(dependencies, dict):
                    continue
                for dependency in dependencies:
                    for tool in _release_tool_for_text(str(dependency)):
                        add(tool, "dependency", path, f"{section}:{dependency}")
            scripts = package.get("scripts") if isinstance(package, dict) else None
            if isinstance(scripts, dict):
                for script, command in scripts.items():
                    if not isinstance(command, str):
                        continue
                    for tool in _release_tool_for_text(command):
                        add(tool, "package-script", path, f"scripts:{script}")

        inspect_kind: str | None = None
        if path.suffix.casefold() in {".yml", ".yaml"} and relative.startswith(".github/workflows/"):
            inspect_kind = "workflow"
        elif name in {"mise.toml", ".mise.toml"}:
            inspect_kind = "tooling"
        elif name in {"mise.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
            inspect_kind = "lock"
        elif path.suffix.casefold() in {".md", ".markdown"} or name.startswith("readme"):
            inspect_kind = "documentation"
        if inspect_kind:
            try:
                text = read_text(path)
            except UnicodeDecodeError:
                continue
            if inspect_kind != "documentation" or "release" in text.casefold():
                for tool in _release_tool_for_text(text):
                    add(tool, inspect_kind, path, "release authority reference")
    return [authorities[key] for key in sorted(authorities)]


def release_tooling_state(root: Path, decision: Mapping[str, Any] | None) -> dict[str, Any]:
    authorities = detect_release_authorities(root)
    executable_tools = {item["tool"] for item in authorities if item["kind"] != "documentation"}
    documented_tools = {item["tool"] for item in authorities if item["kind"] == "documentation"}
    normalized_decision = dict(decision) if isinstance(decision, Mapping) else None
    issues: list[dict[str, str]] = []
    if len(executable_tools) > 1 or documented_tools - executable_tools:
        issues.append(
            {
                "kind": "contradictory_release_tools",
                "message": "Release configuration, execution, and documentation identify contradictory authorities.",
            }
        )
    if normalized_decision is None:
        issues.append(
            {
                "kind": "missing_release_decision",
                "message": "Record whether to convert, retain, or remove the existing release authority.",
            }
        )
    else:
        action = normalized_decision.get("action")
        tool = normalized_decision.get("tool")
        reason = normalized_decision.get("reason")
        recorded_at = normalized_decision.get("recorded_at")
        try:
            recorded_time = datetime.fromisoformat(recorded_at) if isinstance(recorded_at, str) else None
        except ValueError:
            recorded_time = None
        if (
            action not in {"convert", "retain", "remove"}
            or not isinstance(tool, str)
            or not tool
            or not isinstance(reason, str)
            or not reason
            or recorded_time is None
            or recorded_time.tzinfo is None
        ):
            issues.append({"kind": "invalid_release_decision", "message": "Release decision is incomplete."})
        elif action == "convert" and tool != "cog":
            issues.append({"kind": "invalid_release_decision", "message": "Conversion target must be Cog."})
        elif action == "convert" and (executable_tools != {"cog"} or documented_tools != {"cog"}):
            issues.append(
                {"kind": "release_conversion_incomplete", "message": "Conversion requires Cog as the sole authority."}
            )
        elif action == "retain" and (tool == "cog" or executable_tools != {tool} or documented_tools != {tool}):
            issues.append(
                {
                    "kind": "retained_release_tool_conflict",
                    "message": "Retention requires one non-Cog authority with matching documentation.",
                }
            )
        elif action == "remove" and (tool in executable_tools or len(executable_tools) > 1):
            issues.append(
                {
                    "kind": "release_tool_removal_incomplete",
                    "message": "Removed release authority remains executable or another contradiction remains.",
                }
            )
    return {
        "authorities": authorities,
        "executable_tools": sorted(executable_tools),
        "documented_tools": sorted(documented_tools),
        "decision": normalized_decision,
        "issues": issues,
    }


def require_release_tool_reconciliation(manifest: Mapping[str, Any], *, root: Path | None = None) -> None:
    state = manifest.get("release_tooling")
    if root is not None and isinstance(state, Mapping):
        decision = state.get("decision")
        state = release_tooling_state(root, decision if isinstance(decision, Mapping) else None)
    if not isinstance(state, Mapping):
        message = "Release tooling reconciliation is missing from the migration manifest"
        raise MigrationError(message)
    issues = state.get("issues")
    if not isinstance(issues, list) or issues:
        kinds = ", ".join(sorted(str(item.get("kind", "issue")) for item in issues or []))
        suffix = f": {kinds}" if kinds else ""
        raise MigrationError("Release tooling reconciliation must be resolved before finalization" + suffix)


def set_release_tool_decision(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    action: str,
    tool: str,
    reason: str,
) -> None:
    if not reason.strip():
        message = "Release-tool decision requires a nonempty reason"
        raise MigrationError(message)
    decision = {
        "action": action,
        "tool": tool,
        "reason": reason.strip(),
        "recorded_at": utc_now(),
    }
    manifest["release_tooling"] = release_tooling_state(root, decision)
    save_manifest_and_report(root, manifest_path, report_path, manifest)


def build_manifest(
    root: Path,
    *,
    manifest_path: Path,
) -> dict[str, Any]:
    root / "docs/src"
    roadmap_entries, _ = parse_roadmap(root / ROADMAP_PATH)
    roadmap = {entry.slug: entry for entry in roadmap_entries}
    directories = existing_feature_dirs(root / FEATURES_PATH)
    summary_order = parse_summary_feature_order(root / SUMMARY_PATH)
    existing_manifest = load_json(root / manifest_path)

    ordered_slugs: list[str] = []
    existing_slugs = [
        str(feature["slug"])
        for feature in (existing_manifest or {}).get("features", [])
        if isinstance(feature, dict) and isinstance(feature.get("slug"), str)
    ]
    for slug in [entry.slug for entry in roadmap_entries] + summary_order + sorted(directories) + existing_slugs:
        if slug not in ordered_slugs:
            ordered_slugs.append(slug)
    known_slugs = set(ordered_slugs)
    existing_by_slug: dict[str, dict[str, Any]] = {}
    if existing_manifest:
        existing_by_slug = {
            feature["slug"]: feature
            for feature in existing_manifest.get("features", [])
            if isinstance(feature, dict) and isinstance(feature.get("slug"), str)
        }

    legacy_import_globally_complete = bool(
        existing_manifest
        and existing_manifest.get("beads_import_completed_at")
        and existing_by_slug
        and all(feature.get("beads", {}).get("state_applied") for feature in existing_by_slug.values())
    )

    features: list[dict[str, Any]] = []
    for slug in ordered_slugs:
        directory = directories.get(slug)
        source_dir = directory["path"] if directory else root / FEATURES_PATH / slug
        target_dir = root / FEATURES_PATH / slug
        active_dir = source_dir if source_dir.exists() else target_dir
        design_path = active_dir / "design.md"
        tasks_path = active_dir / "tasks.md"
        index_path = active_dir / "index.md"
        open_questions_path = active_dir / "OPEN_QUESTIONS.md"
        tasks = parse_tasks(tasks_path)
        design_status = parse_design_status(design_path)
        index_text = read_text(index_path) if index_path.exists() else ""
        entry = roadmap.get(slug)
        roadmap_status = entry.status if entry else ""
        roadmap_state = normalize_roadmap_status(roadmap_status)
        computed_classification, conflicts, evidence = status_conflicts(
            roadmap_state=roadmap_state,
            design_status=design_status,
            tasks=tasks,
            has_tasks_file=tasks_path.exists(),
            has_index=index_path.exists(),
            index_text=index_text,
        )
        if directory is None and roadmap_state not in {"planned", "deferred"}:
            conflicts.append("Roadmap entry has no feature directory or design.md")
        if entry is None:
            conflicts.append("Feature is retained from migration state but is not represented in planned-features.md")
        previous = existing_by_slug.get(slug, {})
        raw_dependency_slugs = [
            token for token in (entry.dependency_tokens if entry else []) if token in known_slugs and token != slug
        ]
        dependency_overrides = {
            str(key): value
            for key, value in previous.get("dependency_overrides", {}).items()
            if isinstance(value, dict)
        }
        dependency_slugs: list[str] = []
        related_dependency_slugs: list[str] = []
        removed_dependency_slugs: list[str] = []
        for dependency_slug in raw_dependency_slugs:
            relation = str(dependency_overrides.get(dependency_slug, {}).get("relation", "blocks"))
            if relation == "blocks":
                dependency_slugs.append(dependency_slug)
            elif relation == "related":
                related_dependency_slugs.append(dependency_slug)
            elif relation == "remove":
                removed_dependency_slugs.append(dependency_slug)
            else:
                conflicts.append(f"Invalid dependency override for {dependency_slug}: {relation!r}")
                dependency_slugs.append(dependency_slug)
        unresolved_dependency_tokens = [
            token for token in (entry.dependency_tokens if entry else []) if token not in known_slugs
        ]
        if unresolved_dependency_tokens:
            conflicts.append(
                "Roadmap dependency tokens do not resolve to known features: " + ", ".join(unresolved_dependency_tokens)
            )
        if open_questions_path.exists():
            conflicts.append(
                "Legacy OPEN_QUESTIONS.md remains; reconcile its durable content into design.md or Beads and remove it"
            )
        classification_override = previous.get("classification_override")
        if classification_override is not None and classification_override not in VALID_CLASSIFICATIONS:
            conflicts.append(
                f"Invalid classification override {classification_override!r}; using computed classification"
            )
            classification_override = None

        finding_resolutions = {
            str(key): value for key, value in previous.get("finding_resolutions", {}).items() if isinstance(value, dict)
        }
        unresolved_conflicts: list[str] = []
        resolved_conflicts: list[dict[str, Any]] = []
        for conflict in conflicts:
            conflict_id = finding_id(conflict)
            resolution = finding_resolutions.get(conflict_id)
            if resolution is None:
                unresolved_conflicts.append(conflict)
            else:
                resolved_conflicts.append(
                    {
                        "id": conflict_id,
                        "message": conflict,
                        **resolution,
                    }
                )
        conflicts = unresolved_conflicts

        # A feature is not migration-complete merely because old task and
        # roadmap evidence says it shipped. Only unresolved findings block
        # automatic closure; evidence-backed resolutions survive rescans.
        if (
            computed_classification == "needs_review"
            and roadmap_state == "completed"
            and evidence.get("completed_evidence")
            and not conflicts
        ):
            computed_classification = "completed"
        if computed_classification == "completed" and conflicts:
            computed_classification = "needs_review"
        classification = classification_override or computed_classification
        legacy_source_dirs = list(previous.get("legacy_source_dirs", []))
        previous_source = previous.get("source_dir")
        for candidate_source in (previous_source, str(source_dir.relative_to(root))):
            if (
                candidate_source
                and candidate_source != str(target_dir.relative_to(root))
                and candidate_source not in legacy_source_dirs
            ):
                legacy_source_dirs.append(candidate_source)
        beads_state = copy.deepcopy(previous.get("beads", {}))
        if beads_state.get("state_applied") and not beads_state.get("import_phase"):
            beads_state["import_phase"] = "completed" if legacy_import_globally_complete else "relationships"
        feature = {
            "slug": slug,
            "title": (entry.title if entry and entry.title else previous.get("title") or slug_title(slug)),
            "source_dir": str(source_dir.relative_to(root)),
            "legacy_source_dirs": legacy_source_dirs,
            "target_dir": str(target_dir.relative_to(root)),
            "design_path": str((target_dir / "design.md").relative_to(root)),
            "implemented_path": str((target_dir / "index.md").relative_to(root)),
            "legacy_tasks_path": str((target_dir / "tasks.md").relative_to(root)),
            "legacy_open_questions_path": str((target_dir / "OPEN_QUESTIONS.md").relative_to(root)),
            "roadmap_status": roadmap_status,
            "roadmap_state": roadmap_state,
            "design_status": design_status,
            "computed_classification": computed_classification,
            "classification_override": classification_override,
            "classification_override_reason": previous.get("classification_override_reason", ""),
            "classification": classification,
            "dependencies": dependency_slugs,
            "related_dependencies": related_dependency_slugs,
            "removed_dependencies": removed_dependency_slugs,
            "dependency_overrides": dependency_overrides,
            "parent_feature": entry.parent_feature if entry and entry.parent_feature in known_slugs else None,
            "raw_dependencies": entry.raw_dependencies if entry else "",
            "has_design": design_path.exists(),
            "has_tasks": tasks_path.exists(),
            "has_open_questions": open_questions_path.exists(),
            "has_index": index_path.exists(),
            "legacy_index_embeds_design": "{{#include design.md}}" in index_text,
            "legacy_index_embeds_tasks": "{{#include tasks.md}}" in index_text,
            "evidence": evidence,
            "conflicts": conflicts,
            "resolved_conflicts": resolved_conflicts,
            "finding_resolutions": finding_resolutions,
            "tasks": [task.as_dict() for task in tasks],
            "beads": beads_state,
            "migration_decisions": previous.get("migration_decisions", []),
            "legacy_tasks_archive": previous.get("legacy_tasks_archive"),
        }
        features.append(feature)

    add_global_dependency_findings(features)
    legacy_task_files = sum(bool(feature.get("has_tasks")) for feature in features)
    parsed_task_files = sum(bool(feature.get("has_tasks") and feature.get("tasks")) for feature in features)
    parsed_tasks = sum(len(feature.get("tasks", [])) for feature in features)
    baseline_record = load_json(root / DEFAULT_BASELINE_JSON) or {}
    current_hk = capture_hk_inventory(root)
    previous_hk = (existing_manifest or {}).get("hk_reconciliation", {})
    baseline_hk = previous_hk.get("baseline") or baseline_record.get("hk")
    if not isinstance(baseline_hk, dict):
        baseline_hk = (
            current_hk
            if current_hk.get("status") == "absent"
            else {
                "status": "manual_confirmation_required",
                "command": "pkl eval hk.pkl",
                "hooks": {},
                "note": "Pre-adoption hk inventory is missing; confirm it manually before further mutation.",
            }
        )
    dispositions = [item for item in previous_hk.get("dispositions", []) if isinstance(item, dict)]

    had_artifact_state = bool(existing_manifest and "artifacts" in existing_manifest)
    previous_artifacts = (existing_manifest or {}).get("artifacts", {})
    backup_exists = (root / TEMPLATE_BACKUP_DIR).exists()
    backup_disposition = previous_artifacts.get("backup_disposition")
    if (not had_artifact_state and existing_manifest) or (
        backup_exists and backup_disposition not in {"retain", "remove"}
    ):
        backup_disposition = "unresolved"
    elif not backup_exists and backup_disposition not in {"retain", "remove", "unresolved"}:
        backup_disposition = "not_applicable"
    previous_release_tooling = (existing_manifest or {}).get("release_tooling", {})
    previous_release_decision = (
        previous_release_tooling.get("decision") if isinstance(previous_release_tooling, Mapping) else None
    )
    manifest = {
        **(existing_manifest or {}),
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_workflow": "legacy-markdown-feature-workflow",
        # Keep the committed manifest portable across clones and worktrees.
        "root": ".",
        "manifest_path": str(manifest_path),
        "migration_prepared": bool(existing_manifest and existing_manifest.get("migration_prepared")),
        "beads_import_started": bool(existing_manifest and existing_manifest.get("beads_import_started")),
        "beads_import_started_at": (existing_manifest or {}).get("beads_import_started_at"),
        "beads_import_completed_at": (existing_manifest or {}).get("beads_import_completed_at"),
        "beads_import_progress": (existing_manifest or {}).get("beads_import_progress", {}),
        "delivered_record_candidates": (existing_manifest or {}).get("delivered_record_candidates", []),
        "migration_finalized": bool(existing_manifest and existing_manifest.get("migration_finalized")),
        "inventory": {
            "legacy_task_files": legacy_task_files,
            "parsed_task_files": parsed_task_files,
            "unparsed_task_files": legacy_task_files - parsed_task_files,
            "parsed_tasks": parsed_tasks,
        },
        "hk_reconciliation": hk_reconciliation_state(baseline_hk, current_hk, dispositions),
        "release_tooling": release_tooling_state(root, previous_release_decision),
        "checkpoint_evidence": (existing_manifest or {}).get("checkpoint_evidence", []),
        "artifacts": {
            **previous_artifacts,
            "candidate_directory": str(TEMPLATE_CANDIDATE_DIR),
            "candidate_present": (root / TEMPLATE_CANDIDATE_DIR).exists(),
            "backup_directory": str(TEMPLATE_BACKUP_DIR),
            "backup_present": backup_exists,
            "backup_disposition": backup_disposition,
        },
        "features": features,
    }
    if existing_manifest:
        comparable_manifest = {key: value for key, value in manifest.items() if key != "generated_at"}
        comparable_existing = {key: value for key, value in existing_manifest.items() if key != "generated_at"}
        if comparable_manifest == comparable_existing:
            manifest["generated_at"] = existing_manifest.get("generated_at", manifest["generated_at"])
    return manifest


def render_report(manifest: Mapping[str, Any]) -> str:
    features = manifest.get("features", [])
    counts: dict[str, int] = {}
    conflict_count = 0
    task_count = 0
    for feature in features:
        classification = str(feature.get("classification", "unknown"))
        counts[classification] = counts.get(classification, 0) + 1
        conflict_count += len(feature.get("conflicts", []))
        task_count += len(feature.get("tasks", []))

    lines = [
        "<!-- rumdl-disable MD013 -->",
        "",
        "# Legacy Workflow Migration Report",
        "",
        f"Generated: `{manifest.get('generated_at', '')}`",
        "",
        "## Inventory",
        "",
        f"- Features: {len(features)}",
        f"- Legacy task files: {manifest.get('inventory', {}).get('legacy_task_files', 0)}",
        f"- Parsed task files: {manifest.get('inventory', {}).get('parsed_task_files', 0)}",
        f"- Unparsed task files: {manifest.get('inventory', {}).get('unparsed_task_files', 0)}",
        f"- Parsed legacy tasks: {task_count}",
        f"- Reconciliation findings: {conflict_count}",
    ]
    for key in sorted(counts):
        lines.append(f"- `{key}`: {counts[key]}")
    release_state = manifest.get("release_tooling", {})
    release_decision = release_state.get("decision") or {}
    lines.extend(
        [
            "",
            "## Release Tooling Reconciliation",
            "",
            "- Executable authorities: "
            + (", ".join(f"`{tool}`" for tool in release_state.get("executable_tools", [])) or "none"),
            "- Documented authorities: "
            + (", ".join(f"`{tool}`" for tool in release_state.get("documented_tools", [])) or "none"),
            f"- Decision: `{release_decision.get('action', 'missing')}` `{release_decision.get('tool', '')}`",
            f"- Decision reason: {release_decision.get('reason') or '—'}",
            f"- Blocking issues: {len(release_state.get('issues', []))}",
            "",
            "### Detected authorities",
            "",
        ]
    )
    for authority in release_state.get("authorities", []):
        lines.append(
            f"- `{authority.get('tool')}` `{authority.get('kind')}` `{authority.get('path')}` "
            f"ownership=`{authority.get('ownership')}` — {authority.get('detail')}"
        )
    if not release_state.get("authorities"):
        lines.append("- None detected.")
    for issue in release_state.get("issues", []):
        lines.append(f"- BLOCKED `{issue.get('kind')}`: {issue.get('message')}")
    hk_state = manifest.get("hk_reconciliation", {})
    baseline_hk = hk_state.get("baseline", {})
    current_hk = hk_state.get("current", {})
    lines.extend(
        [
            "",
            "## hk Reconciliation",
            "",
            f"- Baseline status: `{baseline_hk.get('status', 'missing')}`",
            f"- Current status: `{current_hk.get('status', 'missing')}`",
            f"- Recorded dispositions: {len(hk_state.get('dispositions', []))}",
            f"- Blocking inventory issues: {len(hk_state.get('issues', []))}",
        ]
    )
    for issue in hk_state.get("issues", []):
        location = "/".join(str(issue.get(key, "")) for key in ("hook", "step") if issue.get(key))
        location_text = f" `{location}`" if location else ""
        message = issue.get("message", "reconciliation required")
        lines.append(f"- `{issue.get('kind', 'unknown')}`{location_text}: {message}")
    artifacts = manifest.get("artifacts", {})
    lines.extend(
        [
            "",
            "## Artifact Lifecycle",
            "",
            f"- Temporary candidates present: {bool(artifacts.get('candidate_present'))}",
            f"- Conditional backup present: {bool(artifacts.get('backup_present'))}",
            f"- Backup disposition: `{artifacts.get('backup_disposition', 'unresolved')}`",
            f"- Backup disposition reason: {artifacts.get('backup_disposition_reason') or '—'}",
            "",
            "## Checkpoint Evidence",
            "",
        ]
    )
    for item in manifest.get("checkpoint_evidence", []):
        lines.append(
            f"- `{item.get('hook', 'unknown')}` `{item.get('status', 'unknown')}` — "
            f"`{item.get('command', '')}` — {item.get('reason') or 'ordinary verified checkpoint'}"
        )
    if not manifest.get("checkpoint_evidence"):
        lines.append("- No checkpoint evidence recorded.")
    lines.extend(["", "## Feature Mapping", ""])
    for feature in features:
        design_status = str(feature.get("design_status", "")).replace("|", "\\|")
        roadmap_status = str(feature.get("roadmap_status", "")).replace("|", "\\|")
        classification = str(feature["classification"])
        if feature.get("classification_override"):
            classification += " (override)"
        lines.extend(
            [
                f"- **Feature:** `{feature['slug']}`",
                f"  - Target: `{feature['slug']}`",
                f"  - Classification: `{classification}`",
                f"  - Roadmap: {roadmap_status or '—'}",
                f"  - Design: {design_status or '—'}",
                f"  - Index: {'yes' if feature.get('has_index') else 'no'}",
                f"  - Findings: {len(feature.get('conflicts', []))}",
            ]
        )

    lines.extend(["", "## Reconciliation Findings", ""])
    for feature in features:
        conflicts = feature.get("conflicts", [])
        if not conflicts and not feature.get("classification_override"):
            continue
        lines.append(f"### {feature['title']} (`{feature['slug']}`)")
        lines.append("")
        for conflict in conflicts:
            lines.append(f"- `finding:{finding_id(str(conflict))}` — {conflict}")
        if feature.get("classification_override"):
            lines.append(
                "- Classification override: `{}` — {}".format(
                    feature["classification_override"],
                    feature.get("classification_override_reason") or "no reason recorded",
                )
            )
        lines.append("")

    resolved = [(feature, finding) for feature in features for finding in feature.get("resolved_conflicts", [])]
    if resolved:
        lines.extend(["## Resolved Findings", ""])
        for feature, finding in resolved:
            lines.append(
                f"- `{feature['slug']}` "
                f"`finding:{finding['id']}` — {finding['message']} "
                f"— {finding.get('reason', 'no reason recorded')}"
            )
        lines.append("")

    candidates = [
        candidate for candidate in manifest.get("delivered_record_candidates", []) if isinstance(candidate, Mapping)
    ]
    if candidates:
        lines.extend(["## Delivered-Record Reviews", ""])
        for candidate in candidates:
            reviewed = bool(candidate.get("reviewed"))
            lines.extend(
                [
                    f"- **Feature:** `{candidate.get('slug', '')}`",
                    f"  - Candidate: `{candidate.get('path', '')}`",
                    f"  - Status: `{'reviewed' if reviewed else 'pending'}`",
                ]
            )
            if reviewed:
                lines.append(f"  - Reviewed at: `{candidate.get('reviewed_at', '')}`")
                reason = " ".join(str(candidate.get("review_reason", "")).split())
                summary = " ".join(str(candidate.get("semantic_summary", "")).split())
                if reason:
                    lines.append(f"  - Review reason: {reason}")
                if summary:
                    lines.append(f"  - Semantic summary: {summary}")

    lines.extend(
        [
            "## Migration Stages",
            "",
            "1. Review this report and confirm the feature slug mapping.",
            "2. Use `classify` and `resolve-findings` to record evidence-backed decisions before import.",
            "3. Run `prepare --apply` to rename feature paths and rewrite links.",
            "4. Run `import-beads --apply` to create Beads state.",
            "5. Use `/migrate-workflow` to reconcile designs, delivered records, and status conflicts.",
            "6. Run `finalize --apply` only after no page includes or links to `tasks.md`.",
            "7. Run `verify --beads` and the normal project checks.",
            "",
        ]
    )
    return "\n".join(lines)


def save_manifest_and_report(root: Path, manifest_path: Path, report_path: Path, manifest: Mapping[str, Any]) -> None:
    current = dict(manifest)
    existing = load_json(root / manifest_path)
    if existing is None:
        current["generated_at"] = current.get("generated_at") or utc_now()
    else:
        existing_semantics = {key: value for key, value in existing.items() if key != "generated_at"}
        current_semantics = {key: value for key, value in current.items() if key != "generated_at"}
        if current_semantics != existing_semantics:
            current["generated_at"] = utc_now()
        else:
            current["generated_at"] = existing.get("generated_at") or current.get("generated_at") or utc_now()
    if isinstance(manifest, dict):
        manifest.clear()
        manifest.update(current)
    dump_compact_json(root / manifest_path, current)
    write_text(root / report_path, render_report(current))


def print_scan_summary(manifest: Mapping[str, Any]) -> None:
    features = manifest.get("features", [])
    conflict_count = sum(len(feature.get("conflicts", [])) for feature in features)
    task_count = sum(len(feature.get("tasks", [])) for feature in features)
    inventory = manifest.get("inventory", {})
    print(f"Features: {len(features)}")
    print(f"Legacy task files: {inventory.get('legacy_task_files', 0)}")
    print(f"Parsed task files: {inventory.get('parsed_task_files', 0)}")
    print(f"Unparsed task files: {inventory.get('unparsed_task_files', 0)}")
    print(f"Parsed legacy tasks: {task_count}")
    print(f"Reconciliation findings: {conflict_count}")
    for feature in features:
        suffix = " override" if feature.get("classification_override") else ""
        print(
            f"  {feature['slug']}: {feature['classification']}{suffix} ({len(feature.get('conflicts', []))} findings)"
        )


def _compile_literal_replacements(
    replacements: Mapping[str, str],
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    ordered = sorted(replacements.items(), key=lambda item: (-len(item[0]), item[0]))
    if not ordered:
        return None, {}
    pattern = re.compile("|".join(re.escape(old) for old, _ in ordered))
    return pattern, dict(ordered)


def _apply_literal_replacements(
    text: str,
    compiled: tuple[re.Pattern[str] | None, Mapping[str, str]],
) -> str:
    pattern, replacements = compiled
    if pattern is None:
        return text
    return pattern.sub(lambda match: replacements[match.group(0)], text)


def _feature_path_replacements(
    mapping: Mapping[str, str],
    *,
    rewrite_sibling_links: bool,
) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for slug in mapping:
        target = mapping[slug]
        replacements.update(
            {
                f"docs/src/features/{slug}/": f"docs/src/features/{target}/",
                f"docs/src/features/{slug}`": f"docs/src/features/{target}`",
                f"features/{slug}/": f"features/{target}/",
                f"feat/{slug}": f"feat/{target}",
            }
        )
        if rewrite_sibling_links:
            replacements.update(
                {
                    f"../{slug}/": f"../{target}/",
                    f"./{slug}/": f"./{target}/",
                    f"({slug}/": f"({target}/",
                    f"<{slug}/": f"<{target}/",
                }
            )
    return replacements


def replace_feature_paths(
    text: str,
    mapping: Mapping[str, str],
    *,
    rewrite_sibling_links: bool,
) -> str:
    """Rewrite references that are structurally known to target feature paths.

    Avoid broad ``/<slug>/`` replacement: a feature slug may also be an API,
    package, or deployment path elsewhere in project documentation. Relative
    sibling forms are rewritten only inside ``docs/src/features``. All literals
    are applied in one pass so a target slug cannot be rewritten again as a
    source slug.
    """

    compiled = _compile_literal_replacements(
        _feature_path_replacements(mapping, rewrite_sibling_links=rewrite_sibling_links)
    )
    return _apply_literal_replacements(text, compiled)


def rewrite_roadmap_headings(
    text: str,
    feature_by_slug: Mapping[str, Mapping[str, str]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        slug = match.group("slug")
        feature = feature_by_slug.get(slug)
        if feature is None:
            return match.group(0)
        title = str(feature.get("title") or match.group("title") or slug_title(slug)).strip()
        return f"### {title} (`{slug}`)"

    updated = ROADMAP_HEADING_RE.sub(replace, text)
    return re.sub(r"(### .+?\(`[^`]+`\))\n(?=-\s)", r"\1\n\n", updated)


SUMMARY_CONCERN_SPECS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("Introduction", ("Introduction",), "introduction", "Introduction"),
    ("Architecture", ("Architecture", "Architecture Design"), "architecture", "Architecture Overview"),
    ("Operator's Manual", ("Operator's Manual", "Operations", "Usage Guide"), "operations", "Operations Overview"),
    ("Development Guide", ("Development Guide", "Development"), "development", "Development Overview"),
    ("Reference", ("Reference",), "reference", "Reference Overview"),
)


def normalized_h1_headings(text: str) -> set[str]:
    return {re.sub(r"\s+", " ", line[2:].strip()).casefold() for line in text.splitlines() if line.startswith("# ")}


def concern_target(root: Path, folder: str) -> tuple[Path, bool]:
    docs_src = root / "docs/src"
    candidates = (
        docs_src / folder / "index.md",
        docs_src / f"{folder}.md",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate, False
    directory = docs_src / folder
    if directory.is_dir():
        existing = sorted(path for path in directory.rglob("*.md") if path.is_file())
        if existing:
            return existing[0], False
    return docs_src / folder / "index.md", True


def ensure_summary_concerns(root: Path, text: str, *, apply: bool) -> tuple[str, list[Path]]:
    headings = normalized_h1_headings(text)
    blocks: list[str] = []
    created_pages: list[Path] = []
    for heading, aliases, folder, link_title in SUMMARY_CONCERN_SPECS:
        if any(alias.casefold() in headings for alias in aliases):
            continue
        target, missing = concern_target(root, folder)
        if missing:
            created_pages.append(target)
            if apply:
                write_text(
                    target,
                    f"# {link_title}\n\n"
                    "<!-- workflow-migration:generated-navigation-page -->\n\n"
                    "This navigation page was created during workflow migration. "
                    "Reconcile it with the project's durable reader-facing documentation "
                    "before declaring migration complete.\n",
                )
        relative = target.relative_to(root / "docs/src").as_posix()
        blocks.append(f"# {heading}\n\n- [{link_title}]({relative})")
        headings.add(heading.casefold())
    if not blocks:
        return text.rstrip() + "\n", created_pages
    return text.rstrip() + "\n\n" + "\n\n".join(blocks) + "\n", created_pages


def ensure_summary_markers(text: str) -> str:
    if MARKER_START in text and MARKER_END in text:
        return text.rstrip() + "\n"
    lines = text.splitlines()
    implemented_index: int | None = None
    for index, line in enumerate(lines):
        if re.match(
            r"^\s*-\s+\[Implemented Features\]\(features/index\.md\)\s*$",
            line,
            re.IGNORECASE,
        ):
            implemented_index = index
            break

    if implemented_index is None:
        reference_index: int | None = None
        for index, line in enumerate(lines):
            if line.startswith("# ") and line[2:].strip().casefold() == "reference":
                reference_index = index
                break
        if reference_index is None:
            while lines and not lines[-1].strip():
                lines.pop()
            if lines:
                lines.append("")
            lines.extend(["# Reference", ""])
            reference_index = len(lines) - 2

        insert_at = reference_index + 1
        while insert_at < len(lines) and not (lines[insert_at].startswith("# ") and insert_at > reference_index):
            insert_at += 1
        while insert_at > reference_index + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        block = [
            "- [Implemented Features](features/index.md)",
            "  " + MARKER_START,
            "  " + MARKER_END,
            "",
        ]
        lines[insert_at:insert_at] = block
        return "\n".join(lines).rstrip() + "\n"

    child_start = implemented_index + 1
    child_end = child_start
    while child_end < len(lines):
        line = lines[child_end]
        if not line.strip():
            child_end += 1
            continue
        if re.match(r"^\s{2,}-\s+\[", line):
            child_end += 1
            continue
        break
    lines.insert(child_start, "  " + MARKER_START)
    child_end += 1
    lines.insert(child_end, "  " + MARKER_END)
    return "\n".join(lines).rstrip() + "\n"


def replace_marker_body(text: str, entries: Sequence[str], *, indent: str = "") -> str:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if MARKER_START in line)
    end = next(index for index, line in enumerate(lines[start + 1 :], start + 1) if MARKER_END in line)
    return "\n".join([*lines[: start + 1], *(indent + entry for entry in entries), *lines[end:]]).rstrip() + "\n"


def delivered_navigation(manifest: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    delivered = [
        feature
        for feature in manifest.get("features", [])
        if feature.get("has_index") and feature.get("classification") == "completed"
    ]
    summary = [f"- [{feature['title']}](features/{feature['slug']}/index.md)" for feature in delivered]
    feature_index = [f"- [{feature['title']}]({feature['slug']}/index.md)" for feature in delivered]
    return summary, feature_index


def ensure_feature_index_markers(text: str) -> str:
    if MARKER_START in text and MARKER_END in text:
        return text.rstrip() + "\n"
    lines = text.splitlines()
    if not any(line.startswith("# ") for line in lines):
        lines = ["# Implemented features", "", *lines]
    bullet_indices = [
        index for index, line in enumerate(lines) if re.match(r"^-\s+\[[^]]+\]\([^)]*index\.md\)\s*$", line)
    ]
    if not bullet_indices:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(["", MARKER_START, "", MARKER_END])
    else:
        start = bullet_indices[0]
        end = bullet_indices[-1] + 1
        before = lines[:start]
        bullets = lines[start:end]
        after = lines[end:]
        while before and not before[-1].strip():
            before.pop()
        while after and not after[0].strip():
            after.pop(0)
        lines = [*before, "", MARKER_START, "", *bullets, "", MARKER_END]
        if after:
            lines.extend(["", *after])
    return "\n".join(lines).rstrip() + "\n"


def ensure_feature_lifecycle_link(text: str) -> str:
    target = "development/feature-lifecycle.md"
    if target in text:
        return text
    lines = text.splitlines()
    section_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip() in {"# Development Guide", "# Development"}:
            section_index = index
            break
    if section_index is None:
        return text
    insert_at = section_index + 1
    while insert_at < len(lines) and not (lines[insert_at].startswith("# ") and insert_at > section_index):
        insert_at += 1
    while insert_at > section_index + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, "- [Feature Lifecycle](development/feature-lifecycle.md)")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def primary_checkout(root: Path) -> bool:
    if not git_repository(root):
        return True
    output = git_output(root, "worktree", "list", "--porcelain")
    first = next((line.removeprefix("worktree ") for line in output.splitlines() if line.startswith("worktree ")), "")
    return bool(first) and Path(first).resolve() == root.resolve()


def require_formula_only_beads(root: Path) -> None:
    beads_dir = root / ".beads"
    formula = beads_dir / "formulas/dstack-feature.formula.toml"
    if (
        not beads_dir.is_dir()
        or beads_dir.is_symlink()
        or any(path.is_symlink() for path in beads_dir.rglob("*"))
        or any(path.name != "formulas" for path in beads_dir.iterdir())
        or not formula.is_file()
    ):
        msg = "Native Beads initialization requires a nonsymlinked formula-only .beads directory"
        raise MigrationError(msg)


def ensure_bd_available(root: Path, *, init_beads: bool) -> None:
    local_controls_exist = (root / ".beads/metadata.json").is_file() and (root / ".beads/config.yaml").is_file()
    if shutil.which("bd") is None:
        if not local_controls_exist and not init_beads:
            msg = "Beads is not repository-locally initialized; run beads-authority --init from the primary checkout."
            raise MigrationError(msg)
        msg = "The 'bd' command is not installed"
        raise MigrationError(msg)
    try:
        validate_beads_authority(root)
        return
    except MigrationError as authority_error:
        if local_controls_exist:
            raise authority_error
        if not init_beads:
            msg = "Beads is not repository-locally initialized; run beads-authority --init from the primary checkout."
            raise MigrationError(msg) from authority_error

    if not primary_checkout(root):
        msg = (
            "Native initialization cannot publish collaborative controls from a linked worktree; initialize Beads "
            "from the primary checkout on the dedicated migration branch."
        )
        raise MigrationError(msg)
    require_formula_only_beads(root)
    prefix = canonical_project_slug(root)
    before = git_output(root, "rev-parse", "HEAD") if git_repository(root) else ""
    run_command(
        ["bd", "init", "--non-interactive", "--skip-agents", "--skip-hooks", "--prefix", prefix],
        cwd=root,
    )
    validate_beads_authority(root)
    if before:
        after = git_output(root, "rev-parse", "HEAD")
        if after == before:
            msg = "Native bd init did not create its collaborative-control commit"
            raise MigrationError(msg)
        changed = set(git_output(root, "diff-tree", "--no-commit-id", "--name-only", "-r", before, after).splitlines())
        allowed = {str(path) for path in BEADS_TRACKED_CONTROL_PATHS} | {".gitignore"}
        unexpected = sorted(changed - allowed)
        if unexpected:
            raise MigrationError("Native bd init committed unexpected project paths: " + ", ".join(unexpected))
        print(f"Native bd init created {after}; inspect and amend it through normal project hooks.")


def selected_features(manifest: Mapping[str, Any], requested: Sequence[str]) -> list[dict[str, Any]]:
    features = [feature for feature in manifest.get("features", []) if isinstance(feature, dict)]
    if not requested:
        return features
    requested_set = set(requested)
    selected = [feature for feature in features if feature.get("slug") in requested_set]
    missing = requested_set - {str(feature.get("slug")) for feature in selected}
    if missing:
        raise MigrationError("Unknown requested features: " + ", ".join(sorted(missing)))
    return selected


def set_classification(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    requested: str,
    classification: str,
    reason: str,
) -> None:
    selected = selected_features(manifest, [requested])
    feature = selected[0]
    if feature.get("beads", {}).get("state_applied"):
        msg = (
            "The feature has already had migration state applied in Beads. "
            "Reconcile the Beads state directly and record the decision in the migration task."
        )
        raise MigrationError(msg)

    if classification == "auto":
        feature["classification_override"] = None
        feature["classification_override_reason"] = ""
        feature["classification"] = feature.get("computed_classification", "needs_review")
        action = "Cleared"
    else:
        if classification not in VALID_CLASSIFICATIONS:
            msg = f"Unsupported classification: {classification}"
            raise MigrationError(msg)
        if not reason.strip():
            msg = "--reason is required when setting a classification override"
            raise MigrationError(msg)
        feature["classification_override"] = classification
        feature["classification_override_reason"] = reason.strip()
        feature["classification"] = classification
        action = "Set"

    feature.setdefault("migration_decisions", []).append(
        {
            "at": utc_now(),
            "kind": "classification_override",
            "value": None if classification == "auto" else classification,
            "reason": reason.strip(),
        }
    )
    save_manifest_and_report(root, manifest_path, report_path, manifest)
    print(f"{action} classification override for {feature['slug']}.")


def set_dependency_relation(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    requested: str,
    dependency_requested: str,
    relation: str,
    reason: str,
) -> None:
    feature = selected_features(manifest, [requested])[0]
    dependency = selected_features(manifest, [dependency_requested])[0]
    if feature["slug"] == dependency["slug"]:
        msg = "A feature cannot depend on or relate to itself"
        raise MigrationError(msg)
    if not reason.strip():
        msg = "--reason is required when changing a dependency relation"
        raise MigrationError(msg)

    decided_at = utc_now()
    candidate_manifest = copy.deepcopy(manifest)
    candidate_feature = selected_features(candidate_manifest, [requested])[0]
    candidate_dependency = selected_features(candidate_manifest, [dependency_requested])[0]
    overrides = candidate_feature.setdefault("dependency_overrides", {})
    overrides[candidate_dependency["slug"]] = {
        "relation": relation,
        "reason": reason.strip(),
        "decided_at": decided_at,
    }
    known = {
        str(value)
        for field_name in ("dependencies", "related_dependencies", "removed_dependencies")
        for value in candidate_feature.get(field_name, [])
    }
    known.add(str(candidate_dependency["slug"]))
    candidate_feature["dependencies"] = sorted(
        value for value in known if str(overrides.get(value, {}).get("relation", "blocks")) == "blocks"
    )
    candidate_feature["related_dependencies"] = sorted(
        value for value in known if str(overrides.get(value, {}).get("relation", "blocks")) == "related"
    )
    candidate_feature["removed_dependencies"] = sorted(
        value for value in known if str(overrides.get(value, {}).get("relation", "blocks")) == "remove"
    )
    candidate_feature.setdefault("migration_decisions", []).append(
        {
            "at": decided_at,
            "kind": "dependency_relation",
            "dependency": candidate_dependency["slug"],
            "relation": relation,
            "reason": reason.strip(),
        }
    )
    for item in candidate_manifest.get("features", []):
        item["conflicts"] = [
            conflict for conflict in item.get("conflicts", []) if not str(conflict).startswith(CYCLE_CONFLICT_PREFIXES)
        ]
    add_global_dependency_findings(candidate_manifest["features"])

    source_slug = str(candidate_feature["slug"])
    target_slug = str(candidate_dependency["slug"])
    offending_cycles = [
        cycle
        for cycle in beads_traversal_cycles(candidate_manifest["features"])
        if cycle_contains_edge(cycle, source_slug, target_slug)
    ]
    if relation != "remove" and offending_cycles:
        rendered = "; ".join(
            render_relationship_cycle(cycle, candidate_manifest["features"]) for cycle in offending_cycles
        )
        hint = (
            "`bd list` traverses `related` edges, so use `remove` or correct the roadmap direction instead."
            if relation == "related"
            else "Use `remove` or correct the roadmap direction instead."
        )
        msg = (
            f"Cannot set this relationship to {relation}: it participates in a Beads traversal cycle: "
            f"{rendered}. {hint}"
        )
        raise MigrationError(msg)

    if manifest.get("beads_import_started"):
        issue_id = str(feature.get("beads", {}).get("root_id") or "")
        depends_on = str(dependency.get("beads", {}).get("root_id") or "")
        if not issue_id or not depends_on:
            msg = (
                "Cannot reconcile an imported dependency until both feature root IDs are recorded in the migration "
                "manifest. Rerun import-beads recovery first."
            )
            raise MigrationError(msg)
        reconcile_bd_relation(root, issue_id=issue_id, depends_on=depends_on, relation=relation)

    manifest.clear()
    manifest.update(candidate_manifest)
    save_manifest_and_report(root, manifest_path, report_path, manifest)
    print(f"Set {feature['slug']} -> {dependency['slug']} as {relation}.")


def resolve_findings(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    requested: str,
    finding_ids: Sequence[str],
    resolve_all: bool,
    reason: str,
) -> None:
    feature = selected_features(manifest, [requested])[0]
    if not reason.strip():
        msg = "--reason is required when resolving migration findings"
        raise MigrationError(msg)
    conflicts = [str(item) for item in feature.get("conflicts", [])]
    available = {finding_id(message): message for message in conflicts}
    selected_ids = set(available) if resolve_all else set(finding_ids)
    if not selected_ids:
        msg = "Select at least one --finding ID or pass --all"
        raise MigrationError(msg)
    unknown = selected_ids - set(available)
    if unknown:
        raise MigrationError("Unknown unresolved finding IDs for this feature: " + ", ".join(sorted(unknown)))
    resolutions = feature.setdefault("finding_resolutions", {})
    resolved_at = utc_now()
    for conflict_id in sorted(selected_ids):
        resolutions[conflict_id] = {
            "resolved_at": resolved_at,
            "reason": reason.strip(),
        }
    feature["conflicts"] = [message for message in conflicts if finding_id(message) not in selected_ids]
    feature.setdefault("migration_decisions", []).append(
        {
            "at": resolved_at,
            "kind": "finding_resolution",
            "finding_ids": sorted(selected_ids),
            "reason": reason.strip(),
        }
    )
    save_manifest_and_report(root, manifest_path, report_path, manifest)
    print(f"Resolved {len(selected_ids)} migration finding(s) for {feature['slug']}.")


def feature_import_completed(feature: Mapping[str, Any]) -> bool:
    return feature.get("beads", {}).get("import_phase") == "completed"


def import_progress(features: Sequence[Mapping[str, Any]], *, recovered: int = 0) -> dict[str, int]:
    completed = sum(feature_import_completed(feature) for feature in features)
    existing = sum(bool(feature.get("beads", {}).get("root_id")) for feature in features)
    conflicting = sum(bool(feature.get("conflicts")) for feature in features)
    return {
        "existing": existing,
        "recovered": recovered,
        "pending": len(features) - existing,
        "conflicting": conflicting,
        "completed": completed,
        "remaining": len(features) - completed,
        "total": len(features),
    }


def print_import_progress(progress: Mapping[str, int], *, prefix: str = "  - ") -> None:
    print(
        prefix
        + ", ".join(
            f"{key}: {progress[key]}"
            for key in ("existing", "recovered", "pending", "conflicting", "completed", "remaining", "total")
        )
    )


def flush_bd_batch(root: Path, message: str) -> None:
    run_command(["bd", "dolt", "commit", "-m", message], cwd=root, allow_existing=True)


def import_beads(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    apply: bool,
    init_beads: bool,
    requested: Sequence[str],
    batch_size: int,
) -> None:
    requested_features = selected_features(manifest, requested)
    all_features = manifest["features"]
    features = requested_features
    if apply:
        incomplete = [feature for feature in requested_features if not feature_import_completed(feature)]
        incomplete.sort(key=lambda feature: bool(feature.get("beads", {}).get("state_applied")))
        features = incomplete[:batch_size]
    formula = load_formula(root)
    preflight_import(manifest, formula)
    ensure_bd_available(root, init_beads=init_beads if apply else False)
    if not apply:
        preview_features = copy.deepcopy(all_features)
        recovered_issues = reconcile_existing_beads_state(root, preview_features, canonicalize=False)
        print("Beads import dry-run (no mutations):")
        print_import_progress(import_progress(preview_features, recovered=recovered_issues))
        print("  - run a separate command with --apply to execute")
        return

    set_batch_active(True)
    print(
        f"APPLY STARTED: importing a bounded partition of {len(features)} feature(s) "
        "into Beads with durable batch commits."
    )
    print_import_progress(import_progress(all_features))
    recovered_issues = reconcile_existing_beads_state(root, all_features, canonicalize=True)
    if recovered_issues:
        save_manifest_and_report(root, manifest_path, report_path, manifest)
        print(f"Recovered migration identities for {recovered_issues} feature(s).")
    manifest["beads_import_started"] = True
    manifest["beads_import_started_at"] = manifest.get("beads_import_started_at") or utc_now()

    for feature in features:
        beads = feature.setdefault("beads", {})
        root_id = beads.get("root_id")
        if feature_import_completed(feature):
            print(f"[{feature['slug']}] already completed; skipping mutations.")
            continue
        if beads.get("import_phase") == "relationships":
            print(f"[{feature['slug']}] state already applied; resuming relationships only.")
            continue
        if not root_id:
            root_id = create_feature_root(root, feature)
            beads["root_id"] = root_id
            beads["import_phase"] = "root-created"
            save_manifest_and_report(root, manifest_path, report_path, manifest)
            flush_bd_batch(root, f"migrate-workflow: create {feature['slug']} root")
        if not feature.get("has_design"):
            if feature["classification"] != "deferred":
                bd_note(root, root_id, "No legacy design.md exists. Use /plan-features before starting this feature.")
            beads["state_applied"] = True
            beads["import_phase"] = "relationships"
            save_manifest_and_report(root, manifest_path, report_path, manifest)
            flush_bd_batch(root, f"migrate-workflow: apply {feature['slug']} state")
            print(f"[{feature['slug']}] roadmap-only root applied; relationships pending.")
            continue
        lifecycle = create_lifecycle_steps(
            root,
            feature,
            root_id,
            formula,
            manifest_path,
            report_path,
            manifest,
        )
        implementation_tasks = create_legacy_implementation_tasks(
            root,
            feature,
            lifecycle["implementation"],
            lifecycle["spec-reconcile"],
            manifest_path,
            report_path,
            manifest,
        )
        beads["import_phase"] = "state"
        save_manifest_and_report(root, manifest_path, report_path, manifest)
        apply_imported_states(root, feature, root_id, lifecycle, implementation_tasks)
        beads["import_phase"] = "relationships"
        save_manifest_and_report(root, manifest_path, report_path, manifest)
        flush_bd_batch(root, f"migrate-workflow: apply {feature['slug']} state")
        print(f"[{feature['slug']}] state applied; relationships pending.")

    roots_by_slug = {
        feature["slug"]: feature.get("beads", {}).get("root_id")
        for feature in manifest["features"]
        if feature.get("beads", {}).get("root_id")
    }
    # Reconcile edges across every root currently recorded in the manifest, not
    # only the batch selected for this invocation. This makes repeated
    # --feature imports order-independent: once both roots exist, the edge is
    # added on the next import command.
    for feature in all_features:
        related_slugs = set(feature.get("dependencies", [])) | set(feature.get("related_dependencies", []))
        parent_slug = feature.get("parent_feature")
        referenced_slugs = related_slugs | ({parent_slug} if parent_slug else set())
        root_id = feature.get("beads", {}).get("root_id")
        if not root_id:
            continue
        relationships_complete = all(roots_by_slug.get(slug) for slug in referenced_slugs)
        for dependency_slug in feature.get("dependencies", []):
            dependency_id = roots_by_slug.get(dependency_slug)
            if dependency_id:
                reconcile_bd_relation(root, issue_id=root_id, depends_on=dependency_id, relation="blocks")
        for dependency_slug in feature.get("related_dependencies", []):
            dependency_id = roots_by_slug.get(dependency_slug)
            if dependency_id:
                reconcile_bd_relation(root, issue_id=root_id, depends_on=dependency_id, relation="related")
        parent_id = roots_by_slug.get(parent_slug) if parent_slug else None
        if parent_id:
            reconcile_bd_relation(root, issue_id=root_id, depends_on=parent_id, relation="related")
        if feature.get("beads", {}).get("state_applied") and relationships_complete:
            feature["beads"]["import_phase"] = "completed"
    flush_bd_batch(root, "migrate-workflow: reconcile feature relationships")
    set_batch_active(False)
    progress = import_progress(all_features, recovered=recovered_issues)
    manifest["beads_import_progress"] = progress
    if progress["remaining"] == 0:
        manifest["beads_import_completed_at"] = manifest.get("beads_import_completed_at") or utc_now()
    save_manifest_and_report(root, manifest_path, report_path, manifest)
    print_import_progress(progress)
    print(f"Import pass complete for {len(features)} selected feature(s).")


def repair_beads_labels(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    apply: bool,
) -> None:
    ensure_bd_available(root, init_beads=False)
    working_manifest = copy.deepcopy(manifest)
    features = [feature for feature in working_manifest.get("features", []) if isinstance(feature, dict)]
    reconcile_existing_beads_state(root, features, canonicalize=False, allow_missing_labels=True)
    formula_steps = {
        str(step["id"]): step
        for step in load_formula(root).get("steps", [])
        if isinstance(step, dict) and step.get("id")
    }
    all_issues = parse_bd_issue_list(run_command(["bd", "list", "--all", "--limit", "0", "--json"], cwd=root))
    issues_by_id = {str(issue.get("id")): issue for issue in all_issues if issue.get("id")}
    plan: list[dict[str, Any]] = []
    for feature in features:
        for issue_id, expected in expected_beads_labels(feature, formula_steps).items():
            issue = issues_by_id.get(issue_id)
            if issue is None:
                msg = f"Cannot repair labels for missing manifest-backed Beads record {issue_id}"
                raise MigrationError(msg)
            actual = {str(label) for label in issue.get("labels", [])}
            unexpected = sorted(actual - expected)
            if unexpected:
                msg = f"Refusing additive label repair for {issue_id}; unexpected labels: {', '.join(unexpected)}"
                raise MigrationError(msg)
            missing = sorted(expected - actual)
            if missing:
                plan.append({"issue_id": issue_id, "labels": missing})
    journal = working_manifest.get("beads_label_repair_journal")
    if journal is not None and not isinstance(journal, dict):
        msg = "Beads label repair journal is malformed"
        raise MigrationError(msg)
    full_plan = plan
    if isinstance(journal, dict):
        journal_records = journal.get("records")
        if not isinstance(journal_records, list):
            msg = "Beads label repair journal has no valid records"
            raise MigrationError(msg)
        full_plan = [dict(item) for item in journal_records if isinstance(item, dict)]
        allowed = {str(item.get("issue_id")): set(item.get("labels", [])) for item in full_plan}
        for item in plan:
            issue_id = str(item["issue_id"])
            if issue_id not in allowed or not set(item["labels"]).issubset(allowed[issue_id]):
                msg = f"Current missing labels for {issue_id} exceed the committed repair journal"
                raise MigrationError(msg)
    remaining_label_count = sum(len(item["labels"]) for item in plan)
    full_label_count = sum(len(item.get("labels", [])) for item in full_plan)
    print(f"Beads label repair plan: {len(plan)} record(s), {remaining_label_count} missing label(s).")
    for item in plan:
        print(f"  - {item['issue_id']}: {', '.join(item['labels'])}")
    if not apply:
        print("Dry-run complete; no mutations were made. Rerun with --apply after reviewing the exact additive plan.")
        return
    if not full_plan:
        print("Deterministic Beads labels are already complete; no mutations were made.")
        return
    plan_digest = hashlib.sha256(json.dumps(full_plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if journal is None:
        journal = {
            "created_at": utc_now(),
            "label_count": full_label_count,
            "plan_sha256": plan_digest,
            "record_count": len(full_plan),
            "records": full_plan,
        }
        working_manifest["beads_label_repair_journal"] = journal
        manifest.clear()
        manifest.update(working_manifest)
        save_manifest_and_report(root, manifest_path, report_path, manifest)
    if plan:
        set_batch_active(True)
        try:
            for item in plan:
                command = ["bd", "update", str(item["issue_id"])]
                for label in item["labels"]:
                    command.extend(("--add-label", str(label)))
                run_command(command, cwd=root)
            flush_bd_batch(root, "migrate-workflow: restore deterministic native labels")
        finally:
            set_batch_active(False)
    manifest.clear()
    manifest.update(working_manifest)
    manifest.pop("beads_label_repair_journal", None)
    manifest.setdefault("beads_label_repairs", []).append(
        {
            "applied_at": utc_now(),
            "label_count": full_label_count,
            "plan_sha256": plan_digest,
            "record_count": len(full_plan),
            "records": full_plan,
        }
    )
    reconcile_existing_beads_state(root, manifest["features"], canonicalize=False)
    save_manifest_and_report(root, manifest_path, report_path, manifest)
    print(f"Repaired {len(full_plan)} record(s) with {full_label_count} additive label(s).")


def _reject_symlinked_candidate_path(root: Path, path: Path, *, description: str) -> None:
    resolved_root = root.resolve()
    if _path_has_symlink(resolved_root, path) or not path.resolve().is_relative_to(resolved_root):
        message = f"Unsafe migration path for {description}: {path}"
        raise MigrationError(message)


def draft_delivered_records(root: Path, manifest: dict[str, Any], *, apply: bool) -> None:
    if manifest.get("migration_finalized"):
        message = (
            "Cannot draft delivered-record candidates from a finalized migration; start a new explicit migration "
            "boundary before drafting"
        )
        raise MigrationError(message)
    candidate_prefix = PurePosixPath(DELIVERED_CANDIDATE_DIR.as_posix())
    _reject_symlinked_candidate_path(root, root / DELIVERED_CANDIDATE_DIR, description="delivered_record_candidates")
    safe_repository_path(
        root,
        DELIVERED_CANDIDATE_DIR,
        description="delivered_record_candidates",
        required_prefix=candidate_prefix,
    )
    previous = {
        str(candidate.get("slug")): candidate
        for candidate in manifest.get("delivered_record_candidates", [])
        if isinstance(candidate, dict)
    }
    candidates: list[dict[str, Any]] = []
    for feature in manifest.get("features", []):
        if feature.get("classification") != "completed":
            continue
        slug = str(feature["slug"])
        target = root / DELIVERED_CANDIDATE_DIR / slug / "index.md"
        _reject_symlinked_candidate_path(root, target, description=f"{slug}.delivered_candidate")
        target = safe_repository_path(
            root,
            DELIVERED_CANDIDATE_DIR / slug / "index.md",
            description=f"{slug}.delivered_candidate",
            required_prefix=candidate_prefix,
        )
        task_labels = ", ".join(task["label"] for task in feature.get("tasks", [])) or "none parsed"
        root_id = feature.get("beads", {}).get("root_id") or "not imported"
        evidence_paths = [str(feature["target_dir"]), *map(str, feature.get("legacy_source_dirs", []))]
        git_evidence = subprocess.run(
            ["git", "log", "--format=%H", "--name-only", "--", *evidence_paths],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        commits = [line for line in git_evidence if re.fullmatch(r"[0-9a-f]{7,64}", line)]
        changed_paths = [line for line in git_evidence if line and line not in commits]
        text = (
            f"# {feature['title']}\n\n"
            "## Delivery summary\n\n"
            "Candidate generated from legacy migration evidence; semantic review is required.\n\n"
            f"- Imported Beads root: `{root_id}`\n"
            f"- Legacy tasks: {task_labels}\n"
            f"- Legacy design: `{feature['design_path']}`\n"
            f"- Git commits: {', '.join(commits[:10]) or 'none found'}\n"
            f"- Changed paths: {', '.join(changed_paths[:25]) or 'none found'}\n"
        )
        digest = hashlib.sha256(text.encode()).hexdigest()
        prior = previous.get(slug, {})
        prior_path = root / str(prior.get("path", ""))
        preserve_review = (
            bool(prior.get("reviewed")) and prior_path.is_file() and prior.get("evidence_digest") == digest
        )
        candidate = {
            "slug": slug,
            "path": str(target.relative_to(root)),
            "evidence_digest": digest,
            "reviewed": preserve_review,
        }
        if preserve_review:
            for key in (
                "review_reason",
                "reviewed_at",
                "semantic_summary",
                "semantic_evidence",
                "semantic_commits",
                "record_path",
                "record_digest",
            ):
                if key in prior:
                    candidate[key] = prior[key]
        candidates.append(candidate)
        if apply:
            write_text(target, text)
    manifest["delivered_record_candidates"] = candidates
    print(f"{'Drafted' if apply else 'Would draft'} {len(candidates)} delivered-record candidate(s).")


def review_delivered_record(
    root: Path,
    manifest: dict[str, Any],
    slug: str,
    reason: str,
    *,
    summary: str,
    evidence_paths: Sequence[str],
    commits: Sequence[str],
) -> None:
    if not reason.strip() or len(summary.strip()) < 40 or not evidence_paths or not commits:
        message = "Delivered-record review requires a reason plus feature-specific --summary, --evidence, and --commit"
        raise MigrationError(message)
    feature = next((item for item in manifest.get("features", []) if item.get("slug") == slug), None)
    if not isinstance(feature, dict):
        msg = f"Unknown feature for delivered-record review: {slug}"
        raise MigrationError(msg)
    identity_terms = {slug.casefold(), str(feature.get("title", "")).casefold()}
    normalized_summary = " ".join(summary.split())
    if not any(term and term in normalized_summary.casefold() for term in identity_terms):
        msg = "Semantic summary must name the reviewed feature title or slug"
        raise MigrationError(msg)

    excluded = {
        str(feature.get("design_path", "")),
        str(feature.get("implemented_path", "")),
        str(feature.get("legacy_tasks_path", "")),
        str(feature.get("legacy_tasks_archive", "")),
    }
    evidence: list[dict[str, str]] = []
    evidence_relatives: set[str] = set()
    for raw_path in evidence_paths:
        candidate_path = (root / raw_path).resolve()
        try:
            relative = candidate_path.relative_to(root.resolve())
        except ValueError as exc:
            msg = f"Semantic evidence escapes the repository: {raw_path}"
            raise MigrationError(msg) from exc
        rendered = relative.as_posix()
        if (
            not candidate_path.is_file()
            or _path_has_symlink(root.resolve(), candidate_path)
            or relative.parts[:1] == ("migration",)
            or rendered in excluded
        ):
            msg = f"Semantic evidence must be an existing non-generated corroborating repository file: {raw_path}"
            raise MigrationError(msg)
        evidence_relatives.add(rendered)
        evidence.append({"path": rendered, "sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest()})

    commit_evidence: list[dict[str, Any]] = []
    corroborated_paths: set[str] = set()
    feature_prefixes = {
        str(feature.get("target_dir", "")).rstrip("/") + "/",
        str(feature.get("source_dir", "")).rstrip("/") + "/",
    }
    for requested in commits:
        resolved = git_output(root, "rev-parse", f"{requested}^{{commit}}")
        changed = {
            line for line in git_output(root, "show", "--format=", "--name-only", resolved).splitlines() if line.strip()
        }
        corroborated_paths.update(changed & evidence_relatives)
        relevant = sorted(
            path
            for path in changed
            if path in evidence_relatives
            or any(prefix != "/" and path.startswith(prefix) for prefix in feature_prefixes)
        )
        if not relevant:
            msg = f"Commit {requested} does not corroborate feature {slug}"
            raise MigrationError(msg)
        commit_evidence.append({"sha": resolved, "paths": relevant})
    missing_corroboration = sorted(evidence_relatives - corroborated_paths)
    if missing_corroboration:
        msg = "Selected commit evidence does not touch corroborating evidence: " + ", ".join(missing_corroboration)
        raise MigrationError(msg)

    for candidate in manifest.get("delivered_record_candidates", []):
        if candidate.get("slug") != slug:
            continue
        path = root / str(candidate.get("path", ""))
        if not path.is_file():
            message = f"Delivered-record candidate is missing: {path.relative_to(root)}"
            raise MigrationError(message)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != candidate.get("evidence_digest"):
            message = f"Delivered-record candidate changed after drafting: {slug}"
            raise MigrationError(message)
        record_path = root / str(feature.get("implemented_path", ""))
        if not record_path.is_file():
            msg = f"Implemented feature record is missing: {feature.get('implemented_path')}"
            raise MigrationError(msg)
        candidate["reviewed"] = True
        candidate["review_reason"] = reason.strip()
        candidate["reviewed_at"] = utc_now()
        candidate["semantic_summary"] = normalized_summary
        candidate["semantic_evidence"] = evidence
        candidate["semantic_commits"] = commit_evidence
        candidate["record_path"] = str(feature["implemented_path"])
        candidate["record_digest"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
        return
    message = f"No delivered-record candidate exists for {slug}"
    raise MigrationError(message)


def archived_task_identity(path: Path) -> list[dict[str, Any]]:
    return [{"label": task.label, "status": task.status, "depends_on": task.depends_on} for task in parse_tasks(path)]


def seal_preexisting_archives(root: Path, destination_paths: set[Path]) -> dict[str, str]:
    archive_root = root / DEFAULT_TASK_ARCHIVE
    if not archive_root.exists():
        return {}
    archives: dict[str, str] = {}
    for candidate in sorted(archive_root.rglob("*")):
        safe_candidate = safe_repository_path(
            root,
            candidate.relative_to(root),
            description="preexisting legacy task archive",
            required_prefix=PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix()),
        )
        if safe_candidate.is_file() and safe_candidate not in destination_paths:
            archives[str(safe_candidate.relative_to(root))] = hashlib.sha256(safe_candidate.read_bytes()).hexdigest()
    return archives


def task_references(root: Path) -> list[str]:
    references: list[str] = []
    docs_src = root / "docs/src"
    if not docs_src.exists():
        return references
    # Block archival only for references that would actually break rendered
    # documentation. Explanatory prose may legitimately mention `tasks.md`
    # while describing the old workflow.
    include_re = re.compile(r"\{\{#include\s+(?:\./)?tasks\.md(?:[:#][^}]*)?\}\}")
    link_re = re.compile(r"\]\((?:[^)\s]+/)?tasks\.md(?:#[^)]+)?\)")
    for path in sorted(docs_src.rglob("*.md")):
        if path.name == "tasks.md":
            continue
        text = read_text(path)
        if include_re.search(text) or link_re.search(text):
            references.append(str(path.relative_to(root)))
    return references


def finalize_migration(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    apply: bool,
    delete_tasks: bool,
    archive_dir: Path,
) -> None:
    require_release_tool_reconciliation(manifest, root=root)
    safe_repository_path(
        root,
        archive_dir,
        description="archive_dir",
        required_prefix=PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix()),
    )
    ensure_bd_available(root, init_beads=False)
    live_features = copy.deepcopy([feature for feature in manifest.get("features", []) if isinstance(feature, dict)])
    reconcile_existing_beads_state(root, live_features, canonicalize=False, allow_recovery=False)
    incomplete_phases = [
        str(feature["slug"])
        for feature in live_features
        if (root / str(feature.get("legacy_tasks_path", ""))).exists()
        and feature.get("beads", {}).get("import_phase") != "completed"
    ]
    if incomplete_phases:
        msg = "Legacy tasks cannot be archived before completed live Beads import: " + ", ".join(incomplete_phases)
        raise MigrationError(msg)
    candidate_by_slug = {
        str(candidate.get("slug")): candidate
        for candidate in manifest.get("delivered_record_candidates", [])
        if isinstance(candidate, dict)
    }
    completed_slugs = {
        str(feature.get("slug"))
        for feature in manifest.get("features", [])
        if isinstance(feature, dict) and feature.get("classification") == "completed"
    }
    unreviewed = sorted(slug for slug in completed_slugs if not candidate_by_slug.get(slug, {}).get("reviewed"))
    if unreviewed:
        message = "Delivered-record candidates require semantic review before finalization: " + ", ".join(
            sorted(unreviewed)
        )
        raise MigrationError(message)
    if not manifest.get("migration_finalized"):
        missing_reviewed: list[str] = []
        changed_reviewed: list[str] = []
        for candidate in candidate_by_slug.values():
            if not candidate.get("reviewed"):
                continue
            slug = str(candidate.get("slug", ""))
            try:
                candidate_path = safe_repository_path(
                    root,
                    candidate.get("path", ""),
                    description=f"{slug}.delivered_candidate",
                    required_prefix=PurePosixPath(DELIVERED_CANDIDATE_DIR.as_posix()),
                )
            except MigrationError as exc:
                message = f"Reviewed delivered-record candidate path is unsafe before finalization: {slug}"
                raise MigrationError(message) from exc
            if not candidate_path.is_file():
                missing_reviewed.append(slug)
            elif hashlib.sha256(candidate_path.read_bytes()).hexdigest() != candidate.get("evidence_digest"):
                changed_reviewed.append(slug)
        if missing_reviewed:
            raise MigrationError(
                "Reviewed delivered-record candidates are missing before finalization: "
                + ", ".join(sorted(missing_reviewed))
            )
        if changed_reviewed:
            raise MigrationError(
                "Reviewed delivered-record candidates changed before finalization: "
                + ", ".join(sorted(changed_reviewed))
            )
    references = task_references(root)
    if references:
        details = "\n".join(f"  - {path}" for path in references)
        raise MigrationError(
            "Legacy tasks.md is still referenced by documentation. Rewrite implemented-feature pages first:\n" + details
        )

    missing_imports: list[str] = []
    for feature in manifest.get("features", []):
        tasks_path = root / feature["legacy_tasks_path"]
        if not tasks_path.exists():
            continue
        beads = feature.get("beads", {})
        if not beads.get("root_id") or not beads.get("state_applied"):
            missing_imports.append(f"{feature['slug']}: feature state has not been fully imported")
            continue
        imported = beads.get("implementation_tasks", {})
        expected = {task["label"] for task in feature.get("tasks", []) if task.get("label") not in {"T000", "T999"}}
        missing = sorted(label for label in expected if not imported.get(label))
        if missing:
            missing_imports.append(f"{feature['slug']}: missing imported tasks {', '.join(missing)}")
    if missing_imports:
        details = "\n".join(f"  - {item}" for item in missing_imports)
        raise MigrationError(
            "Legacy task files cannot be archived until Beads import is complete and recorded:\n" + details
        )

    journal_path = safe_repository_path(
        root,
        FINALIZATION_JOURNAL_PATH,
        description="finalization journal",
        required_prefix=PurePosixPath("migration"),
    )
    staging_dir = safe_repository_path(
        root,
        FINALIZATION_STAGING_DIR,
        description="finalization staging directory",
        required_prefix=PurePosixPath("migration"),
    )
    if journal_path.exists() or staging_dir.exists():
        msg = (
            "An interrupted finalization journal or staging directory exists. Recover the listed task files before "
            "retrying; finalization will not guess whether to archive or restore them."
        )
        raise MigrationError(msg)

    operation_records: list[dict[str, Any]] = []
    for feature in manifest.get("features", []):
        tasks_path = safe_repository_path(
            root,
            feature["legacy_tasks_path"],
            description=f"{feature['slug']}.legacy_tasks_path before archival",
            required_prefix=PurePosixPath(FEATURES_PATH.as_posix()),
        )
        if not tasks_path.exists():
            continue
        archive_path = safe_repository_path(
            root,
            archive_dir / f"{feature['slug']}.md",
            description=f"{feature['slug']}.archive_path",
            required_prefix=PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix()),
        )
        if not delete_tasks and archive_path.exists():
            msg = f"Legacy task archive already exists: {archive_path.relative_to(root)}"
            raise MigrationError(msg)
        staging_path = staging_dir / f"{feature['slug']}.md"
        operation_records.append(
            {
                "feature": feature,
                "source": tasks_path,
                "staging": staging_path,
                "destination": None if delete_tasks else archive_path,
                "description": (
                    f"delete {tasks_path.relative_to(root)}"
                    if delete_tasks
                    else f"archive {tasks_path.relative_to(root)} -> {archive_path.relative_to(root)}"
                ),
                "archive_digest": hashlib.sha256(tasks_path.read_bytes()).hexdigest(),
                "archive_identity": archived_task_identity(tasks_path),
                "previous_archive": feature.get("legacy_tasks_archive"),
                "previous_archive_digest": feature.get("legacy_tasks_archive_digest"),
                "previous_archive_identity": feature.get("legacy_tasks_archive_identity"),
                "previous_has_tasks": feature.get("has_tasks"),
            }
        )

    if not apply:
        print("Finalization dry-run:")
        for operation in operation_records:
            print("  -", operation["description"])
        if not operation_records:
            print("  - no legacy tasks.md files remain")
        return
    if manifest.get("migration_finalized") and not operation_records:
        print("Migration finalization already complete; no changes required.")
        return

    destination_paths = {
        operation["destination"] for operation in operation_records if operation["destination"] is not None
    }
    preexisting_archives = seal_preexisting_archives(root, destination_paths)
    original_preexisting_archives = manifest.get("preexisting_legacy_task_archives")
    original_manifest = (root / manifest_path).read_bytes() if (root / manifest_path).exists() else None
    original_report = (root / report_path).read_bytes() if (root / report_path).exists() else None
    original_finalized = manifest.get("migration_finalized")
    original_finalized_at = manifest.get("finalized_at")
    staging_dir.mkdir(parents=True)
    journal = {
        "schema_version": 1,
        "state": "staging",
        "mode": "delete" if delete_tasks else "archive",
        "operations": [
            {
                "source": str(operation["source"].relative_to(root)),
                "staging": str(operation["staging"].relative_to(root)),
                "destination": (str(operation["destination"].relative_to(root)) if operation["destination"] else None),
            }
            for operation in operation_records
        ],
    }
    dump_json(journal_path, journal)
    manifest_saved = False
    try:
        for operation in operation_records:
            operation["staging"].parent.mkdir(parents=True, exist_ok=True)
            operation["source"].replace(operation["staging"])
            feature = operation["feature"]
            feature["has_tasks"] = False
            feature["legacy_tasks_archive"] = (
                "deleted; retained in Git history" if delete_tasks else str(operation["destination"].relative_to(root))
            )
            feature["legacy_tasks_archive_digest"] = operation["archive_digest"]
            feature["legacy_tasks_archive_identity"] = operation["archive_identity"]
        checker = root / "scripts/check-docs.py"
        if checker.exists():
            run_command([sys.executable, str(checker)], cwd=root)
        if not delete_tasks:
            for operation in operation_records:
                destination = operation["destination"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                operation["staging"].replace(destination)
        manifest["preexisting_legacy_task_archives"] = preexisting_archives
        manifest["migration_finalized"] = True
        manifest["finalized_at"] = utc_now()
        save_manifest_and_report(root, manifest_path, report_path, manifest)
        journal["state"] = "committed"
        dump_json(journal_path, journal)
        manifest_saved = True
        if delete_tasks:
            shutil.rmtree(staging_dir)
        else:
            staging_dir.rmdir()
        journal_path.unlink()
    except Exception as exc:
        if manifest_saved:
            msg = (
                "Finalization state was committed but cleanup was interrupted. Preserve the committed journal and "
                "staging directory; verify their digests and finish only the recorded cleanup."
            )
            raise MigrationError(msg) from exc
        for operation in reversed(operation_records):
            source = operation["source"]
            staged = operation["staging"]
            destination = operation["destination"]
            if destination is not None and destination.exists():
                destination.replace(source)
            elif staged.exists():
                staged.replace(source)
            feature = operation["feature"]
            feature["legacy_tasks_archive"] = operation["previous_archive"]
            feature["legacy_tasks_archive_digest"] = operation["previous_archive_digest"]
            feature["legacy_tasks_archive_identity"] = operation["previous_archive_identity"]
            feature["has_tasks"] = operation["previous_has_tasks"]
        shutil.rmtree(staging_dir, ignore_errors=True)
        journal_path.unlink(missing_ok=True)
        manifest["migration_finalized"] = original_finalized
        if original_preexisting_archives is None:
            manifest.pop("preexisting_legacy_task_archives", None)
        else:
            manifest["preexisting_legacy_task_archives"] = original_preexisting_archives
        if original_finalized_at is None:
            manifest.pop("finalized_at", None)
        else:
            manifest["finalized_at"] = original_finalized_at
        if original_manifest is None:
            (root / manifest_path).unlink(missing_ok=True)
        else:
            (root / manifest_path).write_bytes(original_manifest)
        if original_report is None:
            (root / report_path).unlink(missing_ok=True)
        else:
            (root / report_path).write_bytes(original_report)
        raise
    print(f"Finalized {len(operation_records)} legacy task files and passed strict documentation validation.")


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


def _path_has_symlink(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _bounded_files(
    base: Path,
    *,
    repository_root: Path,
    excluded: set[Path],
    budget: list[int],
) -> tuple[list[Path], bool]:
    files: list[Path] = []
    if _path_has_symlink(repository_root, base) or not base.is_dir() or budget[0] >= CAPABILITY_SCAN_LIMIT:
        return files, _path_has_symlink(repository_root, base) or budget[0] >= CAPABILITY_SCAN_LIMIT
    pending = [base]
    while pending:
        current = pending.pop()
        entries: list[os.DirEntry[str]] = []
        with os.scandir(current) as iterator:
            while budget[0] < CAPABILITY_SCAN_LIMIT:
                try:
                    entry = next(iterator)
                except StopIteration:
                    break
                budget[0] += 1
                entries.append(entry)
            else:
                return files, True
        directories: list[Path] = []
        for entry in sorted(entries, key=lambda item: item.name):
            path = Path(entry.path)
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in CAPABILITY_IGNORED_DIRS and path.resolve() not in excluded:
                    directories.append(path)
            elif entry.is_file(follow_symlinks=False):
                files.append(path)
        pending.extend(reversed(directories))
    return files, False


def _mise_data(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, None
    try:
        data = tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as exc:
        return {}, f"Cannot parse {path.name}: {exc}"
    return (data if isinstance(data, dict) else {}), None


def _mise_tasks(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data, _ = _mise_data(path)
    tasks = data.get("tasks")
    return {str(name) for name in tasks} if isinstance(tasks, dict) else set()


def _config_root_name(path: str) -> str:
    return "root" if path == "." else Path(path).name.replace("_", "-")


def discover_repository_capabilities(root: Path) -> dict[str, Any]:
    """Inventory bounded legacy topology and native validation command candidates."""
    scan_budget = [0]
    root_mise = next(
        (
            root / name
            for name in ("mise.toml", ".mise.toml")
            if (root / name).is_file() and not _path_has_symlink(root, root / name)
        ),
        None,
    )
    config_roots = ["."]
    layout_source: str | None = None
    ambiguities: list[str] = []
    if any(
        _path_has_symlink(root, root / name)
        for name in ("mise.toml", ".mise.toml")
        if (root / name).exists() or (root / name).is_symlink()
    ):
        ambiguities.append("root mise config must not be a symlink")
    if root_mise is not None:
        mise_data, mise_error = _mise_data(root_mise)
        if mise_error:
            ambiguities.append(f"root mise config: {mise_error}")
        monorepo = mise_data.get("monorepo")
        configured = monorepo.get("config_roots") if isinstance(monorepo, dict) else None
        if isinstance(configured, list) and configured:
            safe_roots: list[str] = []
            for value in configured:
                if not isinstance(value, str):
                    ambiguities.append("mise monorepo config_roots contains a non-string value")
                    continue
                path = PurePosixPath(value)
                if value != path.as_posix() or path.is_absolute() or any(part in {"", ".."} for part in path.parts):
                    ambiguities.append(f"unsafe mise config root: {value!r}")
                    continue
                target = root if value == "." else root.joinpath(*path.parts)
                if not target.is_dir():
                    ambiguities.append(f"mise config root does not exist: {value}")
                    continue
                current = root
                escaped = False
                for part in path.parts:
                    current /= part
                    if current.is_symlink():
                        ambiguities.append(f"mise config root resolves through a symlink: {value}")
                        escaped = True
                        break
                if not escaped:
                    safe_roots.append(value)
            if safe_roots:
                config_roots = list(dict.fromkeys(safe_roots))
                layout_source = root_mise.relative_to(root).as_posix()
        elif configured is not None:
            ambiguities.append("mise monorepo config_roots must be a nonempty string list")
    kind = "monorepo" if layout_source is not None else "single-package"

    docs_evidence: list[str] = []
    docs_commands: list[dict[str, Any]] = []
    readme = root / "README.md"
    if readme.is_file() and not readme.is_symlink():
        docs_evidence.append("README.md")
    checker = root / DOCS_CHECKER_PATH
    if (checker.exists() or checker.is_symlink()) and _path_has_symlink(root, checker):
        ambiguities.append(f"documentation checker must not resolve through a symlink: {DOCS_CHECKER_PATH}")
    if checker.is_file() and not _path_has_symlink(root, checker):
        docs_evidence.append(DOCS_CHECKER_PATH.as_posix())
        docs_commands.append(
            {
                "name": "root-docs-checker",
                "argv": ["uv", "run", DOCS_CHECKER_PATH.as_posix()],
                "working_directory": ".",
                "provenance": "existing-script",
            }
        )
    root_tasks = _mise_tasks(root_mise) if root_mise is not None else set()
    for task in ("docs:check", "docs:build"):
        if task in root_tasks and root_mise is not None:
            docs_commands.append(
                {
                    "name": f"root-mise-{task.replace(':', '-')}",
                    "argv": ["mise", "run", task],
                    "working_directory": ".",
                    "provenance": root_mise.relative_to(root).as_posix(),
                }
            )
            break
    docs_systems = (
        (Path("docs/book.toml"), ["mdbook", "build", "docs"]),
        (Path("book.toml"), ["mdbook", "build"]),
        (Path("mkdocs.yml"), ["mkdocs", "build"]),
        (Path("mkdocs.yaml"), ["mkdocs", "build"]),
    )
    for path, command in docs_systems:
        if not (root / path).is_file() or _path_has_symlink(root, root / path):
            continue
        docs_evidence.append(path.as_posix())
        if not docs_commands:
            docs_commands.append(
                {
                    "name": f"root-{path.stem}-build",
                    "argv": command,
                    "working_directory": ".",
                    "provenance": path.as_posix(),
                }
            )

    test_evidence: list[str] = []
    test_commands: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []
    resolved_config_roots = {
        (root if value == "." else root.joinpath(*PurePosixPath(value).parts)).resolve() for value in config_roots
    }
    if "." not in config_roots:
        root_files, root_truncated = _bounded_files(
            root,
            repository_root=root,
            excluded=resolved_config_roots,
            budget=scan_budget,
        )
        if root_truncated:
            ambiguities.append(f"root capability scan reached {CAPABILITY_SCAN_LIMIT} entries")
        docs_evidence.extend(
            path.relative_to(root).as_posix() for path in root_files if path.suffix.casefold() in {".md", ".markdown"}
        )
    for config_root in config_roots:
        package_root = root if config_root == "." else root.joinpath(*PurePosixPath(config_root).parts)
        package_name = _config_root_name(config_root)
        excluded = resolved_config_roots - {package_root.resolve()}
        package_files, truncated = _bounded_files(
            package_root, repository_root=root, excluded=excluded, budget=scan_budget
        )
        if truncated:
            ambiguities.append(f"capability scan reached {CAPABILITY_SCAN_LIMIT} entries under {config_root}")
        docs_evidence.extend(
            path.relative_to(root).as_posix()
            for path in package_files
            if path.suffix.casefold() in {".md", ".markdown"}
        )
        if any(
            _path_has_symlink(root, package_root / name)
            for name in ("mise.toml", ".mise.toml")
            if (package_root / name).exists() or (package_root / name).is_symlink()
        ):
            ambiguities.append(f"{config_root}: package mise config must not resolve through a symlink")
        package_mise = next(
            (
                package_root / name
                for name in ("mise.toml", ".mise.toml")
                if (package_root / name).is_file() and not _path_has_symlink(root, package_root / name)
            ),
            None,
        )
        if package_mise is not None:
            _, package_mise_error = _mise_data(package_mise)
            if package_mise_error:
                ambiguities.append(f"{config_root}: {package_mise_error}")
        task_names = _mise_tasks(package_mise) if package_mise is not None else set()
        test_task = next((name for name in ("test", "tests", "check") if name in task_names), None)
        manifest_names = ("go.mod", "mix.exs", "Cargo.toml", "package.json", "pyproject.toml")
        for name in manifest_names:
            if ((package_root / name).exists() or (package_root / name).is_symlink()) and _path_has_symlink(
                root, package_root / name
            ):
                ambiguities.append(f"{config_root}: manifest must not resolve through a symlink: {name}")
        manifests = [
            name
            for name in manifest_names
            if (package_root / name).is_file() and not _path_has_symlink(root, package_root / name)
        ]
        language_commands: list[tuple[str, list[str], list[Path]]] = []
        go_tests = [path for path in package_files if path.name.endswith("_test.go")]
        if go_tests and "go.mod" in manifests:
            language_commands.append(("go", ["go", "test", "./..."], go_tests))
        elif go_tests:
            ambiguities.append(f"{config_root}: Go test files exist but go.mod is missing")
        elixir_tests = [path for path in package_files if path.name.endswith("_test.exs") and "test" in path.parts]
        if elixir_tests and "mix.exs" in manifests:
            language_commands.append(("elixir", ["mix", "test"], elixir_tests))
        elif elixir_tests:
            ambiguities.append(f"{config_root}: Elixir test files exist but mix.exs is missing")
        rust_tests = [path for path in package_files if path.suffix == ".rs" and "tests" in path.parts]
        rust_tests.extend(
            path
            for path in package_files
            if path.suffix == ".rs" and path not in rust_tests and "#[test]" in read_text(path)
        )
        if rust_tests and "Cargo.toml" in manifests:
            language_commands.append(("rust", ["cargo", "test"], rust_tests))
        elif rust_tests:
            ambiguities.append(f"{config_root}: Rust test evidence exists but Cargo.toml is missing")
        python_tests = [
            path
            for path in package_files
            if path.suffix == ".py" and (path.name.startswith("test_") or path.name.endswith("_test.py"))
        ]
        if python_tests and "pyproject.toml" in manifests:
            language_commands.append(("python", ["uv", "run", "pytest"], python_tests))
        elif python_tests:
            ambiguities.append(f"{config_root}: Python test files exist but pyproject.toml is missing")
        js_suffixes = (
            ".test.js",
            ".test.jsx",
            ".test.ts",
            ".test.tsx",
            ".spec.js",
            ".spec.jsx",
            ".spec.ts",
            ".spec.tsx",
        )
        js_tests = [path for path in package_files if path.name.endswith(js_suffixes)]
        js_command: list[str] | None = None
        if "package.json" in manifests:
            try:
                package_json = json.loads(read_text(package_root / "package.json"))
            except (json.JSONDecodeError, OSError) as exc:
                ambiguities.append(f"{config_root}: cannot parse package.json: {exc}")
            else:
                scripts = package_json.get("scripts") if isinstance(package_json, dict) else None
                test_script = scripts.get("test") if isinstance(scripts, dict) else None
                if isinstance(test_script, str) and test_script.strip():
                    js_command = ["npm", "test"]
        if js_tests and js_command:
            language_commands.append(("javascript", js_command, js_tests))
        elif js_tests:
            ambiguities.append(f"{config_root}: JavaScript test files exist but package.json has no test script")

        observed_tests = sorted(set(go_tests + elixir_tests + rust_tests + python_tests + js_tests))
        package_evidence = [path.relative_to(root).as_posix() for path in observed_tests]
        test_evidence.extend(package_evidence)
        package_commands: list[dict[str, Any]] = []
        if test_task is not None and package_mise is not None:
            target = test_task if config_root == "." else f"//{config_root}:{test_task}"
            package_commands.append(
                {
                    "name": f"{package_name}-mise-{test_task}",
                    "argv": ["mise", "run", target],
                    "working_directory": ".",
                    "provenance": package_mise.relative_to(root).as_posix(),
                }
            )
        else:
            for language, argv, _ in language_commands:
                package_commands.append(
                    {
                        "name": f"{package_name}-{language}-test",
                        "argv": argv,
                        "working_directory": config_root,
                        "provenance": "manifest-and-test-evidence",
                    }
                )
        test_commands.extend(package_commands)
        packages.append(
            {
                "path": config_root,
                "mise_file": package_mise.relative_to(root).as_posix() if package_mise is not None else None,
                "manifests": manifests,
                "test_evidence": sorted(set(package_evidence)),
                "commands": package_commands,
            }
        )

    workflow_root = root / ".github/workflows"
    workflow_files, workflows_truncated = _bounded_files(
        workflow_root, repository_root=root, excluded=set(), budget=scan_budget
    )
    if _path_has_symlink(root, workflow_root):
        ambiguities.append("CI workflow directory must not resolve through a symlink")
    elif workflows_truncated:
        ambiguities.append(f"CI workflow scan reached {CAPABILITY_SCAN_LIMIT} entries")
    ci_files = [path.relative_to(root).as_posix() for path in workflow_files if path.suffix in {".yml", ".yaml"}]
    ci_commands: list[dict[str, str]] = []
    for relative in ci_files:
        lines = read_text(root / relative).splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r"(?:-\s*)?run:\s*(.*)$", stripped)
            if not match:
                continue
            value = match.group(1).strip()
            if re.fullmatch(r"[|>][+-]?", value):
                indentation = len(line) - len(line.lstrip())
                block_indentation: int | None = None
                block: list[str] = []
                for continuation in lines[index + 1 :]:
                    if not continuation.strip():
                        continue
                    continuation_indent = len(continuation) - len(continuation.lstrip())
                    if continuation_indent <= indentation:
                        break
                    if block_indentation is None:
                        block_indentation = continuation_indent
                    if continuation_indent < block_indentation:
                        break
                    block.append(continuation.strip())
                value = "\n".join(block)
            if value:
                step_indentation = len(line) - len(line.lstrip())
                working_directory = "."
                for sibling in lines[index + 1 :]:
                    if not sibling.strip():
                        continue
                    sibling_indentation = len(sibling) - len(sibling.lstrip())
                    sibling_text = sibling.strip()
                    if sibling_indentation <= step_indentation and sibling_text.startswith("-"):
                        break
                    match_working_directory = re.match(r"working-directory:\s*(.+)$", sibling_text)
                    if match_working_directory:
                        working_directory = match_working_directory.group(1).strip()
                        break
                ci_commands.append(
                    {
                        "source": f"{relative}:{index + 1}",
                        "command": value,
                        "working_directory": working_directory,
                        "provenance": "ci-evidence-only",
                    }
                )
    return {
        "layout": {"kind": kind, "config_roots": config_roots, "source": layout_source},
        "packages": packages,
        "documentation": {"evidence": sorted(set(docs_evidence)), "commands": docs_commands},
        "tests": {"evidence": sorted(set(test_evidence)), "commands": test_commands},
        "ci": {"files": ci_files, "commands": ci_commands},
        "ambiguities": sorted(set(ambiguities)),
    }


def _bounded_baseline_output(value: str) -> str:
    return value if len(value) <= 20_000 else value[:20_000]


def _invalid_partition(message: str) -> None:
    raise MigrationError(message)


def run_baseline_command(
    root: Path, command: Sequence[str], *, working_directory: Path | None = None
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            list(command),
            cwd=working_directory or root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return {
            "command": shell_command(command),
            "status": "failed",
            "returncode": None,
            "stdout": "",
            "stderr": _bounded_baseline_output(str(error)),
            "output_truncated": len(str(error)) > 20_000,
        }
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    no_tests = result.returncode == 5 and any(
        token in combined.casefold()
        for token in ("collected 0 items", "no tests ran", "no files were found in testpaths")
    )
    return {
        "command": shell_command(command),
        "status": "no_tests" if no_tests else ("passed" if result.returncode == 0 else "failed"),
        "returncode": result.returncode,
        "stdout": _bounded_baseline_output(result.stdout),
        "stderr": _bounded_baseline_output(result.stderr),
        "output_truncated": len(result.stdout) > 20_000 or len(result.stderr) > 20_000,
    }


def run_validation_partitions(
    root: Path,
    specifications: Sequence[str],
    *,
    docs_command: str | None,
    test_command: str | None,
    execute: bool,
    reusable_partitions: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    names: set[str] = set()
    for specification in specifications:
        try:
            item = json.loads(specification)
        except json.JSONDecodeError as error:
            message = f"invalid validation partition JSON: {error}"
            raise MigrationError(message) from error
        if not isinstance(item, dict):
            _invalid_partition("validation partition must be a JSON object")
        name = item.get("name")
        kind = item.get("kind")
        argv = item.get("argv")
        working_directory = item.get("working_directory", ".")
        provenance = item.get("provenance", "operator-override")
        if not isinstance(name, str) or not name or name in names:
            _invalid_partition("validation partition names must be non-empty and unique")
        if kind not in {"documentation", "tests"}:
            _invalid_partition(f"validation partition {name!r} kind must be documentation or tests")
        if not isinstance(argv, list) or not argv or not all(isinstance(value, str) and value for value in argv):
            _invalid_partition(f"validation partition {name!r} argv must be a non-empty string array")
        relative_directory = PurePosixPath(working_directory) if isinstance(working_directory, str) else None
        if (
            relative_directory is None
            or working_directory != relative_directory.as_posix()
            or relative_directory.is_absolute()
            or any(part in {"", ".."} for part in relative_directory.parts)
        ):
            _invalid_partition(f"validation partition {name!r} has an unsafe working directory")
        directory = root if working_directory == "." else root.joinpath(*PurePosixPath(working_directory).parts)
        if not directory.is_dir() or _path_has_symlink(root, directory):
            _invalid_partition(f"validation partition {name!r} working directory is missing or unsafe")
        if not isinstance(provenance, str) or not provenance:
            _invalid_partition(f"validation partition {name!r} provenance must be non-empty")
        validated.append(
            {
                "name": name,
                "kind": kind,
                "argv": argv,
                "working_directory": working_directory,
                "provenance": provenance,
                "directory": directory,
            }
        )
        names.add(name)
    if docs_command and any(item["kind"] == "documentation" for item in validated):
        _invalid_partition("use either --docs-command or named documentation partitions, not both")
    if test_command and any(item["kind"] == "tests" for item in validated):
        _invalid_partition("use either --test-command or named test partitions, not both")

    if not execute:
        return [
            {
                **{key: value for key, value in item.items() if key != "directory"},
                "status": "proposed",
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "output_truncated": False,
                "recovery": None,
            }
            for item in validated
        ]

    reusable = {item.get("name"): item for item in reusable_partitions if isinstance(item, Mapping)}
    partitions: list[dict[str, Any]] = []
    for item in validated:
        directory = item.pop("directory")
        previous = reusable.get(item["name"])
        identity = ("name", "kind", "argv", "working_directory", "provenance")
        if (
            previous
            and previous.get("status") in {"passed", "no_tests"}
            and all(previous.get(key) == item.get(key) for key in identity)
        ):
            partitions.append(dict(previous))
            continue
        outcome = run_baseline_command(root, item["argv"], working_directory=directory)
        partitions.append(
            {
                **item,
                "status": outcome["status"],
                "returncode": outcome["returncode"],
                "stdout": outcome["stdout"],
                "stderr": outcome["stderr"],
                "output_truncated": outcome["output_truncated"],
                "recovery": "Rerun baseline with this unchanged partition after correcting the reported failure."
                if outcome["status"] == "failed"
                else None,
            }
        )
    return partitions


def render_baseline_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Legacy workflow baseline",
        "",
        f"Generated: `{result.get('generated_at', '')}`",
        "",
    ]
    for name in ("documentation", "tests", "hk"):
        item = result.get(name, {})
        lines.extend(
            [
                f"## {name.capitalize()}",
                "",
                f"- Status: `{item.get('status', 'unknown')}`",
                f"- Command: `{item.get('command') or 'not available'}`",
                f"- Note: {item.get('note') or '—'}",
                "",
            ]
        )
    resolution = result.get("resolution", {})
    lines.extend(
        [
            "## Resolution",
            "",
            f"- Write eligible: `{str(resolution.get('write_eligible', False)).lower()}`",
            "- Unresolved: " + (", ".join(f"`{name}`" for name in resolution.get("unresolved", [])) or "none"),
            "- Resolution flags: "
            + ("; ".join(f"{name}={value}" for name, value in resolution.get("flags", {}).items()) or "none"),
            "- Uncovered candidates: "
            + (
                "; ".join(
                    f"{kind}={','.join(names)}"
                    for kind, names in resolution.get("uncovered_candidates", {}).items()
                    if names
                )
                or "none"
            ),
            "- Residual limitations: " + ("; ".join(resolution.get("residual_limitations", [])) or "none"),
            "",
            "## Validation partitions",
            "",
        ]
    )
    partitions = result.get("validation_partitions", [])
    if not partitions:
        lines.append("- None recorded; legacy documentation/tests fields remain authoritative.")
    for partition in partitions:
        lines.append(
            f"- `{partition['name']}` ({partition['kind']}): status=`{partition['status']}`; "
            f"argv=`{shell_command(partition['argv'])}`; cwd=`{partition['working_directory']}`; "
            f"provenance=`{partition['provenance']}`"
        )
        lines.append(
            f"  - Return code: `{partition['returncode']}`; output truncated: "
            f"`{str(partition['output_truncated']).lower()}`"
        )
        for stream_name in ("stdout", "stderr"):
            lines.append(f"  - {stream_name}:")
            output_lines = partition.get(stream_name, "").splitlines() or ["(empty)"]
            lines.extend(f"        {line}" for line in output_lines)
        if partition.get("recovery"):
            lines.append(f"  - Recovery: {partition['recovery']}")
    lines.append("")
    inventory = result.get("capability_inventory", {})
    layout = inventory.get("layout", {})
    lines.extend(
        [
            "## Capability inventory",
            "",
            f"- Layout: `{layout.get('kind', 'unknown')}`",
            "- Config roots: " + ", ".join(f"`{path}`" for path in layout.get("config_roots", [])),
            "- Documentation evidence: "
            + ", ".join(f"`{path}`" for path in inventory.get("documentation", {}).get("evidence", [])),
            "- Test evidence: " + ", ".join(f"`{path}`" for path in inventory.get("tests", {}).get("evidence", [])),
            "- CI workflows: " + ", ".join(f"`{path}`" for path in inventory.get("ci", {}).get("files", [])),
            "- Ambiguities: " + ("; ".join(inventory.get("ambiguities", [])) or "none"),
            "",
            "### Packages",
            "",
        ]
    )
    for package in inventory.get("packages", []):
        lines.extend(
            [
                f"- `{package['path']}`",
                "  - Manifests: " + ", ".join(f"`{name}`" for name in package.get("manifests", [])),
                "  - Test evidence: " + ", ".join(f"`{path}`" for path in package.get("test_evidence", [])),
            ]
        )
    lines.extend(["", "### Proposed commands", ""])
    for kind in ("documentation", "tests"):
        for item in inventory.get(kind, {}).get("commands", []):
            lines.append(
                f"- `{item['name']}` ({kind}): argv=`{shell_command(item['argv'])}`; "
                f"cwd=`{item['working_directory']}`; provenance=`{item['provenance']}`"
            )
    lines.extend(["", "### CI command evidence", ""])
    for item in inventory.get("ci", {}).get("commands", []):
        lines.append(f"- `{item['source']}`: `{item['command']}` ({item['provenance']})")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def baseline_repository(
    root: Path,
    *,
    docs_command: str | None,
    test_command: str | None,
    validation_partition_specs: Sequence[str],
    write: bool,
    baseline_json: Path,
    baseline_report: Path,
    json_output: bool,
) -> int:
    inventory = discover_repository_capabilities(root)
    existing_path = root / baseline_json
    existing: dict[str, Any] | None = None
    if existing_path.is_file():
        try:
            loaded = json.loads(read_text(existing_path))
            existing = loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            existing = None
    proposed_partitions = run_validation_partitions(
        root,
        validation_partition_specs,
        docs_command=docs_command,
        test_command=test_command,
        execute=False,
    )
    checker = root / DOCS_CHECKER_PATH
    scan_incomplete = bool(inventory["ambiguities"])
    selected_by_kind = {
        kind: [item for item in proposed_partitions if item["kind"] == kind] for kind in ("documentation", "tests")
    }

    def uncovered_candidates(kind: str, explicit_command: str | None) -> list[str]:
        if explicit_command:
            return []
        selected = selected_by_kind[kind]
        return [
            candidate["name"]
            for candidate in inventory[kind]["commands"]
            if not any(
                item["argv"] == candidate["argv"] and item["working_directory"] == candidate["working_directory"]
                for item in selected
            )
        ]

    uncovered = {
        "documentation": uncovered_candidates("documentation", docs_command),
        "tests": uncovered_candidates("tests", test_command),
    }
    documentation_supplied = bool(docs_command or selected_by_kind["documentation"]) and not uncovered["documentation"]
    tests_supplied = bool(test_command or selected_by_kind["tests"]) and not uncovered["tests"]
    unresolved_kinds: list[str] = []
    if uncovered["documentation"] or (
        not documentation_supplied
        and (scan_incomplete or inventory["documentation"]["evidence"] or inventory["documentation"]["commands"])
    ):
        unresolved_kinds.append("documentation")
    if uncovered["tests"] or (
        not tests_supplied and (scan_incomplete or inventory["tests"]["evidence"] or inventory["tests"]["commands"])
    ):
        unresolved_kinds.append("tests")
    if write and unresolved_kinds:
        joined = ", ".join(unresolved_kinds)
        _invalid_partition(
            f"baseline write refused: unresolved {joined}; supply reviewed named partitions or explicit commands"
        )
    validation_partitions = (
        run_validation_partitions(
            root,
            validation_partition_specs,
            docs_command=docs_command,
            test_command=test_command,
            execute=True,
            reusable_partitions=existing.get("validation_partitions", []) if existing else (),
        )
        if write
        else proposed_partitions
    )
    documentation_partitions = [item for item in validation_partitions if item["kind"] == "documentation"]
    test_partitions = [item for item in validation_partitions if item["kind"] == "tests"]
    if documentation_partitions:
        failed = any(item["status"] == "failed" for item in documentation_partitions)
        documentation = {
            "command": f"{len(documentation_partitions)} named partition(s)",
            "status": "proposed" if not write else ("failed" if failed else "passed"),
            "returncode": 1 if failed else 0,
            "stdout": "",
            "stderr": "",
            "note": "See validation_partitions for command ownership and evidence.",
        }
    elif docs_command:
        documentation = (
            run_baseline_command(root, shlex.split(docs_command))
            if write
            else {
                "command": docs_command,
                "status": "proposed",
                "returncode": None,
                "stdout": "",
                "stderr": "",
            }
        )
        documentation["note"] = "Explicit baseline documentation command."
    elif checker.is_file() and not _path_has_symlink(root, checker):
        command = ["uv", "run", str(checker)]
        documentation = (
            run_baseline_command(root, command)
            if write
            else {
                "command": shell_command(command),
                "status": "proposed",
                "returncode": None,
                "stdout": "",
                "stderr": "",
            }
        )
        documentation["note"] = "Existing repository documentation checker."
    elif scan_incomplete or inventory["documentation"]["evidence"] or inventory["documentation"]["commands"]:
        documentation = {
            "command": None,
            "status": "unresolved",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": "Documentation evidence exists; select an authoritative discovered command.",
        }
    else:
        documentation = {
            "command": None,
            "status": "unavailable",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": "No documentation system, task, or checker was discovered.",
        }

    if test_partitions:
        failed = any(item["status"] == "failed" for item in test_partitions)
        all_no_tests = all(item["status"] == "no_tests" for item in test_partitions)
        tests = {
            "command": f"{len(test_partitions)} named partition(s)",
            "status": "proposed" if not write else ("failed" if failed else ("no_tests" if all_no_tests else "passed")),
            "returncode": 1 if failed else 0,
            "stdout": "",
            "stderr": "",
            "note": "See validation_partitions for command ownership and evidence.",
        }
    elif test_command:
        tests = (
            run_baseline_command(root, shlex.split(test_command))
            if write
            else {
                "command": test_command,
                "status": "proposed",
                "returncode": None,
                "stdout": "",
                "stderr": "",
            }
        )
        tests["note"] = "Explicit baseline test command."
    elif scan_incomplete or inventory["tests"]["evidence"] or inventory["tests"]["commands"]:
        tests = {
            "command": None,
            "status": "unresolved",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": "Test evidence exists; select all authoritative discovered partitions.",
        }
    else:
        tests = {
            "command": None,
            "status": "no_tests",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": "No test evidence was found in the bounded repository topology scan.",
        }

    hk = (
        capture_hk_inventory(root)
        if write
        else {
            "status": "proposed" if (root / "hk.pkl").is_file() else "absent",
            "command": "pkl eval hk.pkl",
            "hooks": {},
            "note": "Preview does not evaluate repository hook configuration."
            if (root / "hk.pkl").is_file()
            else "No pre-adoption hk.pkl exists.",
        }
    )
    checks: dict[str, dict[str, Any]] = {
        "documentation": documentation,
        "tests": tests,
        "hk": hk,
    }
    result: dict[str, Any] = {
        "generated_at": utc_now(),
        "capability_inventory": inventory,
        "validation_partitions": validation_partitions,
        "resolution": {
            "write_eligible": not unresolved_kinds,
            "unresolved": unresolved_kinds,
            "flags": {
                "documentation": "supplied" if documentation_supplied else documentation["status"],
                "tests": "supplied" if tests_supplied else tests["status"],
            },
            "uncovered_candidates": uncovered,
            "residual_limitations": inventory["ambiguities"],
        },
        **checks,
    }
    if write:
        if existing:
            previous_semantics = {key: value for key, value in existing.items() if key != "generated_at"}
            current_semantics = {key: value for key, value in result.items() if key != "generated_at"}
            if previous_semantics == current_semantics:
                result["generated_at"] = existing.get("generated_at", result["generated_at"])
        dump_json(existing_path, result)
        write_text(root / baseline_report, render_baseline_report(result))
        print(f"Wrote {baseline_json} and {baseline_report}")
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for name, item in checks.items():
            print(f"{name}: {item['status']} ({item.get('command') or item.get('note')})")
    return 1 if any(item["status"] == "failed" for item in checks.values()) else 0


def record_checkpoint_evidence(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    hook: str,
    status: str,
    command: str,
    reason: str,
    equivalent_result: str,
    residual_risk: str,
    approved_step: str,
    approval: str,
) -> None:
    if status == "exception":
        approved_step_name = approved_step.strip()
        if approved_step_name.casefold() in {"docs", "mdbook-lint", "rumdl"}:
            message = (
                "Documentation-step exceptions are disabled during migration; defer or make validation migration-aware"
            )
            raise MigrationError(message)
        if not all(value.strip() for value in (reason, equivalent_result, residual_risk, approved_step_name)):
            message = (
                "Checkpoint exceptions require reason, equivalent result, residual risk, and one exact approved step"
            )
            raise MigrationError(message)
        expected_approval = f"APPROVE HK_SKIP_STEPS={approved_step_name}"
        if approval.strip() != expected_approval:
            msg = f"Checkpoint exception requires the user's exact approval phrase: {expected_approval}"
            raise MigrationError(msg)
        if f"HK_SKIP_STEPS={approved_step_name}" not in command:
            msg = "Checkpoint exception command does not match the explicitly approved hk step"
            raise MigrationError(msg)
    elif approved_step.strip() or approval.strip():
        msg = "Approval fields are valid only for checkpoint exceptions"
        raise MigrationError(msg)
    evidence = {
        "hook": hook,
        "status": status,
        "command": command,
        "reason": reason.strip(),
        "equivalent_result": equivalent_result.strip(),
        "residual_risk": residual_risk.strip(),
        "approved_step": approved_step.strip() or None,
        "approval": approval.strip() or None,
        "recorded_at": utc_now(),
    }
    manifest.setdefault("checkpoint_evidence", []).append(evidence)
    save_manifest_and_report(root, manifest_path, report_path, manifest)


def set_backup_disposition(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    disposition: str,
    reason: str,
) -> None:
    reason = reason.strip()
    if not reason:
        message = "Backup disposition requires a nonempty reason"
        raise MigrationError(message)
    artifacts = manifest.setdefault("artifacts", {})
    if not artifacts.get("backup_present") and artifacts.get("backup_disposition") == "not_applicable":
        message = "No template-adoption backup requires a disposition"
        raise MigrationError(message)
    artifacts["backup_disposition"] = disposition
    artifacts["backup_disposition_reason"] = reason
    save_manifest_and_report(root, manifest_path, report_path, manifest)


def confirm_hk_inventory(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    inventory_path: Path,
    reason: str,
) -> None:
    state = manifest.get("hk_reconciliation", {})
    baseline_status = state.get("baseline", {}).get("status")
    if baseline_status not in {None, "manual_confirmation_required"}:
        message = "Manual hk inventory can only replace a missing or manual-confirmation-required baseline"
        raise MigrationError(message)
    raw = load_json(root / inventory_path)
    hooks = raw.get("hooks") if isinstance(raw, dict) else None
    if not isinstance(hooks, dict):
        message = "Manual hk inventory must be a JSON object containing a hooks mapping"
        raise MigrationError(message)
    normalized: dict[str, dict[str, Any]] = {}
    for hook, steps in hooks.items():
        if not isinstance(steps, dict):
            message = "Each manual hk hook must map step keys to behavior definitions"
            raise MigrationError(message)
        normalized[str(hook)] = {}
        for step, value in steps.items():
            definition = value.get("definition") if isinstance(value, dict) else value
            if not isinstance(definition, str) or not definition.strip():
                message = "Each manual hk step requires a nonempty behavior definition"
                raise MigrationError(message)
            canonical = " ".join(definition.split())
            normalized[str(hook)][str(step)] = {
                "definition": canonical,
                "fingerprint": hashlib.sha256(canonical.encode()).hexdigest(),
            }
    baseline = {
        "status": "manually_confirmed",
        "command": None,
        "hooks": normalized,
        "note": reason,
    }
    manifest["hk_reconciliation"] = hk_reconciliation_state(
        baseline,
        state.get("current", capture_hk_inventory(root)),
        state.get("dispositions", []),
    )
    save_manifest_and_report(root, manifest_path, report_path, manifest)


def set_hk_disposition(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    hook: str,
    step: str,
    action: str,
    reason: str,
) -> None:
    if not reason.strip():
        message = "hk reconciliation disposition requires a nonempty reason"
        raise MigrationError(message)
    state = manifest.get("hk_reconciliation", {})
    baseline_step = state.get("baseline", {}).get("hooks", {}).get(hook, {}).get(step)
    if not isinstance(baseline_step, dict):
        message = f"Baseline hk inventory has no step {hook}/{step}; record manual inventory first"
        raise MigrationError(message)
    current_step = state.get("current", {}).get("hooks", {}).get(hook, {}).get(step)
    disposition = {
        "hook": hook,
        "step": step,
        "action": action,
        "reason": reason.strip(),
        "existing_behavior": baseline_step.get("definition", ""),
        "existing_fingerprint": baseline_step.get("fingerprint", ""),
        "candidate_behavior": current_step.get("definition", "") if isinstance(current_step, dict) else "absent",
        "candidate_fingerprint": current_step.get("fingerprint", "") if isinstance(current_step, dict) else None,
    }
    dispositions = [
        item for item in state.get("dispositions", []) if not (item.get("hook") == hook and item.get("step") == step)
    ]
    dispositions.append(disposition)
    manifest["hk_reconciliation"] = hk_reconciliation_state(
        state.get("baseline", {}), state.get("current", {}), dispositions
    )
    save_manifest_and_report(root, manifest_path, report_path, manifest)


# Side-effect boundaries are imported after the engine definitions to avoid circular import during module startup.
from migration_beads import (  # noqa: E402
    apply_imported_states,
    bd_note,
    canonical_project_slug,
    create_feature_root,
    create_legacy_implementation_tasks,
    create_lifecycle_steps,
    expected_beads_labels,
    load_formula,
    parse_bd_issue_list,
    preflight_import,
    reconcile_bd_relation,
    reconcile_existing_beads_state,
    run_command,
    set_batch_active,
    validate_beads_authority,
)
from migration_git import (  # noqa: E402
    git_output,
    git_repository,
    safe_repository_path,
)
