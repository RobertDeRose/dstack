"""Mechanical plan, task, and commit-format validation; skills assess meaning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from markdown_it import MarkdownIt

from .beads import issue_labels, issue_type
from .core import DstackError

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

_FEATURE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CONVENTIONAL_PREFIX = re.compile(
    r"^(?P<type>build|chore|ci|docs|feat|fix|perf|refactor|revert|test)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+"
)


def reject_beads_paths(paths: Sequence[str]) -> None:
    committed_policy = {
        ".beads/PRIME.md",
        ".beads/formulas/dstack-feature.formula.toml",
    }
    invalid = sorted(
        path for path in paths if (path == ".beads" or path.startswith(".beads/")) and path not in committed_policy
    )
    if invalid:
        raise DstackError(
            "implementation commits may not include Beads configuration or runtime state; "
            "commit intentional Beads maintenance separately: " + ", ".join(invalid)
        )


@dataclass(frozen=True)
class MarkdownSection:
    title: str
    level: int
    content: str


def markdown_sections(text: str) -> list[MarkdownSection]:
    lines = text.splitlines()
    tokens = MarkdownIt("commonmark").parse(text)
    headings = [
        (token.map[0], token.map[1], int(token.tag[1:]), tokens[index + 1].content.strip())
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.level == 0 and token.map is not None
    ]

    result: list[MarkdownSection] = []
    for position, (_, content_start, level, title) in enumerate(headings):
        end = len(lines)
        for next_index, _, next_level, _ in headings[position + 1 :]:
            if next_level <= level:
                end = next_index
                break
        content = "\n".join(lines[content_start:end]).strip()
        result.append(MarkdownSection(title=title, level=level, content=content))
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


def _lint_implementation_note(value: str) -> str:
    normalized = value.strip()
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
        sections = [section for section in markdown_sections(design) if section.level <= 3]
        if any(section.level < 3 for section in sections):
            errors.append("publishable plan headings must begin at level three")
        expected_headings = [(3, title.casefold()) for title in PLAN_SECTIONS]
        observed_headings = [(section.level, section.title.casefold()) for section in sections]
        if observed_headings != expected_headings:
            errors.append("plan headings must be exactly the publishable section set")
        for required in PLAN_SECTIONS:
            matches = [section for section in sections if section.title.casefold() == required.casefold()]
            if not matches:
                errors.append(f"missing plan section: {required}")
            elif len(matches) > 1:
                errors.append(f"duplicate plan section: {required}")
            else:
                if matches[0].level != 3:
                    errors.append(f"plan section must be level-three: {required}")
                if not matches[0].content:
                    errors.append(f"empty plan section: {required}")

    acceptance = _issue_text(issue, "acceptance_criteria")
    if not acceptance:
        errors.append("native Beads acceptance criteria are empty")

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
    title = _issue_text(issue, "title")
    if not title:
        raise DstackError("cannot derive commit subject: implementation Bead title is empty")
    if not _FEATURE_SLUG.fullmatch(feature_slug):
        raise DstackError(f"invalid feature slug for commit subject: {feature_slug!r}")

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


def build_commit_message(subject: str, body: str, task_id: str) -> str:
    if not subject or "\n" in subject:
        raise DstackError("commit subject must be one non-empty line")
    if not task_id or task_id != task_id.strip() or any(character.isspace() for character in task_id):
        raise DstackError("Task ID must be one non-empty token")
    if re.search(r"(?im)^(?:Task|Beads):\s*", body):
        raise DstackError("commit body must not contain an ownership footer; dStack adds it")
    parts = [subject]
    if body.strip():
        parts.extend(["", body.strip()])
    parts.extend(["", f"Task: {task_id}"])
    return "\n".join(parts).rstrip() + "\n"


def task_commit_body(task: Mapping[str, object]) -> str:
    notes = implementation_notes(task)
    if not notes:
        raise DstackError("implementation task requires at least one Implementation note before committing")
    body = "\n".join(f"- {note}" for note in notes)
    if len(body) > MAX_IMPLEMENTATION_BODY_LENGTH:
        raise DstackError(
            f"implementation commit body exceeds the bounded limit of {MAX_IMPLEMENTATION_BODY_LENGTH} characters"
        )
    return body


def canonical_docs_message(feature: Mapping[str, object], slug: str, task_id: str) -> str:
    title = str(feature.get("title") or "").strip().removeprefix("Feature: ").strip()
    if not title or "\n" in title:
        raise DstackError("feature title must be one non-empty line for the documentation commit")
    return build_commit_message(f"docs({slug}): {title}", "", task_id)


def canonical_task_message(task: Mapping[str, object], slug: str) -> str:
    task_id = str(task.get("id") or "")
    return build_commit_message(commit_subject(task, slug), task_commit_body(task), task_id)


def commit_record_matches_message(record: Mapping[str, object], message: str) -> bool:
    subject = str(record.get("subject") or "")
    body = str(record.get("body") or "")
    observed = f"{subject}\n\n{body}" if body else subject
    return observed.rstrip() == message.rstrip()


def validate_commit_paths(paths: Sequence[str], slug: str, *, documentation: bool) -> None:
    """Enforce only the Beads-state exclusion and the feature-documentation boundary."""

    reject_beads_paths(paths)
    directory = f"docs/src/features/{slug}"
    if documentation:
        invalid = [path for path in paths if path != "docs/src/SUMMARY.md" and not path.startswith(directory + "/")]
        if invalid:
            raise DstackError("feature documentation commit contains non-feature paths: " + ", ".join(invalid))
    else:
        invalid = [path for path in paths if path == directory or path.startswith(directory + "/")]
        if invalid:
            raise DstackError(
                "feature documentation belongs to the close step, not an implementation task: " + ", ".join(invalid)
            )


def implementation_notes(issue: Mapping[str, Any]) -> list[str]:
    """Return ordered, bounded execution notes that may become commit bullets."""

    notes = _bounded_notes_text(issue)
    result: list[str] = []
    prefix = "Implementation:"
    for line in notes.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
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
