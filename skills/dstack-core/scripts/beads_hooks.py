"""Install and verify the Beads Git hook shims."""

# ruff: noqa: S603

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


INSTALL_COMMAND = ("bd", "hooks", "install")
LIST_COMMAND = ("bd", "hooks", "list", "--json")
RECOVERY_COMMANDS = ["bd hooks install", "bd hooks list --json"]
MAX_ERROR_CHARS = 2_000


def _stage(status: str, error: str | None = None) -> dict[str, Any]:
    return {"status": status, "error": error}


def _verification(status: str = "skipped", error: str | None = None) -> dict[str, Any]:
    return {"status": status, "error": error, "hook_count": 0, "hooks": []}


def skipped_beads_hooks(reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
        "install": _stage("skipped"),
        "verification": _verification(),
        "recovery": [],
    }


def unavailable_beads_hooks(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "install": _stage("unavailable", reason),
        "verification": _verification(),
        "recovery": list(RECOVERY_COMMANDS),
    }


def _failure(reason: str, *, install: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "failed",
        "reason": reason,
        "install": install,
        "verification": verification,
        "recovery": list(RECOVERY_COMMANDS),
    }


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout or f"command exited {result.returncode}").strip()
    return text[-MAX_ERROR_CHARS:]


def _run(command: Sequence[str], project_root: Path, *, quiet: bool) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))
    if not quiet:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
    return result


def _verified_hooks(payload: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("hooks"), list) or not payload["hooks"]:
        return None, "bd hooks list --json returned no hook records"

    hooks: list[dict[str, Any]] = []
    for hook in payload["hooks"]:
        if not isinstance(hook, dict):
            return None, "bd hooks list --json returned a malformed hook record"
        name = hook.get("Name", hook.get("name"))
        installed = hook.get("Installed", hook.get("installed"))
        outdated = hook.get("Outdated", hook.get("outdated"))
        if not isinstance(name, str) or not name or installed is not True or outdated is not False:
            return None, "bd hooks list --json reported a missing or outdated hook"
        hooks.append(hook)
    return hooks, None


def install_and_verify_beads_hooks(
    project_root: Path,
    *,
    available: bool,
    quiet: bool,
) -> dict[str, Any]:
    """Install Beads hooks and require every reported hook to be current."""
    if not available:
        return unavailable_beads_hooks("bd is unavailable or its launcher cannot execute")

    install = _run(INSTALL_COMMAND, project_root, quiet=quiet)
    if install.returncode:
        error = _command_error(install)
        return _failure(
            "bd hooks install failed",
            install=_stage("failed", error),
            verification=_verification(),
        )

    listed = _run(LIST_COMMAND, project_root, quiet=quiet)
    if listed.returncode:
        error = _command_error(listed)
        return _failure(
            "bd hooks list failed",
            install=_stage("succeeded"),
            verification=_verification("failed", error),
        )
    try:
        payload = json.loads(listed.stdout)
    except json.JSONDecodeError:
        return _failure(
            "bd hooks list returned invalid JSON",
            install=_stage("succeeded"),
            verification=_verification("failed", "bd hooks list --json returned invalid JSON"),
        )

    hooks, error = _verified_hooks(payload)
    if error is not None or hooks is None:
        return _failure(
            "Beads hook verification failed",
            install=_stage("succeeded"),
            verification=_verification("failed", error),
        )
    return {
        "status": "succeeded",
        "reason": "all reported Beads hooks are installed and current",
        "install": _stage("succeeded"),
        "verification": {
            "status": "succeeded",
            "error": None,
            "hook_count": len(hooks),
            "hooks": hooks,
        },
        "recovery": [],
    }
