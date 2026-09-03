from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO


_OUTPUT_FORMAT = "DSTACK_OUTPUT_FORMAT"


def _pretty(stream: TextIO) -> bool:
    override = os.environ.get(_OUTPUT_FORMAT, "auto").strip().casefold()
    if override == "pretty":
        return True
    if override == "compact":
        return False
    return bool(stream.isatty())


def _dump(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write(payload: Any, stream: TextIO) -> None:
    if _pretty(stream):
        from rich.console import Console

        terminal = bool(stream.isatty())
        Console(
            file=stream,
            force_terminal=terminal,
            color_system="standard" if terminal else None,
        ).print_json(data=payload, sort_keys=True, ensure_ascii=False)
    else:
        print(_dump(payload), file=stream)


def emit(payload: Any) -> None:
    """Emit deterministic JSON, formatted for a terminal or machine consumer."""

    _write(payload, sys.stdout)


def fail(message: str) -> int:
    _write({"status": "error", "error": message}, sys.stderr)
    return 2
