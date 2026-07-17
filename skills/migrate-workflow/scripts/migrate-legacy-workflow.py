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
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MANIFEST = Path("migration/workflow-migration.json")
DEFAULT_REPORT = Path("migration/workflow-migration.md")
DEFAULT_TASK_ARCHIVE = Path("migration/legacy-tasks")
DEFAULT_BASELINE_JSON = Path("migration/baseline.json")
DEFAULT_BASELINE_REPORT = Path("migration/baseline.md")
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


def ensure_trailing_newline(path: Path) -> None:
    if not path.is_file():
        return
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        path.write_bytes(content + b"\n")


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
    return slug.replace("-", " ").capitalize()


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


def _pkl_string_set(root: Path, expression: str) -> list[str]:
    result = subprocess.run(
        ["pkl", "eval", "hk.pkl", "--expression", expression],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return re.findall(r'"((?:[^"\\]|\\.)*)"', result.stdout)


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
        hook_names = _pkl_string_set(root, "hooks.keys")
        hooks: dict[str, dict[str, Any]] = {}
        for hook in hook_names:
            step_names = _pkl_string_set(root, f'hooks["{hook}"].steps.keys')
            steps: dict[str, Any] = {}
            for step in step_names:
                expression = f'hooks["{hook}"].steps["{step}"]'
                result = subprocess.run(
                    ["pkl", "eval", "hk.pkl", "--expression", expression],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip())
                definition = " ".join(result.stdout.split())
                steps[step] = {
                    "fingerprint": hashlib.sha256(definition.encode()).hexdigest(),
                    "definition": definition,
                }
            hooks[hook] = steps
        return {"status": "evaluable", "command": command, "hooks": hooks, "note": "Pkl evaluation passed."}
    except (OSError, RuntimeError) as error:
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


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    capture: bool = True,
    allow_existing: bool = False,
) -> str:
    actual_command = list(command)
    if BD_BATCH_ACTIVE and actual_command[0] == "bd" and actual_command[1:2] != ["dolt"]:
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
        msg = f"Command failed ({result.returncode}): {shell_command(actual_command)}\n{result.stderr.strip()}"
        raise MigrationError(msg)
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
    return [
        issue
        for issue in parse_bd_issue_list(output)
        if issue_metadata(issue).get("migration_source") == "legacy-markdown-workflow"
    ]


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


