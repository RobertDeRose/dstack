#!/usr/bin/env python3
"""Set dstack skill frontmatter versions for a release."""

from __future__ import annotations

import re
import sys
from pathlib import Path


VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
VERSION_LINE = re.compile(r'^  version: "[^"]+"$', re.MULTILINE)


def main() -> int:
    if len(sys.argv) != 2 or not VERSION.fullmatch(sys.argv[1]):
        message = "usage: set-skill-version.py <semantic-version>"
        raise SystemExit(message)

    paths = sorted(Path("skills").glob("*/SKILL.md"))
    if not paths:
        message = "no skills/*/SKILL.md files found"
        raise SystemExit(message)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        frontmatter_end = text.find("\n---", 4)
        if not text.startswith("---\n") or frontmatter_end < 0:
            message = f"invalid skill frontmatter: {path}"
            raise SystemExit(message)
        frontmatter = text[:frontmatter_end]
        updated, count = VERSION_LINE.subn(f'  version: "{sys.argv[1]}"', frontmatter)
        if count != 1:
            message = f"expected one metadata version in {path}, found {count}"
            raise SystemExit(message)
        path.write_text(updated + text[frontmatter_end:], encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
