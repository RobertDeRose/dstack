"""Canonical mdBook foundation and stateless validation."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .output import emit
from .core import DstackError, read_utf8_text, replace_text_if_unchanged, run


DESIGN_SCAFFOLD = """# Feature design

## Outcome

{planned_intent}

Acceptance:

{planned_acceptance}

## Non-goals

## Design

## Failure, security, and compatibility

## Validation

## Documentation impact
"""

RECONCILIATION_SCAFFOLD = """# {title}

[Design record](design.md)

## Delivered outcome

## Material deviations

## Validation

## Documentation links

## Remaining limitations
"""

ALIGNMENT_RECONCILIATION_SCAFFOLD = """# Alignment reconciliation

## Delivered outcome

## Material deviations

## Validation

## Documentation links

## Remaining limitations
"""

RECORD_SUBJECTS = {
    "feature-design": (
        "Outcome",
        "Non-goals",
        "Design",
        "Failure, security, and compatibility",
        "Validation",
        "Documentation impact",
    ),
    "feature-reconciliation": (
        "Delivered outcome",
        "Material deviations",
        "Validation",
        "Documentation links",
        "Remaining limitations",
    ),
    "alignment-reconciliation": (
        "Delivered outcome",
        "Material deviations",
        "Validation",
        "Documentation links",
        "Remaining limitations",
    ),
}

# Historical records used earlier, more verbose section layouts. They remain
# valid evidence; new records use only the compact canonical subjects above.
RECORD_SUBJECT_ALTERNATIVES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "feature-design": {
        "Outcome": (("Outcome",), ("Goal",), ("Feature summary",)),
        "Non-goals": (("Non-goals",),),
        "Design": (("Design",), ("Proposed design",)),
        "Failure, security, and compatibility": (
            ("Failure, security, and compatibility",),
            ("Failure / security / compatibility behavior",),
            ("Failure behavior", "Security implications", "Compatibility and migration implications"),
            (
                "Failure, recovery, and state behavior",
                "Security implications",
                "Compatibility and migration implications",
            ),
        ),
        "Validation": (("Validation",), ("Validation strategy",)),
        "Documentation impact": (("Documentation impact",),),
    },
    "feature-reconciliation": {
        "Delivered outcome": (("Delivered outcome",), ("Delivered capability",)),
        "Material deviations": (("Material deviations",), ("Design reconciliation",)),
        "Validation": (("Validation",), ("Validation and limitations",)),
        "Documentation links": (("Documentation links",), ("Documentation",)),
        "Remaining limitations": (("Remaining limitations",), ("Validation and limitations",)),
    },
    "alignment-reconciliation": {
        "Delivered outcome": (("Delivered outcome",), ("Delivered corrections",)),
        "Material deviations": (("Material deviations",), ("Architecture integration",)),
        "Validation": (("Validation",), ("Validation evidence",)),
        "Documentation links": (("Documentation links",), ("Documentation and operator effects",)),
        "Remaining limitations": (("Remaining limitations",), ("Remaining findings and limitations",)),
    },
}


# Public sentinel used by callers. Link targets are scanned rather than parsed
# with this regular expression so balanced parentheses remain intact.
LINK_PATTERN = re.compile(r"!?\[[^]]*\]\((.+)\)")
INCLUDE_PATTERN = re.compile(r"\{\{#include\s+([^}\s]+)[^}]*\}\}")
FENCE_PATTERN = re.compile(r"^( {0,3})(`{3,}|~{3,})")

CORE_NAVIGATION = (
    ("Project", "index.md"),
    ("Architecture", "architecture/index.md"),
    ("Development", "development/index.md"),
    ("Documentation", "development/documentation.md"),
    ("Feature Records", "features/index.md"),
)
SUPPORTED_MDBOOK_VERSION_OUTPUT = "mdbook v0.5.3"


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _mask_markdown_code(text: str) -> str:
    """Replace Markdown code with spaces while preserving offsets and newlines."""

    masked = list(text)
    lines = text.splitlines(keepends=True)
    offset = 0
    fence: tuple[str, int] | None = None
    for line in lines:
        plain = line.rstrip("\r\n")
        match = FENCE_PATTERN.match(plain)
        opened = False
        if fence is None and match:
            marker = match.group(2)
            fence = (marker[0], len(marker))
            opened = True
        if fence is not None:
            for index in range(offset, offset + len(line)):
                if masked[index] not in "\r\n":
                    masked[index] = " "
            if (
                not opened
                and match
                and match.group(2)[0] == fence[0]
                and len(match.group(2)) >= fence[1]
                and plain[match.end() :].strip() == ""
            ):
                fence = None
        offset += len(line)

    masked_text = "".join(masked)
    index = 0
    while index < len(masked_text):
        if masked_text[index] != "`" or _is_escaped(masked_text, index):
            index += 1
            continue
        run = 1
        while index + run < len(masked_text) and masked_text[index + run] == "`":
            run += 1
        end = index + run
        while end < len(masked_text):
            end = masked_text.find("`", end)
            if end < 0:
                break
            closing = 1
            while end + closing < len(masked_text) and masked_text[end + closing] == "`":
                closing += 1
            if closing == run:
                for position in range(index, end + run):
                    if masked[position] not in "\r\n":
                        masked[position] = " "
                index = end + run
                break
            end += closing
        else:
            index += run
            continue
        if end < 0:
            index += run
    return "".join(masked)


def _markdown_matches(text: str, pattern: re.Pattern[str]) -> tuple[str, list[re.Match[str]]]:
    masked = _mask_markdown_code(text)
    matches = []
    for match in pattern.finditer(masked):
        syntax = match.start()
        if pattern is LINK_PATTERN and masked[syntax] == "!":
            if _is_escaped(masked, syntax) or _is_escaped(masked, syntax + 1):
                continue
        elif _is_escaped(masked, syntax):
            continue
        matches.append(match)
    return masked, matches


def _markdown_link_target_spans(text: str) -> list[tuple[int, int]]:
    """Return Markdown inline-link target spans outside code.

    A small scanner is both stricter and more accurate than a single regex:
    it respects escapes and keeps balanced parentheses in local paths.
    """

    masked = _mask_markdown_code(text)
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(masked):
        syntax = index
        if masked[index] == "!":
            if _is_escaped(masked, index) or index + 1 >= len(masked) or masked[index + 1] != "[":
                index += 1
                continue
            index += 1
        if masked[index] != "[" or _is_escaped(masked, index):
            index = syntax + 1
            continue

        label_end = index + 1
        while label_end < len(masked):
            if masked[label_end] == "]" and not _is_escaped(masked, label_end):
                break
            label_end += 1
        if label_end >= len(masked) or label_end + 1 >= len(masked) or masked[label_end + 1] != "(":
            index = syntax + 1
            continue

        target_start = label_end + 2
        cursor = target_start
        depth = 1
        while cursor < len(masked):
            character = masked[cursor]
            if _is_escaped(masked, cursor):
                cursor += 1
                continue
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if depth == 0 and cursor > target_start:
            spans.append((target_start, cursor))
            index = cursor + 1
        else:
            index = syntax + 1
    return spans


def markdown_values(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Return values matched by a Markdown pattern outside code spans."""

    if pattern is LINK_PATTERN:
        return [text[start:end] for start, end in _markdown_link_target_spans(text)]
    _, matches = _markdown_matches(text, pattern)
    return [match.group(1) for match in matches]