def reconcile_existing_beads_state(
    root: Path,
    features: Sequence[dict[str, Any]],
) -> int:
    roots = index_discovered_issues(discover_migrated_issues(root, "workflow:feature", issue_type="epic"))
    lifecycle = index_discovered_issues(
        discover_migrated_issues(root, "migration:legacy-workflow"),
        discriminator="formula_step_id",
    )
    implementation_tasks = index_discovered_issues(
        discover_migrated_issues(root, "migration:legacy-task"),
        discriminator="legacy_task_id",
    )
    reconciliation = index_discovered_issues(
        discover_migrated_issues(root, "migration:reconciliation"),
        discriminator="migration_role",
        default_discriminator="status-reconciliation",
    )

    recovered_features: set[str] = set()
    problems: list[str] = []
    for feature in features:
        slug = str(feature["slug"])
        beads = feature.setdefault("beads", {})

        root_id, did_recover, problem = reconcile_recorded_issue(
            feature=feature,
            recorded=str(beads.get("root_id") or ""),
            candidates=roots.get((slug, "root"), []),
            description="Beads roots",
        )
        if problem:
            problems.append(problem)
        elif did_recover:
            beads["root_id"] = root_id
            recovered_features.add(slug)

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
            elif did_recover:
                lifecycle_state[step_id] = issue_id
                recovered_features.add(slug)

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
            elif did_recover:
                task_state[label] = issue_id
                recovered_features.add(slug)

        reconciliation_id, did_recover, problem = reconcile_recorded_issue(
            feature=feature,
            recorded=str(beads.get("migration_reconciliation_id") or ""),
            candidates=reconciliation.get((slug, "status-reconciliation"), []),
            description="migration reconciliation tasks",
        )
        if problem:
            problems.append(problem)
        elif did_recover:
            beads["migration_reconciliation_id"] = reconciliation_id
            recovered_features.add(slug)

    if problems:
        raise MigrationError(
            "Existing migrated Beads state must be reconciled before import:\n  - " + "\n  - ".join(problems)
        )
    # Old interrupted imports used number-bearing metadata. Recovery is keyed
    # by the slug fallback above, then immediately canonicalized.
    for feature in features:
        beads = feature.get("beads", {})
        issue_ids = [beads.get("root_id"), beads.get("migration_reconciliation_id")]
        issue_ids.extend(beads.get("lifecycle", {}).values())
        issue_ids.extend(beads.get("implementation_tasks", {}).values())
        for issue_id in {str(value) for value in issue_ids if value}:
            bd_set_metadata(root, issue_id, {"feature_slug": feature["slug"], "feature_name": feature["title"]})
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
    if status:
        command.extend(("--status", status))
    output = run_command(command, cwd=root)
    issue_id = output.splitlines()[-1].strip() if output else ""
    if not issue_id or any(character.isspace() for character in issue_id):
        msg = f"Could not parse Beads issue ID from: {output!r}"
        raise MigrationError(msg)
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
    beads_dir = root / ".beads"
    if not beads_dir.exists():
        if not init_beads:
            msg = "Beads is not initialized. Run bd init --stealth --skip-agents or pass --init-beads."
            raise MigrationError(msg)
        run_command(["bd", "init", "--stealth", "--skip-agents"], cwd=root, capture=False)
    ensure_trailing_newline(root / ".beads/metadata.json")
    ensure_trailing_newline(root / ".beads/config.yaml")


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
    if not apply:
        print("Beads import dry-run (no mutations):")
        print_import_progress(import_progress(all_features))
        print("  - run a separate command with --apply to execute")
        return

    global BD_BATCH_ACTIVE
    BD_BATCH_ACTIVE = True
    print(f"APPLY STARTED: importing {len(features)} selected feature(s) into Beads with bounded batch commits.")
    print_import_progress(import_progress(all_features))
    ensure_bd_available(root, init_beads=init_beads)
    incomplete_features = [
        feature
        for feature in features
        if not feature_import_completed(feature) and feature.get("beads", {}).get("import_phase") != "relationships"
    ]
    recovered_issues = reconcile_existing_beads_state(root, incomplete_features)
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
    ensure_trailing_newline(root / ".beads/metadata.json")
    ensure_trailing_newline(root / ".beads/config.yaml")
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
        for key in ("review_reason", "reviewed_at"):
            if key in prior:
                candidate[key] = prior[key]
        candidates.append(candidate)
        if apply:
            write_text(target, text)
    manifest["delivered_record_candidates"] = candidates
    print(f"{'Drafted' if apply else 'Would draft'} {len(candidates)} delivered-record candidate(s).")


