"""Deterministic plan, task, and transitional commit-policy validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .core import DstackError, issue_labels, issue_type

PLAN_SECTIONS = (
    "Goals",
    "User-facing behavior",
    "Implemented design",
    "Compatibility and constraints",
    "Validation",
    "Non-goals",
)
COMMIT_TYPES = frozenset({"build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "test"})
COMMIT_SUBJECT_MAX = 100

_HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_PLACEHOLDER = re.compile(r"(?i)\b(?:todo|tbd|fixme|lorem ipsum)\b|<[^>\n]+>|\?\?\?|^\s*[-*]\s*\[ \]", re.MULTILINE)
_SCOPE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CONVENTIONAL_PREFIX = re.compile(r"^(?:build|chore|ci|docs|feat|fix|perf|refactor|revert|test)(?:\([^)]+\))?!?:\s+")


@dataclass(frozen=True)
class MarkdownSection:
    title: str
    level: int
    content: str


def markdown_sections(text: str) -> list[MarkdownSection]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        match = _HEADING.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    result: list[MarkdownSection] = []
    for position, (line_index, level, title) in enumerate(headings):
        end = len(lines)
        for next_index, next_level, _ in headings[position + 1 :]:
            if next_level <= level:
                end = next_index
                break
        content = "\n".join(lines[line_index + 1 : end]).strip()
        result.append(MarkdownSection(title=title, level=level, content=content))
    return result


def _sections_by_title(text: str) -> dict[str, list[MarkdownSection]]:
    result: dict[str, list[MarkdownSection]] = {}
    for section in markdown_sections(text):
        result.setdefault(section.title.casefold(), []).append(section)
    return result


def _issue_text(issue: Mapping[str, Any], field: str) -> str:
    value = issue.get(field)
    return str(value).strip() if isinstance(value, str) else ""


def validate_plan_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if issue_type(issue) != "task":
        errors.append("plan Bead must be a task issue")
    if "dstack:step:plan" not in issue_labels(issue):
        errors.append("plan Bead lacks dstack:step:plan label")
    if not _issue_text(issue, "description"):
        errors.append("native Beads description is empty")

    design = _issue_text(issue, "design")
    if not design:
        errors.append("native Beads design field is empty")
    else:
        all_sections = markdown_sections(design)
        if any(section.level < 3 for section in all_sections):
            errors.append("publishable plan headings must begin at level three")
        expected_headings = [(3, title.casefold()) for title in PLAN_SECTIONS]
        observed_headings = [(section.level, section.title.casefold()) for section in all_sections]
        if observed_headings != expected_headings:
            errors.append("plan headings must be exactly the publishable section set")
        sections = _sections_by_title(design)
        for required in PLAN_SECTIONS:
            matches = sections.get(required.casefold(), [])
            if not matches:
                errors.append(f"missing plan section: {required}")
            elif len(matches) > 1:
                errors.append(f"duplicate plan section: {required}")
            else:
                if matches[0].level != 3:
                    errors.append(f"plan section must be level-three: {required}")
                if not matches[0].content:
                    errors.append(f"empty plan section: {required}")
        if _PLACEHOLDER.search(design):
            errors.append("plan contains an unresolved placeholder or unchecked item")

    acceptance = _issue_text(issue, "acceptance_criteria")
    if not acceptance:
        errors.append("native Beads acceptance criteria are empty")
    elif _PLACEHOLDER.search(acceptance):
        errors.append("acceptance criteria contain a placeholder or unchecked item")

    return {
        "status": "ok" if not errors else "invalid",
        "bead": issue.get("id"),
        "errors": errors,
        "required_sections": list(PLAN_SECTIONS),
    }


def commit_policy(issue: Mapping[str, Any]) -> tuple[str | None, str | None, list[str]]:
    """Read the legacy commit labels while active workflows transition."""

    labels = issue_labels(issue)
    type_labels = [label.removeprefix("dstack:commit:") for label in labels if label.startswith("dstack:commit:")]
    scope_labels = [label.removeprefix("dstack:scope:") for label in labels if label.startswith("dstack:scope:")]
    errors: list[str] = []
    commit_type: str | None = None
    scope: str | None = None

    if len(type_labels) != 1:
        errors.append("implementation Bead must have exactly one dstack:commit:<type> label")
    elif type_labels[0] not in COMMIT_TYPES:
        errors.append(f"unsupported commit type: {type_labels[0]}")
    else:
        commit_type = type_labels[0]

    if len(scope_labels) > 1:
        errors.append("implementation Bead may have at most one dstack:scope:<scope> label")
    elif scope_labels:
        if not _SCOPE.fullmatch(scope_labels[0]):
            errors.append(f"invalid commit scope: {scope_labels[0]}")
        else:
            scope = scope_labels[0]
    return commit_type, scope, errors


def validate_task_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if issue_type(issue) != "task":
        errors.append("implementation Bead must be a task issue")
    if "dstack:work:implementation" not in issue_labels(issue):
        errors.append("implementation Bead lacks dstack:work:implementation label")
    if not _issue_text(issue, "title"):
        errors.append("implementation Bead title is empty")
    description = _issue_text(issue, "description")
    if not description:
        errors.append("implementation Bead description is empty")
    elif not any(label.startswith("dstack:commit:") for label in issue_labels(issue)):
        commit_material = description.split("\n\n", 1)[0]
        bullets = [line.strip() for line in commit_material.splitlines() if line.strip()]
        if not bullets or any(not re.match(r"^-\s+\S", line) for line in bullets):
            errors.append("implementation Bead description must begin with Markdown commit bullets")
        elif _PLACEHOLDER.search(commit_material):
            errors.append("implementation Bead description commit bullets contain a placeholder")
    acceptance = _issue_text(issue, "acceptance_criteria")
    if not acceptance:
        errors.append("implementation Bead acceptance criteria are empty")
    elif _PLACEHOLDER.search(acceptance):
        errors.append("acceptance criteria contain a placeholder or unchecked item")

    return {
        "status": "ok" if not errors else "invalid",
        "bead": issue.get("id"),
        "errors": errors,
    }


def _lower_initial(value: str) -> str:
    for index, character in enumerate(value):
        if character.isalpha():
            return value[:index] + character.lower() + value[index + 1 :]
    return value


def commit_subject(issue: Mapping[str, Any]) -> str:
    validation = validate_task_issue(issue)
    commit_type, scope, commit_errors = commit_policy(issue)
    errors = [error for error in validation["errors"] if "title" in error]
    errors.extend(commit_errors)
    if errors:
        raise DstackError("cannot derive commit subject: " + "; ".join(errors))

    title = _issue_text(issue, "title")
    if _CONVENTIONAL_PREFIX.match(title):
        raise DstackError("implementation Bead title must not include a Conventional Commit prefix")
    summary = _lower_initial(title.rstrip().rstrip("."))
    prefix = f"{commit_type}({scope})" if scope else str(commit_type)
    subject = f"{prefix}: {summary}"
    if len(subject) > COMMIT_SUBJECT_MAX:
        raise DstackError(
            f"derived commit subject is {len(subject)} characters; update the Bead title to fit {COMMIT_SUBJECT_MAX}"
        )
    return subject


def no_repository_change_reason(issue: Mapping[str, Any]) -> str | None:
    notes = _issue_text(issue, "notes")
    match = re.search(r"(?im)^No repository change:\s*(\S.+)$", notes)
    return match.group(1).strip() if match else None