# Keep the internal spelling for local documentation helpers.
_markdown_values = markdown_values


HEADING_PATTERN = re.compile(r"^(#{1,6}) ([^#\n].*?)[ \t]*$", re.MULTILINE)
PLACEHOLDER_PATTERN = re.compile(r"(?i)\b(?:todo|tbd|fixme|lorem ipsum)\b|<[^>\n]+>|\{\{[^}\n]+\}\}")
REFERENCE_LINK_PATTERN = re.compile(r"(?<!!)\[[^]\n]+\]\[[^]\n]*\]")


def validate_record(
    text: str,
    kind: str,
    *,
    source: Path | None = None,
    source_root: Path | None = None,
) -> None:
    subjects = RECORD_SUBJECTS.get(kind)
    if not subjects:
        raise DstackError(f"unknown documentation record kind: {kind}")
    alternatives = RECORD_SUBJECT_ALTERNATIVES[kind]
    masked = _mask_markdown_code(text)
    headings = list(HEADING_PATTERN.finditer(masked))
    by_title: dict[str, list[re.Match[str]]] = {}
    for heading in headings:
        title = heading.group(2).strip()
        by_title.setdefault(title.casefold(), []).append(heading)
    duplicates = sorted(matches[0].group(2).strip() for matches in by_title.values() if len(matches) > 1)
    errors = [f"duplicate heading: {title}" for title in duplicates]
    if PLACEHOLDER_PATTERN.search(masked):
        errors.append("record contains a placeholder or TODO")
    if REFERENCE_LINK_PATTERN.search(masked):
        errors.append("record uses unsupported reference-style local links")

    def validate_subject(subject: str, heading: re.Match[str]) -> None:
        level = len(heading.group(1))
        end = len(text)
        for candidate in headings:
            if candidate.start() <= heading.start():
                continue
            if len(candidate.group(1)) <= level:
                end = candidate.start()
                break
        content = text[heading.end() : end].strip()
        if not re.search(r"[A-Za-z0-9]", _mask_markdown_code(content)):
            errors.append(f"section has no substantive content: {subject}")
            return
        if content.startswith("Not applicable"):
            prefix = "Not applicable — "
            reason = content.removeprefix(prefix).strip() if content.startswith(prefix) else ""
            if (
                not reason
                or PLACEHOLDER_PATTERN.search(reason)
                or reason.casefold()
                in {
                    "none",
                    "n/a",
                    "not applicable",
                    "no impact",
                }
            ):
                errors.append(f"section requires 'Not applicable — <specific reason>': {subject}")

    for subject in subjects:
        selected: tuple[str, ...] | None = None
        for option in alternatives[subject]:
            if all(by_title.get(title.casefold()) for title in option):
                selected = option
                break
        if selected is None:
            errors.append(f"missing required section: {subject}")
            continue
        for title in selected:
            validate_subject(title, by_title[title.casefold()][0])

    if source is not None and source_root is not None:
        root = source_root.resolve()
        try:
            source.resolve().relative_to(root)
            base = source.parent
        except ValueError:
            base = root
        for raw in _markdown_values(text, LINK_PATTERN):
            target = urlsplit(_raw_target(raw))
            if target.scheme or target.netloc or not target.path:
                continue
            relative = Path(unquote(target.path))
            candidate = (base / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"record local link escapes repository: {raw}")
                continue
            if not candidate.is_file():
                errors.append(f"record local link is missing: {raw}")
    if errors:
        raise DstackError(f"invalid {kind} record: " + "; ".join(sorted(set(errors))))


