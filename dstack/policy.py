"""Deterministic plan, task, and commit-policy validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .core import DstackError, issue_labels, issue_type

PLAN_SECTIONS = (
    "Goal",
    "Current behavior",
    "Proposed behavior",
    "Repository evidence",
    "Questions and answers",
    "Decisions and rationale",
    "Compatibility",
    "Documentation impact",
    "Non-goals",
)
DOCUMENTATION_AUDIENCES = ("End-user", "Developer", "Future-agent")
COMMIT_TYPES = frozenset({"build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "test"})
COMMIT_SUBJECT_MAX = 100

_HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_PLACEHOLDER = re.compile(r"(?i)\b(?:todo|tbd|fixme|lorem ipsum)\b|<[^>\n]+>|\?\?\?|^\s*[-*]\s*\[ \]", re.MULTILINE)
_OPEN_QUESTION = re.compile(r"(?im)^\s*(?:[-*]\s*)?(?:status\s*:\s*)?(?:open|unresolved|pending|unknown)(?:\s|$|:)")
_QUESTION_LINE = re.compile(r"(?i)^\s*(?:[-*]\s*)?Question(?:\s+\d+)?\s*:\s*(\S.+?)\s*$")
_ANSWER_LINE = re.compile(r"(?i)^\s*(?:[-*]\s*)?Answer(?:\s+\d+)?\s*:\s*(\S.+?)\s*$")
_NO_MATERIAL_QUESTIONS = re.compile(r"(?i)^\s*(?:[-*]\s*)?No material questions(?: remain)?\s*:\s*(\S.+?)\s*$")
_UNRESOLVED_ANSWER = re.compile(r"(?i)^(?:open|unresolved|pending|unknown|not decided)\b")
_DOC_LINE = re.compile(
    r"(?im)^\s*[-*]\s*"
    r"(?P<audience>end[- ]users?|developers?|future[- ]agents?)\s*:\s*"
    r"(?P<status>required|not affected)\s*(?:[-–—:]\s*)(?P<reason>.+?)\s*$"
)
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
    if issue_type(issue) not in {"task", "feature"}:
        errors.append("plan Bead must be a task or feature")
    if "dstack:step:plan" not in issue_labels(issue):
        errors.append("plan Bead lacks dstack:step:plan label")

    plan = _issue_text(issue, "design")
    if not plan:
        errors.append("native Beads design field is empty")
        sections: dict[str, list[MarkdownSection]] = {}
    else:
        sections = _sections_by_title(plan)
        for required in PLAN_SECTIONS:
            matches = sections.get(required.casefold(), [])
            if not matches:
                errors.append(f"missing plan section: {required}")
            elif len(matches) > 1:
                errors.append(f"duplicate plan section: {required}")
            elif not matches[0].content:
                errors.append(f"empty plan section: {required}")
        if _PLACEHOLDER.search(plan):
            errors.append("plan contains an unresolved placeholder or unchecked item")

        questions = sections.get("questions and answers", [])
        if questions:
            question_content = questions[0].content
            if _OPEN_QUESTION.search(question_content):
                errors.append("Questions and answers contains an unresolved question")
            errors.extend(question_ledger_errors(question_content))

        docs = sections.get("documentation impact", [])
        if docs:
            nested = _sections_by_title(docs[0].content)
            for audience in ("End users", "Developers", "Future agents"):
                matches = nested.get(audience.casefold(), [])
                if not matches:
                    errors.append(f"Documentation impact lacks {audience}")
                elif len(matches) > 1:
                    errors.append(f"Documentation impact duplicates {audience}")
                elif not matches[0].content:
                    errors.append(f"Documentation impact has no assessment for {audience}")

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
        "documentation_audiences": list(DOCUMENTATION_AUDIENCES),
    }


def question_ledger_errors(content: str) -> list[str]:
    errors: list[str] = []
    no_question_reasons: list[str] = []
    pairs = 0
    pending_question: str | None = None

    for raw_line in content.splitlines():
        if match := _NO_MATERIAL_QUESTIONS.match(raw_line):
            no_question_reasons.append(match.group(1).strip())
            continue
        if match := _QUESTION_LINE.match(raw_line):
            if pending_question is not None:
                errors.append("Questions and answers has a Question without a following Answer")
            pending_question = match.group(1).strip()
            continue
        if match := _ANSWER_LINE.match(raw_line):
            answer = match.group(1).strip()
            if pending_question is None:
                errors.append("Questions and answers has an Answer without a preceding Question")
            else:
                if _UNRESOLVED_ANSWER.match(answer):
                    errors.append("Questions and answers contains an unresolved answer")
                pairs += 1
                pending_question = None

    if pending_question is not None:
        errors.append("Questions and answers has a Question without a following Answer")
    if len(no_question_reasons) > 1:
        errors.append("Questions and answers duplicates the no-material-questions declaration")
    if no_question_reasons and pairs:
        errors.append(
            "Questions and answers cannot combine answered questions with a no-material-questions declaration"
        )
    if no_question_reasons and len(no_question_reasons[0]) < 12:
        errors.append("no-material-questions declaration must explain why no user decision was required")
    if not no_question_reasons and pairs == 0:
        errors.append(
            "Questions and answers must contain paired `Question:`/`Answer:` lines or `No material questions: <reason>`"
        )
    return errors


def documentation_impact(issue: Mapping[str, Any]) -> tuple[dict[str, dict[str, str]], list[str]]:
    text = "\n\n".join(value for field in ("description", "design", "notes") if (value := _issue_text(issue, field)))
    found: dict[str, dict[str, str]] = {}
    duplicates: set[str] = set()
    aliases = {
        "end-user": "End-user",
        "end-users": "End-user",
        "end user": "End-user",
        "end users": "End-user",
        "developer": "Developer",
        "developers": "Developer",
        "future-agent": "Future-agent",
        "future-agents": "Future-agent",
        "future agent": "Future-agent",
        "future agents": "Future-agent",
    }
    for match in _DOC_LINE.finditer(text):
        audience = aliases[match.group("audience").casefold()]
        if audience in found:
            duplicates.add(audience)
            continue
        found[audience] = {
            "status": match.group("status").casefold(),
            "reason": match.group("reason").strip(),
        }

    errors: list[str] = []
    for audience in DOCUMENTATION_AUDIENCES:
        if audience not in found:
            errors.append(f"missing documentation-impact classification for {audience}")
        elif len(found[audience]["reason"]) < 8:
            errors.append(f"documentation-impact reason for {audience} is too weak")
    for audience in sorted(duplicates):
        errors.append(f"duplicate documentation-impact classification for {audience}")
    return found, errors


def commit_policy(issue: Mapping[str, Any]) -> tuple[str | None, str | None, list[str]]:
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
    if issue_type(issue) in {"epic", "molecule", "gate"}:
        errors.append("implementation work must be a concrete non-container Bead")
    if "dstack:work:implementation" not in issue_labels(issue):
        errors.append("implementation Bead lacks dstack:work:implementation label")
    if not _issue_text(issue, "title"):
        errors.append("implementation Bead title is empty")
    if not _issue_text(issue, "description"):
        errors.append("implementation Bead description is empty")
    acceptance = _issue_text(issue, "acceptance_criteria")
    if not acceptance:
        errors.append("implementation Bead acceptance criteria are empty")
    elif _PLACEHOLDER.search(acceptance):
        errors.append("acceptance criteria contain a placeholder or unchecked item")

    impact, impact_errors = documentation_impact(issue)
    errors.extend(impact_errors)
    commit_type, scope, commit_errors = commit_policy(issue)
    errors.extend(commit_errors)
    return {
        "status": "ok" if not errors else "invalid",
        "bead": issue.get("id"),
        "errors": errors,
        "documentation_impact": impact,
        "commit": {"type": commit_type, "scope": scope},
    }


def _lower_initial(value: str) -> str:
    for index, character in enumerate(value):
        if character.isalpha():
            return value[:index] + character.lower() + value[index + 1 :]
    return value


def commit_subject(issue: Mapping[str, Any]) -> str:
    validation = validate_task_issue(issue)
    commit_errors = [
        error for error in validation["errors"] if "commit" in error or "scope" in error or "title" in error
    ]
    if commit_errors:
        raise DstackError("cannot derive commit subject: " + "; ".join(commit_errors))

    title = _issue_text(issue, "title")
    if _CONVENTIONAL_PREFIX.match(title):
        raise DstackError("implementation Bead title must not include a Conventional Commit prefix")
    summary = _lower_initial(title.rstrip().rstrip("."))
    commit_type = str(validation["commit"]["type"])
    scope = validation["commit"]["scope"]
    prefix = f"{commit_type}({scope})" if scope else commit_type
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
