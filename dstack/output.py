"""Neutral JSON output helpers for public controller commands."""

from __future__ import annotations

import json
import sys
from typing import Any


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def fail(message: str) -> int:
    json.dump({"status": "error", "error": message}, sys.stderr)
    sys.stderr.write("\n")
    return 1