def foundation_files(project: str) -> dict[str, str]:
    title = project.replace("-", " ").replace("_", " ").strip().title() or "Project"
    return {
        "docs/book.toml": (f'[book]\ntitle = {json.dumps(title)}\nlanguage = "en"\nsrc = "src"\n'),
        "docs/src/SUMMARY.md": (
            "# Summary\n\n"
            "- [Project](index.md)\n"
            "- [Architecture](architecture/index.md)\n"
            "- [Development](development/index.md)\n"
            "  - [Documentation](development/documentation.md)\n"
            "- [Feature Records](features/index.md)\n"
        ),
        "docs/src/index.md": (
            f"# {title}\n\n"
            f"This book documents {title} for users, operators, developers, "
            "reviewers, and future maintainers.\n"
        ),
        "docs/src/architecture/index.md": (
            "# Architecture\n\n"
            "Describe the current system, its components, relationships, "
            "boundaries, and durable invariants here.\n"
        ),
        "docs/src/development/index.md": (
            "# Development\n\nDescribe how to build, test, change, validate, and release this project here.\n"
        ),
        "docs/src/development/documentation.md": (
            "# Documentation\n\n"
            "Put documentation where a reader would look based on the question "
            "they are trying to answer. Keep current product behavior in current "
            "architecture, user, operator, development, and reference pages; "
            "keep accepted change intent and delivery reconciliation in feature "
            "records. Humans and agents use the same durable documentation.\n"
        ),
        "docs/src/features/index.md": (
            "# Feature Records\n\n"
            "Feature records preserve accepted change intent and reconcile it "
            "with delivered behavior. Current product guidance belongs in the "
            "sections where readers look for that behavior.\n"
        ),
    }