def review_delivered_record(manifest: dict[str, Any], slug: str, reason: str) -> None:
    if not reason.strip():
        message = "--reason is required for delivered-record semantic review"
        raise MigrationError(message)
    for candidate in manifest.get("delivered_record_candidates", []):
        if candidate.get("slug") == slug:
            candidate["reviewed"] = True
            candidate["review_reason"] = reason.strip()
            candidate["reviewed_at"] = utc_now()
            return
    message = f"No delivered-record candidate exists for {slug}"
    raise MigrationError(message)


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
    apply: bool,
    delete_tasks: bool,
    archive_dir: Path,
) -> None:
    unreviewed = [
        str(candidate.get("slug"))
        for candidate in manifest.get("delivered_record_candidates", [])
        if not candidate.get("reviewed")
    ]
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

    operations: list[str] = []
    for feature in manifest.get("features", []):
        tasks_path = root / feature["legacy_tasks_path"]
        if not tasks_path.exists():
            continue
        if delete_tasks:
            operations.append(f"delete {tasks_path.relative_to(root)}")
            if apply:
                tasks_path.unlink()
                feature["legacy_tasks_archive"] = "deleted; retained in Git history"
        else:
            archive_path = root / archive_dir / f"{feature['slug']}.md"
            operations.append(f"archive {tasks_path.relative_to(root)} -> {archive_path.relative_to(root)}")
            if apply:
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                if archive_path.exists():
                    msg = f"Legacy task archive already exists: {archive_path.relative_to(root)}"
                    raise MigrationError(msg)
                tasks_path.rename(archive_path)
                feature["legacy_tasks_archive"] = str(archive_path.relative_to(root))
        feature["has_tasks"] = False

    if not apply:
        print("Finalization dry-run:")
        for operation in operations:
            print("  -", operation)
        if not operations:
            print("  - no legacy tasks.md files remain")
        return
    manifest["migration_finalized"] = True
    manifest["finalized_at"] = utc_now()
    checker = root / "scripts/check-docs.py"
    if checker.exists():
        run_command(["uv", "run", str(checker)], cwd=root)
    print(f"Finalized {len(operations)} legacy task files and passed strict documentation validation.")


