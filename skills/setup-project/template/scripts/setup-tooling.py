#!/usr/bin/env python3
# ruff: noqa: S603
"""Resolve and install the generated project's mise tooling without rolling back its scaffold."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any


PLATFORMS = ("linux-x64", "linux-arm64", "macos-x64", "macos-arm64")
LOCK_COMMAND = ["mise", "lock", "--yes", "--platform", ",".join(PLATFORMS)]
INSTALL_COMMAND = ["mise", "install", "--locked"]
HOOK_COMMAND = ["mise", "x", "--", "hk", "install", "--mise"]
RERUN_COMMAND = "python3 scripts/setup-tooling.py --json"
ISOLATED_MISE = "MISE_GLOBAL_CONFIG_FILE=/dev/null "
MAX_ERROR_CHARS = 2_000


def stage(status: str, *, error: str | None = None, path: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status}
    if path is not None:
        result["path"] = path
    result["error"] = error
    return result


def skipped_result() -> dict[str, Any]:
    return {
        "status": "skipped",
        "mise": "skipped",
        "lock": stage("skipped", path="mise.lock"),
        "install": stage("skipped"),
        "hooks": stage("skipped"),
        "platforms": list(PLATFORMS),
        "recovery": [RERUN_COMMAND],
    }


def command_error(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout or f"command exited {result.returncode}").strip()
    return text[-MAX_ERROR_CHARS:]


def run(command: Sequence[str], project_root: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=project_root,
            env=os.environ | {"MISE_GLOBAL_CONFIG_FILE": os.devnull},
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))


def provision(project_root: Path) -> dict[str, Any]:
    result = skipped_result()
    result["status"] = "degraded"
    result["mise"] = "available" if shutil.which("mise") else "unavailable"
    if result["mise"] == "unavailable":
        result["recovery"] = [RERUN_COMMAND]
        return result

    lock = run(LOCK_COMMAND, project_root)
    lock_path = project_root / "mise.lock"
    if lock.returncode or not lock_path.is_file() or lock_path.stat().st_size == 0:
        error = command_error(lock) if lock.returncode else "mise lock did not create a nonempty mise.lock"
        result["lock"] = stage("failed", path="mise.lock", error=error)
        result["recovery"] = [ISOLATED_MISE + " ".join(LOCK_COMMAND), RERUN_COMMAND]
        return result
    result["lock"] = stage("succeeded", path="mise.lock")

    install = run(INSTALL_COMMAND, project_root)
    if install.returncode:
        result["install"] = stage("failed", error=command_error(install))
        result["recovery"] = [ISOLATED_MISE + " ".join(INSTALL_COMMAND), RERUN_COMMAND]
        return result
    result["install"] = stage("succeeded")

    if not (project_root / ".git").exists():
        result["hooks"] = stage("skipped-no-git")
        result["recovery"] = [ISOLATED_MISE + " ".join(HOOK_COMMAND)]
        return result

    hooks = run(HOOK_COMMAND, project_root)
    if hooks.returncode:
        result["hooks"] = stage("failed", error=command_error(hooks))
        result["recovery"] = [ISOLATED_MISE + " ".join(HOOK_COMMAND)]
        return result

    result["hooks"] = stage("succeeded")
    result["status"] = "succeeded"
    result["recovery"] = []
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip", action="store_true", help="Report an explicitly skipped provisioning run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = skipped_result() if args.skip else provision(Path(__file__).resolve().parents[1])
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Tooling provisioning: {result['status']}")
        for recovery in result["recovery"]:
            print(f"Recovery: {recovery}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
