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
COMMIT_SUBJECT_MAX = 100
MAX_IMPLEMENTATION_NOTES = 100
MAX_IMPLEMENTATION_NOTE_LENGTH = 96
MAX_IMPLEMENTATION_BODY_LENGTH = 4000
MAX_IMPLEMENTATION_NOTES_FIELD_LENGTH = 50000

_HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_PLACEHOLDER = re.compile(r"(?i)\b(?:todo|tbd|fixme|lorem ipsum)\b|\?\?\?|^\s*[-*]\s*\[ \]", re.MULTILINE)
_FEATURE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CONVENTIONAL_PREFIX = re.compile(
    r"^(?P<type>build|chore|ci|docs|feat|fix|perf|refactor|revert|test)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+"
)
_OWNERSHIP_TOKEN = re.compile(r"(?i)\b(?:Task|Beads):\s*\S+")
_NOTE_LINE_END = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")


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


def _bounded_notes_text(issue: Mapping[str, Any]) -> str:
    value = issue.get("notes")
    if not isinstance(value, str):
        return ""
    if len(value) > MAX_IMPLEMENTATION_NOTES_FIELD_LENGTH:
        raise DstackError(
            "implementation notes field exceeds the bounded limit of "
            f"{MAX_IMPLEMENTATION_NOTES_FIELD_LENGTH} characters"
        )
    return value


def _iter_note_lines(notes: str):
    start = 0
    for match in _NOTE_LINE_END.finditer(notes):
        yield notes[start : match.start()]
        start = match.end()
    if start < len(notes):
        yield notes[start:]


def _normalize_implementation_note(value: str) -> str:
    return value.strip()


def _lint_implementation_note(value: str) -> str:
    normalized = _normalize_implementation_note(value)
    if not normalized:
        raise DstackError("implementation note must contain text after Implementation:")
    if len(normalized) > MAX_IMPLEMENTATION_NOTE_LENGTH:
        raise DstackError(
            f"implementation note exceeds the bounded length of {MAX_IMPLEMENTATION_NOTE_LENGTH} characters"
        )
    return normalized


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
    if not _issue_text(issue, "design"):
        errors.append("implementation Bead design is empty")
    try:
        execution_notes = implementation_notes(issue)
    except DstackError as exc:
        errors.append(str(exc))
    else:
        if execution_notes and no_repository_change_reason(issue):
            errors.append("implementation notes cannot be combined with a No repository change reason")
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


def commit_subject(issue: Mapping[str, Any], feature_slug: str) -> str:
    validation = validate_task_issue(issue)
    errors = [error for error in validation["errors"] if "title" in error]
    if errors:
        raise DstackError("cannot derive commit subject: " + "; ".join(errors))
    if not _FEATURE_SLUG.fullmatch(feature_slug):
        raise DstackError(f"invalid feature slug for commit subject: {feature_slug!r}")

    title = _issue_text(issue, "title")
    prefix = _CONVENTIONAL_PREFIX.match(title)
    kind, breaking = "feat", ""
    if prefix:
        scope = prefix.group("scope")
        if scope is not None and scope != feature_slug:
            raise DstackError("task title scope must match the feature slug")
        kind, breaking = prefix.group("type"), prefix.group("breaking") or ""
        title = title[prefix.end() :]
    summary = _lower_initial(title.rstrip().rstrip("."))
    if not summary or any(character in summary for character in "\r\n"):
        raise DstackError("task title must contain one non-empty summary line")
    subject = f"{kind}({feature_slug}){breaking}: {summary}"
    if len(subject) > COMMIT_SUBJECT_MAX:
        raise DstackError(
            f"derived commit subject is {len(subject)} characters; update the Bead title to fit {COMMIT_SUBJECT_MAX}"
        )
    return subject


def implementation_notes(issue: Mapping[str, Any]) -> list[str]:
    """Return ordered, bounded execution notes that may become commit bullets."""

    notes = _bounded_notes_text(issue)
    result: list[str] = []
    prefix = "Implementation:"
    for line in _iter_note_lines(notes):
        candidate = line.strip()
        if not candidate:
            continue
        if _OWNERSHIP_TOKEN.search(candidate):
            raise DstackError("implementation notes must not contain Task: or Beads: ownership footers")
        if not candidate.startswith(prefix):
            continue
        value = _lint_implementation_note(candidate.removeprefix(prefix))
        if len(result) >= MAX_IMPLEMENTATION_NOTES:
            raise DstackError(f"implementation notes exceed the bounded limit of {MAX_IMPLEMENTATION_NOTES} entries")
        result.append(value)

    return result


def no_repository_change_reason(issue: Mapping[str, Any]) -> str | None:
    notes = _bounded_notes_text(issue)
    match = re.search(r"(?im)^No repository change:\s*(\S.+)$", notes)
    return match.group(1).strip() if match else None