def verify_migration(root: Path, manifest: Mapping[str, Any], *, verify_beads: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    unreviewed_candidates = [
        str(candidate.get("slug"))
        for candidate in manifest.get("delivered_record_candidates", [])
        if not candidate.get("reviewed")
    ]
    if unreviewed_candidates:
        errors.append(
            "Delivered-record candidates require semantic review: " + ", ".join(sorted(unreviewed_candidates))
        )
    warnings: list[str] = []
    features = [feature for feature in manifest.get("features", []) if isinstance(feature, dict)]
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
        if verify_beads:
            root_id = feature.get("beads", {}).get("root_id")
            if not root_id:
                warnings.append(f"{feature['slug']} has no Beads root ID")
            else:
                result = subprocess.run(
                    ["bd", "show", root_id, "--json"],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    errors.append(f"Cannot resolve Beads root {root_id} for {feature['slug']}")

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


def repository_test_files(root: Path) -> list[Path]:
    ignored = {".git", ".venv", "node_modules", "build", "dist", "target", "__pycache__"}
    return sorted(
        path
        for path in root.rglob("*.py")
        if path.name.startswith("test_") or path.name.endswith("_test.py")
        if not any(part in ignored for part in path.relative_to(root).parts)
    )


def discover_baseline_test_command(root: Path) -> list[str] | None:
    if not repository_test_files(root):
        return None
    for name in ("mise.toml", ".mise.toml"):
        path = root / name
        if not path.exists():
            continue
        try:
            data = tomllib.loads(read_text(path))
        except tomllib.TOMLDecodeError:
            continue
        tasks = data.get("tasks")
        if isinstance(tasks, dict) and "test" in tasks and shutil.which("mise"):
            return ["mise", "run", "test"]
    if (root / "pyproject.toml").exists() and shutil.which("uv"):
        return ["uv", "run", "pytest"]
    return [sys.executable, "-m", "pytest"]


def run_baseline_command(root: Path, command: Sequence[str]) -> dict[str, Any]:
    result = subprocess.run(
        list(command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    no_tests = result.returncode == 5 and any(
        token in combined.casefold()
        for token in ("collected 0 items", "no tests ran", "no files were found in testpaths")
    )
    return {
        "command": shell_command(command),
        "status": "no_tests" if no_tests else ("passed" if result.returncode == 0 else "failed"),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


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
    return "\n".join(lines).rstrip() + "\n"


def baseline_repository(
    root: Path,
    *,
    docs_command: str | None,
    test_command: str | None,
    write: bool,
    baseline_json: Path,
    baseline_report: Path,
) -> int:
    checker = root / DOCS_CHECKER_PATH
    if docs_command:
        documentation = run_baseline_command(root, shlex.split(docs_command))
        documentation["note"] = "Explicit baseline documentation command."
    elif checker.exists():
        command = ["uv", "run", str(checker)] if shutil.which("uv") else [sys.executable, str(checker)]
        documentation = run_baseline_command(root, command)
        documentation["note"] = "Existing repository documentation checker."
    else:
        documentation = {
            "command": None,
            "status": "unavailable",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": "scripts/check-docs.py did not exist before template adoption.",
        }

    discovered_tests = repository_test_files(root)
    if test_command:
        tests = run_baseline_command(root, shlex.split(test_command))
        tests["note"] = "Explicit baseline test command."
    elif not discovered_tests:
        tests = {
            "command": None,
            "status": "no_tests",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": "No test_*.py or *_test.py files were found; no test command was run.",
        }
    else:
        command = discover_baseline_test_command(root)
        if command is None:
            tests = {
                "command": None,
                "status": "unavailable",
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "note": "Test files exist but no executable test command was discovered.",
            }
        else:
            tests = run_baseline_command(root, command)
            tests["note"] = f"Discovered {len(discovered_tests)} Python test file(s)."

    hk = capture_hk_inventory(root)
    checks: dict[str, dict[str, Any]] = {
        "documentation": documentation,
        "tests": tests,
        "hk": hk,
    }
    result: dict[str, Any] = {
        "generated_at": utc_now(),
        **checks,
    }
    if write:
        dump_json(root / baseline_json, result)
        write_text(root / baseline_report, render_baseline_report(result))
        print(f"Wrote {baseline_json} and {baseline_report}")
    for name, item in checks.items():
        print(f"{name}: {item['status']} ({item.get('command') or item.get('note')})")
    return 1 if any(item["status"] == "failed" for item in checks.values()) else 0


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
        "reason": reason,
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

    baseline = subparsers.add_parser("baseline", help="Record pre-adoption documentation and test capabilities")
    baseline.add_argument("--root", type=Path, help="Repository root; defaults to git root")
    baseline.add_argument("--docs-command", help="Explicit documentation validation command")
    baseline.add_argument("--test-command", help="Explicit test command")
    baseline.add_argument("--write", action="store_true", help="Write baseline JSON and Markdown reports")
    baseline.add_argument("--baseline-json", type=Path, default=DEFAULT_BASELINE_JSON)
    baseline.add_argument("--baseline-report", type=Path, default=DEFAULT_BASELINE_REPORT)
    baseline.add_argument("--json", action="store_true", help="Print a machine-readable result")

    scan = subparsers.add_parser("scan", help="Inventory the legacy workflow")
    add_common_arguments(scan)
    scan.add_argument("--write", action="store_true", help="Write manifest and report")

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
    return build_manifest(root, manifest_path=args.manifest)


def require_hk_reconciliation(manifest: Mapping[str, Any]) -> None:
    issues = manifest.get("hk_reconciliation", {}).get("issues", [])
    if issues:
        kinds = ", ".join(sorted({str(item.get("kind", "issue")) for item in issues}))
        message = f"hk reconciliation must be resolved before migration mutation: {kinds}"
        raise MigrationError(message)


def _main(args: argparse.Namespace) -> int:
    root = repository_root(args.root)
    try:
        if args.command == "baseline":
            return baseline_repository(
                root,
                docs_command=args.docs_command,
                test_command=args.test_command,
                write=args.write,
                baseline_json=args.baseline_json,
                baseline_report=args.baseline_report,
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
            review_delivered_record(manifest, args.feature, args.reason)
            save_manifest_and_report(root, args.manifest, args.report, manifest)
            return 0

        if args.command == "finalize":
            finalize_migration(
                root,
                manifest,
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
