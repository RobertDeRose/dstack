from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO


_OUTPUT_FORMAT = "DSTACK_OUTPUT_FORMAT"


def _pretty() -> bool:
    return os.environ.get(_OUTPUT_FORMAT, "compact").strip().casefold() == "pretty"


def _dump(payload: Any) -> str:
    if _pretty():
        return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write(payload: Any, stream: TextIO) -> None:
    print(_dump(payload), file=stream)


def emit(payload: Any) -> None:
    """Emit deterministic JSON; pretty-print only when explicitly requested."""

    _write(payload, sys.stdout)


def fail(message: str) -> int:
    _write({"status": "error", "error": message}, sys.stderr)
    return 2
