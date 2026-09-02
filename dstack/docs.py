"""Canonical mdBook foundation and stateless documentation validation."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .core import DstackError, _assert_no_symlink_components, read_utf8_text, run
from .output import emit

SUPPORTED_MDBOOK_VERSION_OUTPUT = "mdbook v0.5.3"
LINK_PATTERN = re.compile(r"!?\[[^]]*\]\((.+)\)")
INCLUDE_PATTERN = re.compile(r"\{\{#include\s+([^}\s]+)[^}]*\}\}")
FENCE_PATTERN = re.compile(r"^( {0,3})(`{3,}|~{3,})")
ADR_PATTERN = "[0-9][0-9][0-9][0-9]-*.md"
ADR_STATUSES = frozenset({"Proposed", "Accepted", "Deprecated", "Superseded"})


def _is_escaped(text: str, index: int) -> bool:
    count = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        count += 1
        index -= 1
    return count % 2 == 1


def _mask_markdown_code(text: str) -> str:
    """Mask fenced and inline code while preserving offsets and line breaks."""

    masked = list(text)
    offset = 0
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
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
        width = 1
        while index + width < len(masked_text) and masked_text[index + width] == "`":
            width += 1
        cursor = index + width
        while cursor < len(masked_text):
            cursor = masked_text.find("`", cursor)
            if cursor < 0:
                break
            closing = 1
            while cursor + closing < len(masked_text) and masked_text[cursor + closing] == "`":
                closing += 1
            if closing == width:
                for position in range(index, cursor + width):
                    if masked[position] not in "\r\n":
                        masked[position] = " "
                index = cursor + width
                break
            cursor += closing
        else:
            index += width
            continue
        if cursor < 0:
            index += width
    return "".join(masked)


def _link_target_spans(text: str) -> list[tuple[int, int]]:
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
            if _is_escaped(masked, cursor):
                cursor += 1
                continue
            if masked[cursor] == "(":
                depth += 1
            elif masked[cursor] == ")":
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
    if pattern is LINK_PATTERN:
        return [text[start:end] for start, end in _link_target_spans(text)]
    masked = _mask_markdown_code(text)
    return [match.group(1) for match in pattern.finditer(masked) if not _is_escaped(masked, match.start())]


def _raw_target(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _inside(path: Path, parent: Path, message: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise DstackError(message) from exc
    return resolved


def foundation_files(project: str) -> dict[str, str]:
    title = project.replace("-", " ").replace("_", " ").strip().title() or "Project"
    return {
        "docs/book.toml": f'[book]\ntitle = {json.dumps(title)}\nlanguage = "en"\nsrc = "src"\n',
        "docs/src/SUMMARY.md": (
            "# Summary\n\n"
            "- [Project](index.md)\n"
            "- [Getting started](getting-started/index.md)\n"
            "- [Operations](operations/index.md)\n"
            "- [Architecture](architecture/index.md)\n"
            "- [Development](development/index.md)\n"
            "- [Reference](reference/index.md)\n"
            "- [Architecture decisions](decisions/index.md)\n"
        ),
        "docs/src/index.md": f"# {title}\n\nDescribe the project and its supported users here.\n",
        "docs/src/getting-started/index.md": (
            "# Getting started\n\nDescribe installation and the shortest successful user path here.\n"
        ),
        "docs/src/operations/index.md": (
            "# Operations\n\nDescribe configuration, deployment, operation, failure handling, and recovery here.\n"
        ),
        "docs/src/architecture/index.md": (
            "# Architecture\n\nDescribe current components, boundaries, data flow, and durable invariants here.\n"
        ),
        "docs/src/development/index.md": (
            "# Development\n\nDescribe how to build, test, change, validate, and release the project here.\n"
        ),
        "docs/src/reference/index.md": "# Reference\n\nProvide exact interfaces and configuration reference here.\n",
        "docs/src/decisions/index.md": (
            "# Architecture decisions\n\nRecord durable rationale as ADRs or linked decision Beads.\n"
        ),
    }


def create_foundation(root: Path) -> list[str]:
    _assert_no_symlink_components(root, purpose="documentation root")
    repository = root.resolve()
    created: list[str] = []
    for relative, content in foundation_files(repository.name).items():
        path = repository / relative
        _assert_no_symlink_components(path, purpose="documentation foundation path")
        _inside(path.parent, repository, "documentation foundation path escapes repository")
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
    return created


def configured_source(root: Path) -> tuple[str, Path]:
    repository = root.resolve()
    docs = _inside(repository / "docs", repository, "documentation directory escapes repository")
    book = docs / "book.toml"
    if book.is_symlink() or not book.is_file():
        raise DstackError("docs/book.toml must be a regular file")
    try:
        payload = tomllib.loads(read_utf8_text(book, purpose="mdBook configuration"))
    except tomllib.TOMLDecodeError as exc:
        raise DstackError(f"invalid mdBook configuration: {book}") from exc
    table = payload.get("book", {})
    if not isinstance(table, dict):
        raise DstackError("mdBook [book] configuration must be a table")
    raw = table.get("src", "src")
    if not isinstance(raw, str) or not raw.strip():
        raise DstackError("mdBook [book].src must be a non-empty relative path")
    relative = Path(raw.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise DstackError("mdBook [book].src must stay within docs")
    current = docs
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DstackError("mdBook [book].src must not traverse symlinks")
    source = current.resolve()
    try:
        source.relative_to(docs.resolve())
    except ValueError as exc:
        raise DstackError("mdBook [book].src must stay within docs") from exc
    return raw.strip(), source


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
    return markdown_values(read_utf8_text(path, purpose="documentation link source"), LINK_PATTERN)


def validate_decision_records(source: Path) -> list[str]:
    decisions = source / "decisions"
    if not decisions.is_dir():
        return []
    records = {path.name: path for path in decisions.glob(ADR_PATTERN)}
    errors: list[str] = []
    for path in sorted(records.values()):
        text = read_utf8_text(path, purpose="decision record")
        fields: dict[str, str] = {}
        for name in ("Status", "Supersedes", "Superseded by"):
            match = re.search(rf"^- \*\*{re.escape(name)}:\*\*\s*(.+)$", text, re.MULTILINE)
            if match is None:
                errors.append(f"{path.name} lacks {name}")
            else:
                fields[name] = match.group(1).strip()
        if (status := fields.get("Status")) and status not in ADR_STATUSES:
            errors.append(f"{path.name} has invalid status {status!r}")
        for name in ("Supersedes", "Superseded by"):
            value = fields.get(name)
            if not value or value == "None":
                continue
            links = markdown_values(value, LINK_PATTERN)
            if not links:
                errors.append(f"{path.name} {name} must be None or local ADR links")
                continue
            for raw in links:
                target = urlsplit(_raw_target(raw))
                target_name = Path(unquote(target.path)).name
                if target.scheme or target.netloc or target_name not in records:
                    errors.append(f"{path.name} {name} references an unknown ADR: {raw}")
    return errors


def require_mdbook() -> str:
    executable = shutil.which("mdbook")
    if executable is None:
        raise DstackError("mdbook is unavailable on PATH")
    observed = run([executable, "--version"], cwd=Path.cwd()).stdout.strip()
    if observed != SUPPORTED_MDBOOK_VERSION_OUTPUT:
        raise DstackError(
            f"dStack requires {SUPPORTED_MDBOOK_VERSION_OUTPUT}; found {observed or '<empty output>'}"
        )
    return executable


def validate_docs(root: Path, *, mdbook: str | None = None) -> dict[str, object]:
    _assert_no_symlink_components(root, purpose="documentation root")
    repository = root.resolve()
    docs = _inside(repository / "docs", repository, "documentation directory escapes repository")
    expected_source = _inside(docs / "src", repository, "documentation source escapes repository")

    missing = [relative for relative in foundation_files(repository.name) if not (repository / relative).is_file()]
    if missing:
        raise DstackError("missing required documentation: " + ", ".join(missing))

    raw_source, source = configured_source(repository)
    if source != expected_source:
        raise DstackError(f"mdBook [book].src must resolve to docs/src; configured source is {raw_source!r}")

    errors = validate_decision_records(source)
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
        text = read_utf8_text(path, purpose="documentation include source")
        for raw in markdown_values(text, INCLUDE_PATTERN):
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
        run([executable, "build", str(docs), "--dest-dir", output], cwd=repository)

    return {
        "status": "ok",
        "chapters": sorted(path.relative_to(source).as_posix() for path in chapters),
        "includes": sorted(path.relative_to(source).as_posix() for path in includes),
    }


def cmd_docs_validate(args: object) -> int:
    emit(validate_docs(Path(getattr(args, "root"))))
    return 0
