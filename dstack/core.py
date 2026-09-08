#!/usr/bin/env python3
"""Low-level process and filesystem primitives shared by dStack."""

from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


class DstackError(RuntimeError):
    """Raised when a deterministic dStack operation cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


DEFAULT_COMMAND_TIMEOUT_SECONDS = 120.0


def command_timeout(command: Sequence[str]) -> float:
    override = os.environ.get("DSTACK_COMMAND_TIMEOUT_SECONDS", "").strip()
    if override:
        try:
            value = float(override)
        except ValueError as exc:
            raise DstackError("DSTACK_COMMAND_TIMEOUT_SECONDS must be numeric") from exc
        if not math.isfinite(value) or value <= 0:
            raise DstackError("DSTACK_COMMAND_TIMEOUT_SECONDS must be positive and finite")
        return value
    return DEFAULT_COMMAND_TIMEOUT_SECONDS


def command_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    if extra:
        env.update(extra)
    return env


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    input_text: str | None = None,
    timeout: float | None = None,
) -> CommandResult:
    if not command:
        raise DstackError("cannot run an empty command")
    effective_timeout = command_timeout(command) if timeout is None else timeout
    if not math.isfinite(effective_timeout) or effective_timeout <= 0:
        raise DstackError("command timeout must be positive and finite")
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            input=input_text.encode("utf-8") if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=command_env(env),
            timeout=effective_timeout,
        )
    except FileNotFoundError as exc:
        raise DstackError(f"required executable not found on PATH: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DstackError(
            f"command timed out after {effective_timeout:g}s ({' '.join(command)}) in {cwd}; "
            "inspect native command state before retrying because the operation may have partially completed"
        ) from exc

    # Do not let universal-newline decoding alter Git pathnames containing CR/LF.
    result = CommandResult(
        completed.returncode,
        completed.stdout.decode("utf-8", errors="surrogateescape"),
        completed.stderr.decode("utf-8", errors="surrogateescape"),
    )
    if check and completed.returncode != 0:
        detail = truncate_output(result.stderr) or truncate_output(result.stdout) or f"exit {completed.returncode}"
        raise DstackError(f"command failed ({' '.join(command)}): {detail}")
    return result


def _assert_no_symlink_components(path: Path, *, purpose: str) -> None:
    current = Path(path)
    while True:
        if current.is_symlink():
            raise DstackError(f"{purpose} must not be a symlink: {path}")
        if current.parent == current:
            return
        current = current.parent


def read_utf8_text(path: Path, *, purpose: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise DstackError(f"cannot read {purpose}: {path}") from exc


def truncate_output(value: str, *, limit: int = 4000) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    marker = "\n... output truncated ...\n"
    if limit <= len(marker):
        return marker[:limit]
    remaining = limit - len(marker)
    head = remaining // 2
    tail = remaining - head
    suffix = text[-tail:] if tail else ""
    return text[:head] + marker + suffix
