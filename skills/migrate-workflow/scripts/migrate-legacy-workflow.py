#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Stable executable entrypoint for the legacy workflow migration CLI."""

import sys
from pathlib import Path


SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from migration_cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