def _inside(path: Path, parent: Path, message: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise DstackError(message) from exc
    return resolved


def _book_source_value(book: Path) -> str:
    try:
        payload = tomllib.loads(read_utf8_text(book, purpose="mdBook configuration"))
    except (DstackError, OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise DstackError(f"invalid mdBook configuration: {book}") from exc
    table = payload.get("book", {})
    if not isinstance(table, dict):
        raise DstackError("mdBook [book] configuration must be a table")
    raw = table.get("src", "src")
    if not isinstance(raw, str) or not raw.strip():
        raise DstackError("mdBook [book].src must be a non-empty relative path")
    return raw.strip()


def configured_source(root: Path) -> tuple[str, Path]:
    root = root.resolve()
    docs = _inside(root / "docs", root, "documentation directory escapes repository")
    book = docs / "book.toml"
    if not book.is_file() or book.is_symlink():
        raise DstackError("docs/book.toml must be a regular file")
    raw = _book_source_value(book)
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise DstackError("mdBook [book].src must stay within docs")
    lexical_source = docs / relative
    current = docs
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DstackError("mdBook [book].src must not traverse symlinks")
    source = lexical_source.resolve()
    try:
        source.relative_to(docs.resolve())
    except ValueError as exc:
        raise DstackError("mdBook [book].src must stay within docs") from exc
    return raw, source


def _summary_link_target(raw: str) -> str | None:
    target = urlsplit(_raw_target(raw))
    if target.scheme or target.netloc or not target.path:
        return None
    normalized = Path(unquote(target.path)).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def ensure_core_navigation(root: Path) -> list[str]:
    """Add missing canonical pages without rewriting project-owned navigation."""

    root = root.resolve()
    summary = root / "docs/src/SUMMARY.md"
    if summary.is_symlink() or not summary.is_file():
        raise DstackError("documentation foundation path is not a regular file: docs/src/SUMMARY.md")

    original = read_utf8_text(summary, purpose="mdBook summary")
    targets = {
        target for raw in _markdown_values(original, LINK_PATTERN) if (target := _summary_link_target(raw)) is not None
    }
    missing = [(label, target) for label, target in CORE_NAVIGATION if target not in targets]
    if not missing:
        return []

    lines = original.rstrip("\n").splitlines()
    for label, target in missing:
        if target == "development/documentation.md":
            continue
        lines.append(f"- [{label}]({target})")

    if "development/documentation.md" not in targets:
        parent = next(
            (
                index
                for index, line in enumerate(lines)
                if "development/index.md" in _markdown_values(line, LINK_PATTERN)
            ),
            None,
        )
        entry = "  - [Documentation](development/documentation.md)"
        if parent is None:
            lines.append(entry.lstrip())
        else:
            indentation = lines[parent][: len(lines[parent]) - len(lines[parent].lstrip())]
            lines.insert(parent + 1, indentation + entry)
    replace_text_if_unchanged(
        summary,
        expected=original,
        content="\n".join(lines) + "\n",
        purpose="mdBook summary",
    )
    return [target for _, target in missing]


def create_foundation(root: Path) -> list[str]:
    root = root.resolve()
    created: list[str] = []
    for relative, content in foundation_files(root.name).items():
        path = root / relative
        _inside(path.parent, root, "documentation foundation path escapes repository")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                handle.write(content)
            created.append(relative)
        except FileExistsError:
            if path.is_symlink() or not path.is_file():
                raise DstackError(f"documentation foundation path is not a regular file: {relative}")
        except (OSError, UnicodeError) as exc:
            raise DstackError(f"cannot create documentation foundation path {relative}: {exc}") from exc
    ensure_core_navigation(root)
    return created


def require_mdbook() -> str:
    executable = shutil.which("mdbook")
    if not executable:
        raise DstackError("mdbook is unavailable on PATH")
    observed = run([executable, "--version"], cwd=Path.cwd()).stdout.strip()
    if observed != SUPPORTED_MDBOOK_VERSION_OUTPUT:
        raise DstackError(
            "dStack requires mdBook 0.5.3 exactly "
            f"({SUPPORTED_MDBOOK_VERSION_OUTPUT}); found {observed or '<empty output>'}"
        )
    return executable


def _raw_target(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _local_target(source: Path, raw: str, source_root: Path) -> Path | None:
    target = urlsplit(_raw_target(raw))
    if target.scheme or target.netloc:
        return None
    path_text = unquote(target.path)
    if not path_text:
        return source
    relative = Path(path_text)
    if relative.is_absolute():
        raise DstackError(f"local documentation target escapes docs/src: {raw}")
    candidate = (source.parent / relative).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as exc:
        raise DstackError(f"local documentation target escapes docs/src: {raw}") from exc
    if not candidate.is_file():
        raise DstackError(f"missing local documentation target: {raw}")
    return candidate


def _links(path: Path) -> list[str]:
    return _markdown_values(read_utf8_text(path, purpose="documentation link source"), LINK_PATTERN)


def validate_decision_records(source: Path) -> list[str]:
    decisions = source / "decisions"
    if not decisions.is_dir():
        return []
    errors: list[str] = []
    allowed = {"Proposed", "Accepted", "Deprecated", "Superseded"}
    for path in sorted(decisions.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = read_utf8_text(path, purpose="decision record")
        fields: dict[str, str] = {}
        for name in ("Status", "Supersedes", "Superseded by"):
            match = re.search(rf"^- \*\*{re.escape(name)}:\*\*\s*(.+)$", text, re.MULTILINE)
            if not match:
                errors.append(f"{path.name} lacks {name}")
                continue
            fields[name] = match.group(1).strip()
        status = fields.get("Status")
        if status and status not in allowed:
            errors.append(f"{path.name} has invalid status {status!r}")
        for name in ("Supersedes", "Superseded by"):
            value = fields.get(name)
            if value and value != "None" and not _markdown_values(value, LINK_PATTERN):
                errors.append(f"{path.name} {name} must be None or a local link")
    return errors


def validate_docs(root: Path, *, mdbook: str | None = None) -> dict[str, object]:
    root = root.resolve()
    docs = _inside(root / "docs", root, "documentation directory escapes repository")
    source = _inside(docs / "src", root, "documentation source escapes repository")
    required = foundation_files(root.name)
    missing: list[str] = []
    invalid: list[str] = []
    for relative in required:
        path = root / relative
        if path.is_symlink() or (path.exists() and not path.is_file()):
            invalid.append(relative)
        elif not path.is_file():
            missing.append(relative)
    foundation_errors = []
    if missing:
        foundation_errors.append("missing required documentation: " + ", ".join(missing))
    if invalid:
        foundation_errors.append("required documentation is not a regular file: " + ", ".join(invalid))
    if foundation_errors:
        raise DstackError("; ".join(foundation_errors))

    raw_source, configured = configured_source(root)
    if configured != source:
        raise DstackError(f"mdBook [book].src must resolve to docs/src; configured source is {raw_source!r}")

    errors: list[str] = validate_decision_records(source)
    summary = source / "SUMMARY.md"
    chapters: set[Path] = set()
    for raw in _links(summary):
        try:
            target = _local_target(summary, raw, source)
        except DstackError as exc:
            errors.append(str(exc))
            continue
        if target is not None and target.suffix.casefold() == ".md":
            chapters.add(target)

    markdown = set(source.rglob("*.md"))
    for path in markdown:
        for raw in _links(path):
            try:
                _local_target(path, raw, source)
            except DstackError as exc:
                errors.append(str(exc))

    includes: set[Path] = set()
    pending = list(chapters)
    while pending:
        path = pending.pop()
        for raw in _markdown_values(read_utf8_text(path, purpose="documentation include source"), INCLUDE_PATTERN):
            try:
                included = _local_target(path, raw.split(":", 1)[0], source)
            except DstackError as exc:
                errors.append(str(exc))
                continue
            if included is not None and included not in includes:
                includes.add(included)
                if included.suffix.casefold() == ".md":
                    pending.append(included)

    orphans = sorted(path.relative_to(source).as_posix() for path in markdown - chapters - includes - {summary})
    if orphans:
        errors.append("orphan documentation is not in SUMMARY.md: " + ", ".join(orphans))
    if errors:
        raise DstackError("documentation validation failed: " + "; ".join(sorted(set(errors))))

    executable = mdbook or require_mdbook()
    with tempfile.TemporaryDirectory(prefix="dstack-mdbook-") as output:
        run(
            [executable, "build", str(docs), "--dest-dir", output],
            cwd=root,
        )

    return {
        "status": "ok",
        "chapters": sorted(path.relative_to(source).as_posix() for path in chapters),
        "includes": sorted(path.relative_to(source).as_posix() for path in includes),
    }


def initialize_docs(root: Path) -> dict[str, object]:
    executable = require_mdbook()
    created = create_foundation(root)
    return {
        "created_documentation": created,
        "documentation": validate_docs(root, mdbook=executable),
    }


def cmd_docs_validate(args: object) -> int:
    emit(validate_docs(Path(getattr(args, "root"))))
    return 0
