from __future__ import annotations

import json
import sys
from typing import Any


def emit(payload: Any) -> None:
    """Emit compact deterministic JSON for agent-facing commands."""

    print(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def fail(message: str) -> int:
    print(json.dumps({"status": "error", "error": message}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
    return 2
