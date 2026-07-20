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

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import tomllib
from collections.abc import Iterable, Mapping, Sequence
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
    "review-architecture": "review_architecture_id",
    "review-simplicity": "review_simplicity_id",
    "review-documentation": "review_documentation_id",
    "review-execution": "review_execution_id",
    "spec-reconcile": "spec_reconcile_id",
    "implementation": "implementation_id",
    "docs-reconcile": "docs_reconcile_id",
    "validate": "validation_id",
    "review-delivery": "review_delivery_id",
    "review-drift": "review_drift_id",
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
    lines.extend(
        [
            "",
            "## Feature Mapping",
            "",
            "| Feature | Target | Classification | Roadmap | Design | Index | Findings |",
            "|---|---|---|---|---|---:|---:|",
        ]
    )
    for feature in features:
        design_status = str(feature.get("design_status", "")).replace("|", "\\|")
        roadmap_status = str(feature.get("roadmap_status", "")).replace("|", "\\|")
        classification = str(feature["classification"])
        if feature.get("classification_override"):
            classification += " (override)"
        lines.append(
            ("| `{slug}` | `{slug}` | `{classification}` | {roadmap} | {design} | {index} | {findings} |").format(
                slug=feature["slug"],
                classification=classification,
                roadmap=roadmap_status or "—",
                design=design_status or "—",
                index="yes" if feature.get("has_index") else "no",
                findings=len(feature.get("conflicts", [])),
            )
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
    dump_json(root / manifest_path, manifest)
    write_text(root / report_path, render_report(manifest))


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


def replace_feature_paths(
    text: str,
    mapping: Mapping[str, str],
    *,
    rewrite_sibling_links: bool,
) -> str:
    """Rewrite references that are structurally known to target feature paths.

    Avoid broad ``/<slug>/`` replacement: a feature slug may also be an API,
    package, or deployment path elsewhere in project documentation. Relative
    sibling forms are rewritten only inside ``docs/src/features``.
    """

    result = text
    for slug in sorted(mapping, key=lambda slug: len(slug), reverse=True):
        target = mapping[slug]
        replacements = [
            (f"docs/src/features/{slug}/", f"docs/src/features/{target}/"),
            (f"docs/src/features/{slug}`", f"docs/src/features/{target}`"),
            (f"features/{slug}/", f"features/{target}/"),
            (f"feat/{slug}", f"feat/{target}"),
        ]
        if rewrite_sibling_links:
            replacements.extend(
                (
                    (f"../{slug}/", f"../{target}/"),
                    (f"./{slug}/", f"./{target}/"),
                    (f"({slug}/", f"({target}/"),
                    (f"<{slug}/", f"<{target}/"),
                )
            )
        for old, new in replacements:
            result = result.replace(old, new)
    return result


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


def git_output(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = f"Git command failed: git {shell_command(arguments)}\n{result.stderr.strip()}"
        raise MigrationError(message)
    return result.stdout.strip()


def git_repository(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def session_resume_approval(branch: str, root: Path) -> str:
    return f"RESUME DSTACK MIGRATION {branch} IN {root.resolve()}"


def authorize_session(
    root: Path,
    *,
    mode: str,
    base_branch: str,
    migration_branch: str,
    approval: str,
) -> None:
    if not git_repository(root):
        msg = "Migration session authority requires a Git repository"
        raise MigrationError(msg)
    current_branch = git_output(root, "branch", "--show-current")
    if not current_branch:
        msg = "Migration must run on a named branch, not detached HEAD"
        raise MigrationError(msg)
    if current_branch != migration_branch:
        msg = f"Current branch {current_branch!r} is not the explicitly selected migration branch {migration_branch!r}"
        raise MigrationError(msg)
    if migration_branch == base_branch:
        msg = "The migration branch must differ from the explicitly selected base branch"
        raise MigrationError(msg)
    root_path = root.resolve()
    common_dir = Path(git_output(root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    authority_path = root / SESSION_AUTHORITY_PATH
    base_sha = git_output(root, "rev-parse", f"{base_branch}^{{commit}}")
    head_sha = git_output(root, "rev-parse", "HEAD")

    if mode == "fresh":
        if authority_path.exists():
            msg = "Migration session authority already exists; fresh mode cannot adopt or overwrite resumable state"
            raise MigrationError(msg)
        if head_sha != base_sha:
            msg = "Fresh migration branch must point exactly at the selected base-branch HEAD before any checkpoint"
            raise MigrationError(msg)
        if git_output(root, "status", "--porcelain"):
            msg = "Fresh migration authority requires a clean worktree"
            raise MigrationError(msg)
        authority: dict[str, Any] = {
            "schema_version": 1,
            "mode": "fresh",
            "base_branch": base_branch,
            "base_sha": base_sha,
            "migration_branch": migration_branch,
            "worktree_path": str(root_path),
            "git_common_dir": str(common_dir),
            "created_at": utc_now(),
        }
    else:
        authority = load_json(authority_path) or {}
        if not authority:
            msg = (
                "Resume requires existing session authority from a previously authorized fresh migration; "
                "checkpoint commits or a manifest are not authority"
            )
            raise MigrationError(msg)
        expected = session_resume_approval(migration_branch, root)
        if approval.strip() != expected:
            msg = f"Resume requires the user's exact approval phrase: {expected}"
            raise MigrationError(msg)
        require_session_authority(root, authority=authority)
        if authority.get("base_branch") != base_branch:
            msg = "Resume base branch does not match the recorded migration authority"
            raise MigrationError(msg)
        resume_log_path = root / SESSION_RESUME_LOG_PATH
        resume_log = load_json(resume_log_path) or {"schema_version": 1, "approvals": []}
        approvals = resume_log.setdefault("approvals", [])
        if not isinstance(approvals, list):
            msg = "Migration resume approval audit has an invalid approvals collection"
            raise MigrationError(msg)
        approvals.append(
            {
                "approved_at": utc_now(),
                "approval": expected,
                "head_sha": head_sha,
                "worktree_path": str(root_path),
            }
        )
        dump_json(resume_log_path, resume_log)
    if mode == "fresh":
        dump_json(authority_path, authority)
    print(f"Authorized {mode} migration session on {migration_branch} from {base_branch}.")


def require_session_authority(
    root: Path,
    *,
    authority: Mapping[str, Any] | None = None,
    require_committed: bool = True,
) -> None:
    if not git_repository(root):
        msg = "Workflow migration requires a Git worktree; non-Git execution has no branch or checkpoint authority"
        raise MigrationError(msg)
    authority_path = root / SESSION_AUTHORITY_PATH
    state = dict(authority or load_json(authority_path) or {})
    if not state:
        msg = (
            "Migration session authority is missing. Do not inspect or auto-resume existing migration branches; "
            "checkpoint commits or a manifest are not authority. Obtain explicit base/branch intent and run "
            "authorize-session first."
        )
        raise MigrationError(msg)
    current_branch = git_output(root, "branch", "--show-current")
    expected_branch = str(state.get("migration_branch", ""))
    if not current_branch or current_branch != expected_branch:
        msg = f"Current branch {current_branch!r} is not the authorized migration branch {expected_branch!r}"
        raise MigrationError(msg)
    if str(root.resolve()) != str(state.get("worktree_path", "")):
        msg = "Current worktree path does not match the authorized migration worktree"
        raise MigrationError(msg)
    common_dir = Path(git_output(root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    if str(common_dir) != str(state.get("git_common_dir", "")):
        msg = "Current Git repository does not match the authorized migration repository"
        raise MigrationError(msg)
    base_sha = str(state.get("base_sha", ""))
    if not base_sha:
        msg = "Migration authority does not record the selected base SHA"
        raise MigrationError(msg)
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        msg = "Authorized base SHA is not an ancestor of the current migration branch"
        raise MigrationError(msg)
    if require_committed:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(SESSION_AUTHORITY_PATH)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        committed = subprocess.run(
            ["git", "show", f"HEAD:{SESSION_AUTHORITY_PATH.as_posix()}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if tracked.returncode != 0 or committed.returncode != 0:
            msg = "Migration session authority must be committed before leaving the baseline gate"
            raise MigrationError(msg)
        authority_bytes = authority_path.read_bytes()
        if committed.stdout != authority_bytes:
            msg = "Working migration session authority differs from the committed checkpoint"
            raise MigrationError(msg)
        introduction = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--reverse",
                "--",
                SESSION_AUTHORITY_PATH.as_posix(),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        introduction_commits = [line for line in introduction.stdout.splitlines() if line]
        if introduction.returncode != 0 or len(introduction_commits) != 1:
            msg = "Migration session authority must have exactly one immutable introduction commit"
            raise MigrationError(msg)
        original = subprocess.run(
            ["git", "show", f"{introduction_commits[0]}:{SESSION_AUTHORITY_PATH.as_posix()}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if original.returncode != 0 or original.stdout != authority_bytes:
            msg = "Migration session authority differs from its original authorization commit"
            raise MigrationError(msg)


def safe_repository_path(
    root: Path,
    value: Any,
    *,
    description: str,
    required_prefix: PurePosixPath,
) -> Path:
    rendered = str(value)
    pure = PurePosixPath(rendered)
    if (
        not rendered
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in rendered
        or re.match(r"^[A-Za-z]:", rendered)
        or not pure.is_relative_to(required_prefix)
    ):
        msg = f"Unsafe migration path for {description}: {rendered!r}"
        raise MigrationError(msg)
    candidate = root.joinpath(*pure.parts)
    resolved_root = root.resolve()
    if _path_has_symlink(resolved_root, candidate) or not candidate.resolve().is_relative_to(resolved_root):
        msg = f"Unsafe migration path for {description}: {rendered!r} resolves through or beyond repository authority"
        raise MigrationError(msg)
    return candidate


def validate_manifest_paths(root: Path, manifest: Mapping[str, Any]) -> None:
    feature_prefix = PurePosixPath(FEATURES_PATH.as_posix())
    archive_prefix = PurePosixPath(DEFAULT_TASK_ARCHIVE.as_posix())
    candidate_prefix = PurePosixPath(DELIVERED_CANDIDATE_DIR.as_posix())
    for feature in manifest.get("features", []):
        if not isinstance(feature, dict):
            continue
        slug = str(feature.get("slug", "unknown"))
        for key in (
            "source_dir",
            "target_dir",
            "design_path",
            "implemented_path",
            "legacy_tasks_path",
        ):
            safe_repository_path(
                root,
                feature.get(key, ""),
                description=f"{slug}.{key}",
                required_prefix=feature_prefix,
            )
        optional = feature.get("legacy_open_questions_path")
        if optional:
            safe_repository_path(
                root,
                optional,
                description=f"{slug}.legacy_open_questions_path",
                required_prefix=feature_prefix,
            )
        for index, source in enumerate(feature.get("legacy_source_dirs", [])):
            safe_repository_path(
                root,
                source,
                description=f"{slug}.legacy_source_dirs[{index}]",
                required_prefix=feature_prefix,
            )
        archive = feature.get("legacy_tasks_archive")
        if archive and not str(archive).startswith("deleted;"):
            safe_repository_path(
                root,
                archive,
                description=f"{slug}.legacy_tasks_archive",
                required_prefix=archive_prefix,
            )
    for candidate in manifest.get("delivered_record_candidates", []):
        if not isinstance(candidate, dict):
            continue
        candidate_slug = str(candidate.get("slug", "unknown"))
        if candidate.get("path"):
            safe_repository_path(
                root,
                candidate["path"],
                description=f"{candidate_slug}.delivered_candidate",
                required_prefix=candidate_prefix,
            )
        if candidate.get("record_path"):
            safe_repository_path(
                root,
                candidate["record_path"],
                description=f"{candidate_slug}.record_path",
                required_prefix=feature_prefix,
            )
        for index, evidence in enumerate(candidate.get("semantic_evidence", [])):
            if isinstance(evidence, dict):
                safe_repository_path(
                    root,
                    evidence.get("path", ""),
                    description=f"{candidate_slug}.semantic_evidence[{index}]",
                    required_prefix=PurePosixPath("."),
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
    if docs_src.exists():
        for path in sorted(docs_src.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".toml", ".json", ".yaml", ".yml"}:
                continue
            old = read_text(path)
            new = replace_feature_paths(
                old,
                mapping,
                rewrite_sibling_links=path.is_relative_to(root / FEATURES_PATH),
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


def shell_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


BD_BATCH_ACTIVE = False
BD_AUTHORITY_DB: Path | None = None
BD_AUTHORITY_SNAPSHOT: dict[str, Any] | None = None


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
        if BD_AUTHORITY_DB is not None and "--db" not in actual_command:
            actual_command[1:1] = ["--db", str(BD_AUTHORITY_DB)]
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


def primary_worktree(root: Path) -> Path:
    if not git_repository(root):
        return root.resolve()
    output = git_output(root, "worktree", "list", "--porcelain")
    first = next((line.removeprefix("worktree ") for line in output.splitlines() if line.startswith("worktree ")), "")
    if not first:
        msg = "Cannot determine the primary Git worktree for Beads authority"
        raise MigrationError(msg)
    return Path(first).resolve()


def canonical_project_slug(root: Path) -> str:
    for candidate in (root / ".copier-answers.yml", primary_worktree(root) / ".copier-answers.yml"):
        if not candidate.is_file():
            continue
        match = re.search(r"^project_slug:\s*['\"]?([^'\"\s]+)", read_text(candidate), re.MULTILINE)
        if match:
            return match.group(1)
    return primary_worktree(root).name


def validate_beads_authority(root: Path) -> dict[str, Any]:
    global BD_AUTHORITY_DB, BD_AUTHORITY_SNAPSHOT
    expected_root = primary_worktree(root)
    unresolved_beads = expected_root / ".beads"
    if unresolved_beads.is_symlink() or _path_has_symlink(expected_root, unresolved_beads):
        msg = "Repository-local .beads authority must not be a symlink"
        raise MigrationError(msg)
    expected_beads = unresolved_beads.resolve()
    metadata_path = expected_beads / "metadata.json"
    config_path = expected_beads / "config.yaml"
    if not metadata_path.is_file() or not config_path.is_file():
        msg = (
            f"Repository-local Beads authority is incomplete at {expected_beads}; both metadata.json and config.yaml "
            "are required. A formula-only .beads directory is not initialized."
        )
        raise MigrationError(msg)
    metadata = load_json(metadata_path)
    if not isinstance(metadata, dict):
        msg = f"Invalid repository-local Beads metadata: {metadata_path}"
        raise MigrationError(msg)
    BD_AUTHORITY_DB = expected_beads
    BD_AUTHORITY_SNAPSHOT = None
    context = parse_json_object(run_command(["bd", "context", "--json"], cwd=root), command="bd context --json")
    location = parse_json_object(run_command(["bd", "where", "--json"], cwd=root), command="bd where --json")
    project_slug = canonical_project_slug(root)
    expected_database = project_slug.replace("-", "_")
    expected_prefix = project_slug
    problems: list[str] = []

    def same_path(value: Any, expected: Path) -> bool:
        try:
            return Path(str(value)).expanduser().resolve() == expected
        except (OSError, RuntimeError, ValueError):
            return False

    if not same_path(context.get("beads_dir"), expected_beads):
        problems.append(f"bd context beads_dir is {context.get('beads_dir')!r}, expected {str(expected_beads)!r}")
    if not same_path(context.get("repo_root"), expected_root):
        problems.append(f"bd context repo_root is {context.get('repo_root')!r}, expected {str(expected_root)!r}")
    if not same_path(location.get("path"), expected_beads):
        problems.append(f"bd where path is {location.get('path')!r}, expected {str(expected_beads)!r}")
    database_path = Path(str(location.get("database_path", ""))).expanduser().resolve()
    if not database_path.is_relative_to(expected_beads):
        problems.append("bd where database_path is outside the repository-local .beads directory")
    if context.get("database") != expected_database or metadata.get("dolt_database") != expected_database:
        problems.append(
            f"Beads database identity must be {expected_database!r}; context={context.get('database')!r}, "
            f"metadata={metadata.get('dolt_database')!r}"
        )
    if location.get("prefix") != expected_prefix:
        problems.append(f"Beads issue prefix is {location.get('prefix')!r}, expected {expected_prefix!r}")
    if not metadata.get("project_id") or context.get("project_id") != metadata.get("project_id"):
        problems.append("Beads project_id is missing or disagrees with repository-local metadata")
    if context.get("dolt_mode") != "embedded" or context.get("is_redirected") is True:
        problems.append("Migration requires a non-redirected repository-local embedded Dolt database")
    if problems:
        message = "Beads authority mismatch; refusing global/shared fallback:\n  - " + "\n  - ".join(problems)
        raise MigrationError(message)
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
        for step_id in (
            "design",
            "review-architecture",
            "review-simplicity",
            "review-documentation",
            "review-execution",
            "spec-reconcile",
        ):
            lifecycle[step_id] = "closed"
        imported_tasks = [
            task for task in feature.get("tasks", []) if str(task.get("label", "")) not in {"T000", "T999"}
        ]
        if all(str(task.get("status", "")) == "closed" for task in imported_tasks):
            lifecycle["implementation"] = "closed"
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
    expected_status: str,
    expected_parent: str = "",
    required_labels: Iterable[str] = (),
    expected_owned_labels: Iterable[str] = (),
    required_metadata: Mapping[str, str] | None = None,
    expected_type: str | None = None,
) -> None:
    if issue is None:
        return
    actual_type = str(issue.get("issue_type") or issue.get("type") or "")
    if expected_type and actual_type != expected_type:
        problems.append(f"{description} {issue_id} has type {actual_type!r}; expected {expected_type!r}")
    actual_status = str(issue.get("status") or "")
    if actual_status != expected_status:
        problems.append(f"{description} {issue_id} has status {actual_status!r}; expected status {expected_status!r}")
    if expected_parent and str(issue.get("parent") or "") != expected_parent:
        problems.append(f"{description} {issue_id} is not parented by {expected_parent}")
    labels = {str(label) for label in issue.get("labels", [])}
    missing_labels = sorted(set(required_labels) - labels)
    if missing_labels:
        problems.append(f"{description} {issue_id} is missing required labels: {', '.join(missing_labels)}")
    owned_labels = {
        label
        for label in labels
        if label == "workflow:feature" or label.startswith(("migration:", "formula-step:", "legacy-task:"))
    }
    expected_owned = set(expected_owned_labels)
    if expected_owned and owned_labels != expected_owned:
        problems.append(
            f"{description} {issue_id} has unexpected migration-owned labels: "
            f"expected {sorted(expected_owned)}, found {sorted(owned_labels)}"
        )
    metadata = issue_metadata(issue)
    for key, value in (required_metadata or {}).items():
        if str(metadata.get(key, "")) != value:
            problems.append(f"{description} {issue_id} has invalid metadata {key!r}; expected {value!r}")


def reconcile_existing_beads_state(
    root: Path,
    features: Sequence[dict[str, Any]],
    *,
    canonicalize: bool,
    allow_recovery: bool = True,
) -> int:
    root_issues = discover_migrated_issues(root, "migration:legacy-markdown", issue_type="epic")
    lifecycle_issues = discover_migrated_issues(root, "migration:legacy-workflow")
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
    all_discovered = (*root_issues, *lifecycle_issues, *implementation_issues, *reconciliation_issues)
    discovered_by_id = {str(issue.get("id")): issue for issue in all_discovered if issue.get("id")}
    discovered_metadata = {issue_id: issue_metadata(issue) for issue_id, issue in discovered_by_id.items()}

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

    for feature in features:
        slug = str(feature["slug"])
        beads = feature.get("beads", {})
        root_id = str(beads.get("root_id") or "")
        root_issue = discovered_by_id.get(root_id)
        root_status, lifecycle_statuses, task_statuses = expected_migrated_statuses(feature)
        validate_expected_issue(
            problems=problems,
            issue=root_issue,
            issue_id=root_id,
            description=f"{slug} recorded root",
            expected_status=root_status,
            required_labels=("workflow:feature", "migration:legacy-markdown"),
            expected_owned_labels=(
                "workflow:feature",
                "migration:legacy-markdown",
                *(("migration:needs-reconciliation",) if feature.get("classification") == "needs_review" else ()),
            ),
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
                expected_status=lifecycle_statuses[step_id],
                expected_parent=root_id,
                required_labels=("migration:legacy-workflow", f"formula-step:{step_id}"),
                expected_owned_labels=("migration:legacy-workflow", f"formula-step:{step_id}"),
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
                expected_status=task_statuses[label],
                expected_parent=implementation_parent,
                required_labels=("migration:legacy-task", f"legacy-task:{label.casefold()}"),
                expected_owned_labels=("migration:legacy-task", f"legacy-task:{label.casefold()}"),
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
                expected_owned_labels=("migration:reconciliation",),
                required_metadata={
                    "migration_source": "legacy-markdown-workflow",
                    "migration_key": f"legacy-feature:{slug}:reconciliation",
                    "migration_role": "status-reconciliation",
                    "feature_slug": slug,
                },
                expected_type="task",
            )
        if root_id and root_issue is not None:
            roots_by_slug = {
                str(candidate["slug"]): str(candidate.get("beads", {}).get("root_id") or "") for candidate in features
            }
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
            actual_relationships = bd_dependency_types(root, root_id)
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


def bd_dependency_types(root: Path, issue_id: str) -> dict[str, str]:
    output = run_command(["bd", "dep", "list", issue_id, "--json"], cwd=root)
    dependencies = parse_bd_issue_list(output, command="bd dep list --json")
    return {str(item["id"]): str(item.get("dependency_type") or "blocks") for item in dependencies if item.get("id")}


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
    for feature in features:
        source = str(feature["slug"])
        issue_id = str(feature.get("beads", {}).get("root_id") or "")
        if not issue_id:
            continue
        for dependency_id, relation in bd_dependency_types(root, issue_id).items():
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
            "review-architecture",
            "review-simplicity",
            "review-documentation",
            "review-execution",
            "spec-reconcile",
            "implementation",
            "docs-reconcile",
            "validate",
            "review-delivery",
            "review-drift",
            "delivery",
        ):
            bd_close(root, lifecycle[step_id], "Migrated completed legacy feature evidence")
        bd_close(root, root_id, "Migrated completed legacy feature")
    elif classification == "needs_review":
        for step_id in (
            "design",
            "review-architecture",
            "review-simplicity",
            "review-documentation",
            "review-execution",
            "spec-reconcile",
        ):
            bd_close(
                root, lifecycle[step_id], "Legacy implementation evidence imported; migration reconciliation remains"
            )

        open_implementation_ids = [
            implementation_tasks[label]
            for label, task in task_by_label.items()
            if label in implementation_tasks and task["status"] != "closed"
        ]
        if not open_implementation_ids:
            bd_close(root, lifecycle["implementation"], "All imported legacy implementation tasks are complete")

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


def ensure_bd_available(root: Path, *, init_beads: bool) -> None:
    if shutil.which("bd") is None:
        msg = "The 'bd' command is not installed"
        raise MigrationError(msg)
    beads_dir = primary_worktree(root) / ".beads"
    initialized = (beads_dir / "metadata.json").is_file() and (beads_dir / "config.yaml").is_file()
    if not initialized:
        if not init_beads:
            msg = (
                "Beads is not repository-locally initialized. A formula-only .beads directory is insufficient. "
                "Run the guarded beads-authority --init command."
            )
            raise MigrationError(msg)
        run_command(["bd", "init", "--stealth", "--skip-agents"], cwd=root)
    if not (beads_dir / "metadata.json").is_file() or not (beads_dir / "config.yaml").is_file():
        msg_0 = "bd init returned without creating complete repository-local Beads authority"
        raise MigrationError(msg_0)
    validate_beads_authority(root)


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
) -> None:
    features = selected_features(manifest, requested)
    all_features = manifest["features"]
    initially_completed = {str(feature["slug"]) for feature in all_features if feature_import_completed(feature)}
    changed_slugs = {str(feature["slug"]) for feature in features} - initially_completed
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

    global BD_BATCH_ACTIVE
    BD_BATCH_ACTIVE = True
    print(f"APPLY STARTED: importing {len(features)} selected feature(s) into Beads with bounded batch commits.")
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
        if feature["classification"] == "deferred" and not feature.get("has_design"):
            beads["state_applied"] = True
            continue
        if not feature.get("has_design"):
            bd_note(root, root_id, "No legacy design.md exists. Use /plan-features before starting this feature.")
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
        feature_slug = str(feature["slug"])
        if feature_import_completed(feature) and feature_slug not in changed_slugs:
            continue
        if feature_slug not in changed_slugs and not referenced_slugs & changed_slugs:
            continue
        root_id = feature.get("beads", {}).get("root_id")
        if not root_id:
            continue
        relationships_complete = all(roots_by_slug.get(slug) for slug in referenced_slugs)
        for dependency_slug in feature.get("dependencies", []):
            dependency_id = roots_by_slug.get(dependency_slug)
            if dependency_id:
                bd_dep(root, root_id, dependency_id)
        for dependency_slug in feature.get("related_dependencies", []):
            dependency_id = roots_by_slug.get(dependency_slug)
            if dependency_id:
                bd_dep(root, root_id, dependency_id, "related")
        parent_id = roots_by_slug.get(parent_slug) if parent_slug else None
        if parent_id:
            bd_dep(root, root_id, parent_id, "related")
        if feature.get("beads", {}).get("state_applied") and relationships_complete:
            feature["beads"]["import_phase"] = "completed"
    flush_bd_batch(root, "migrate-workflow: reconcile feature relationships")
    BD_BATCH_ACTIVE = False
    progress = import_progress(all_features, recovered=recovered_issues)
    manifest["beads_import_progress"] = progress
    if progress["remaining"] == 0:
        manifest["beads_import_completed_at"] = manifest.get("beads_import_completed_at") or utc_now()
    save_manifest_and_report(root, manifest_path, report_path, manifest)
    print_import_progress(progress)
    print(f"Import pass complete for {len(features)} selected feature(s).")


def draft_delivered_records(root: Path, manifest: dict[str, Any], *, apply: bool) -> None:
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
        candidate = {
            "slug": slug,
            "path": str(target.relative_to(root)),
            "evidence_digest": digest,
            "reviewed": bool(prior.get("reviewed")) and prior.get("evidence_digest") == digest,
        }
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
            run_command(["uv", "run", str(checker)], cwd=root)
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


def verify_migration(root: Path, manifest: Mapping[str, Any], *, verify_beads: bool) -> tuple[list[str], list[str]]:
    errors = finalized_inventory_errors(root, manifest) if manifest.get("migration_finalized") else []
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
            errors.append(f"Reviewed delivered-record candidate is missing: {slug}")
            continue
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
            graph, relationships = bd_feature_relationship_graph(root, features)
        except MigrationError as exc:
            errors.append(f"Cannot inspect imported Beads relationships: {exc}")
        else:
            for cycle in graph_cycles(graph):
                errors.append(
                    "Imported Beads graph contains a traversal cycle: " + render_typed_cycle(cycle, relationships)
                )

    for path in sorted((root / "docs/src").rglob("*.md")) if (root / "docs/src").exists() else []:
        text = read_text(path)
        for source_name, slug in mapping.items():
            if source_name == slug:
                continue
            stale_patterns = (f"docs/src/features/{source_name}/", f"features/{source_name}/", f"({source_name}/")
            if any(pattern in text for pattern in stale_patterns):
                errors.append(f"Stale feature path for {slug} in {path.relative_to(root)}")
                break
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
        if not all(value.strip() for value in (reason, equivalent_result, residual_risk, approved_step)):
            message = (
                "Checkpoint exceptions require reason, equivalent result, residual risk, and one exact approved step"
            )
            raise MigrationError(message)
        expected_approval = f"APPROVE HK_SKIP_STEPS={approved_step.strip()}"
        if approval.strip() != expected_approval:
            msg = f"Checkpoint exception requires the user's exact approval phrase: {expected_approval}"
            raise MigrationError(msg)
        if f"HK_SKIP_STEPS={approved_step.strip()}" not in command:
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
