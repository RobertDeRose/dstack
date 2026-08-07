#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "copier>=9.16,<10",
#     "packaging>=24,<27",
#     "PyYAML>=6.0,<7",
# ]
# ///
# ruff: noqa: EM101, EM102
"""Run a dstack workflow script from one stable uv script environment."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run-workflow.py <workflow-script> [args ...]")
    target = Path(sys.argv[1]).expanduser().resolve()
    if not target.is_file():
        raise SystemExit(f"Workflow script does not exist: {target}")
    sys.path.insert(0, str(target.parent))
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
