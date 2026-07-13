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
# ruff: noqa: S603, S607
"""Update a Copier-managed dstack project and validate the resulting scaffold."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from copier import run_update
from packaging.version import InvalidVersion, Version


DEFAULT_TEMPLATE_SOURCE = "gh:RobertDeRose/dstack"
CONFLICT_START = re.compile(r"^<<<<<<<(?: .*)?$", re.MULTILINE)
CONFLICT_MIDDLE = re.compile(r"^=======$", re.MULTILINE)
CONFLICT_END = re.compile(r"^>>>>>>>(?: .*)?$", re.MULTILINE)
IGNORED_SCAN_DIRS = {
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
LEGACY_TASK_IGNORED_DIRS = IGNORED_SCAN_DIRS | {
    ".agents",
    ".beads",
    ".codex",
    ".cursor",
    ".github",
    "_template",
    "archive",
    "archived",
    "migration",
    "skills",
    "third_party",
    "vendor",
    "vendors",
}


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command and preserve useful output when it fails."""
    if not quiet:
        print("+", " ".join(command))
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=quiet,
        text=True,
    )
    if completed.returncode != 0:
        if quiet:
            if completed.stdout:
                print(completed.stdout, file=sys.stderr, end="")
            if completed.stderr:
                print(completed.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(
            completed.returncode,
            list(command),
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def run_capture(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output and fail with its diagnostics."""
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip())
        message = f"Command failed ({completed.returncode}): {' '.join(command)}"
        if details:
            message += f"\n{details}"
        raise SystemExit(message)
    return completed


def git_root(path: Path) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        msg = "Copier updates require a Git repository"
        raise SystemExit(msg)
    return Path(completed.stdout.strip()).resolve()


def git_status(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def legacy_task_files(root: Path) -> list[str]:
    """Return active legacy task files without treating tools, templates, or archives as live state."""
    found: list[str] = []
    for current, directories, filenames in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if directory not in LEGACY_TASK_IGNORED_DIRS and not directory.startswith(".")
        ]
        if not any(filename.casefold() == "tasks.md" for filename in filenames):
            continue
        current_path = Path(current)
        for filename in filenames:
            if filename.casefold() == "tasks.md":
                found.append((current_path / filename).relative_to(root).as_posix())
    return sorted(found)


def beads_state_present(root: Path) -> bool:
    """Detect initialized Beads state without counting a copied formula as a database."""
    beads = root / ".beads"
    markers = (
        beads / "metadata.json",
        beads / "config.yaml",
        beads / "beads.db",
        beads / "issues.jsonl",
        beads / "embeddeddolt",
        beads / "dolt",
    )
    return any(path.exists() for path in markers)


def project_preflight(root: Path, answers_file: str) -> dict[str, Any]:
    tasks = legacy_task_files(root)
    beads_present = beads_state_present(root)
    answers = root / answers_file
    if tasks and not beads_present:
        route = "migrate-workflow"
        reason = "legacy feature tasks exist but Beads has not been initialized"
    elif answers.is_file():
        route = "update-project"
        reason = "Copier state exists"
    else:
        route = "migrate-workflow"
        reason = "Copier state is missing from an existing repository"
    return {
        "destination": str(root),
        "answers_file": str(answers),
        "answers_exists": answers.is_file(),
        "legacy_task_files": tasks,
        "beads_state_present": beads_present,
        "recommended_workflow": route,
        "reason": reason,
    }


def nul_paths(command: Sequence[str], *, root: Path) -> set[str]:
    completed = subprocess.run(
        list(command),
        cwd=root,
        check=True,
        capture_output=True,
    )
    return {value.decode("utf-8", errors="surrogateescape") for value in completed.stdout.split(b"\0") if value}


def changed_project_paths(root: Path) -> set[str]:
    """Return Git-visible modified and untracked paths, excluding ignored files."""
    tracked = nul_paths(
        ["git", "diff", "--name-only", "-z", "HEAD", "--"],
        root=root,
    )
    untracked = nul_paths(
        ["git", "ls-files", "-z", "--others", "--exclude-standard"],
        root=root,
    )
    return {
        relative
        for relative in tracked | untracked
        if not any(part in IGNORED_SCAN_DIRS for part in Path(relative).parts)
    }


def unmerged_paths(root: Path) -> set[str]:
    return nul_paths(
        ["git", "diff", "--name-only", "-z", "--diff-filter=U", "--"],
        root=root,
    )


def reject_files(root: Path) -> set[str]:
    """Find reject files while pruning dependency and generated-cache trees."""
    found: set[str] = set()
    for current, directories, filenames in os.walk(root):
        directories[:] = [directory for directory in directories if directory not in IGNORED_SCAN_DIRS]
        current_path = Path(current)
        for filename in filenames:
            if filename.endswith(".rej"):
                found.add((current_path / filename).relative_to(root).as_posix())
    return found


def contains_inline_conflict(text: str) -> bool:
    """Require a coherent start/middle/end marker set to avoid separator false positives."""
    return bool(CONFLICT_START.search(text) and CONFLICT_MIDDLE.search(text) and CONFLICT_END.search(text))


def scan_conflicts(
    root: Path,
    *,
    baseline_rejects: set[str] | None = None,
) -> list[str]:
    """Inspect only Git-visible update output plus newly created reject files."""
    conflicts = set(unmerged_paths(root))
    candidates = changed_project_paths(root)

    for relative in sorted(candidates):
        path = root / relative
        if not path.is_file():
            continue
        if path.suffix == ".rej":
            conflicts.add(relative)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if contains_inline_conflict(text):
            conflicts.add(relative)

    prior = baseline_rejects or set()
    conflicts.update(reject_files(root) - prior)
    return sorted(conflicts)


def tagged_version(tag: str) -> Version | None:
    if not tag.startswith("v"):
        return None
    try:
        version = Version(tag.removeprefix("v"))
    except InvalidVersion:
        return None
    if len(version.release) != 3:
        return None
    return version


def default_vcs_ref(source: str, *, include_prereleases: bool = False) -> str:
    """Resolve the newest published PEP 440 release tag from the recorded Git source."""
    completed = subprocess.run(
        ["git", "ls-remote", "--tags", git_source(source), "refs/tags/v*"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        msg = f"Unable to discover dstack release tags from {source!r}; pass --vcs-ref explicitly."
        raise SystemExit(msg)

    tags = {
        line.split()[1].removeprefix("refs/tags/").removesuffix("^{}")
        for line in completed.stdout.splitlines()
        if len(line.split()) == 2
    }
    releases: list[tuple[Version, str]] = []
    for tag in tags:
        version = tagged_version(tag)
        if version is None:
            continue
        if not include_prereleases and (version.is_prerelease or version.is_devrelease):
            continue
        releases.append((version, tag))
    if not releases:
        qualifier = " including prereleases" if include_prereleases else " stable"
        msg = f"No{qualifier} dstack release tags found in {source!r}; pass --vcs-ref explicitly."
        raise SystemExit(msg)
    return max(releases)[1]


def load_answers(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        msg = f"Unable to read Copier answers from {path}: {exc}"
        raise SystemExit(msg) from exc
    if not isinstance(loaded, dict):
        msg = f"Copier answers must be a mapping: {path}"
        raise SystemExit(msg)
    return loaded


def validate_template_source(source: str) -> None:
    if any(character in source for character in ("\n", "\r", "\x00")):
        msg = "Template source contains prohibited control characters"
        raise SystemExit(msg)
    if source == DEFAULT_TEMPLATE_SOURCE:
        return
    if Path(source).expanduser().exists():
        return
    if source.startswith(("gh:", "gl:", "https://", "ssh://", "git@")):
        return
    msg = (
        "Unsupported template source. Use the packaged gh: source, an existing local path, "
        "or an explicit gh:, gl:, https://, ssh://, or git@ source."
    )
    raise SystemExit(msg)


def git_source(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source.removeprefix('gh:')}.git"
    if source.startswith("gl:"):
        return f"https://gitlab.com/{source.removeprefix('gl:')}.git"
    return source


def require_release_tag(source: str, vcs_ref: str) -> str | None:
    """Refuse an implicit HEAD fallback and return the resolved tag commit."""
    if tagged_version(vcs_ref) is None:
        return None
    completed = subprocess.run(
        [
            "git",
            "ls-remote",
            "--exit-code",
            "--tags",
            git_source(source),
            f"refs/tags/{vcs_ref}",
            f"refs/tags/{vcs_ref}^{{}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        message = (
            f"dstack release tag {vcs_ref!r} is not available from {source!r}. "
            "The updater will not fall back to HEAD. Publish the matching tag or pass "
            "an explicit --vcs-ref after reviewing the source revision."
        )
        if detail:
            message += f"\nGit reported: {detail}"
        raise SystemExit(message)
    refs: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2:
            refs[fields[1]] = fields[0]
    return refs.get(f"refs/tags/{vcs_ref}^{{}}") or refs.get(f"refs/tags/{vcs_ref}")


def parse_json_output(command: Sequence[str], *, cwd: Path) -> Any:
    completed = run_capture(command, cwd=cwd)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        msg = f"Expected JSON from {' '.join(command)}; output was not valid JSON"
        raise SystemExit(msg) from exc


def bd_available(root: Path) -> bool:
    if shutil.which("bd") is None:
        return False
    completed = subprocess.run(["bd", "--version"], cwd=root, check=False, capture_output=True, text=True)
    return completed.returncode == 0


def check_beads(root: Path) -> dict[str, Any]:
    """Run storage-mode-neutral Beads smoke checks."""
    info = parse_json_output(["bd", "info", "--json"], cwd=root)
    ready = parse_json_output(["bd", "ready", "--json", "--limit", "1"], cwd=root)

    formula_checked = False
    formula = root / ".beads/formulas/feature-lifecycle.formula.toml"
    if formula.is_file():
        parse_json_output(
            ["bd", "formula", "show", "feature-lifecycle", "--json"],
            cwd=root,
        )
        formula_checked = True

    database_path = info.get("database_path") if isinstance(info, dict) else None
    issue_count = info.get("issue_count") if isinstance(info, dict) else None
    return {
        "commands": [
            "bd info --json",
            "bd ready --json --limit 1",
            *(["bd formula show feature-lifecycle --json"] if formula_checked else []),
        ],
        "database_path": database_path,
        "issue_count": issue_count,
        "ready_sample_count": len(ready) if isinstance(ready, list) else None,
        "formula_checked": formula_checked,
    }


TOOLING_RERUN = "python3 scripts/setup-tooling.py --json"
TOOLING_PLATFORMS = ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"]


def skipped_tooling(*, recovery: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": "skipped",
        "mise": "skipped",
        "lock": {"status": "skipped", "path": "mise.lock", "error": None},
        "install": {"status": "skipped", "error": None},
        "hooks": {"status": "skipped", "error": None},
        "platforms": TOOLING_PLATFORMS,
        "recovery": recovery or [],
    }


def failed_tooling(error: str) -> dict[str, Any]:
    return {
        "status": "degraded",
        "mise": "skipped",
        "lock": {"status": "failed", "path": "mise.lock", "error": error},
        "install": {"status": "skipped", "error": None},
        "hooks": {"status": "skipped", "error": None},
        "platforms": TOOLING_PLATFORMS,
        "recovery": [TOOLING_RERUN],
    }


def tooling_result_error(result: dict[str, Any], destination: Path) -> str | None:
    if result.get("status") not in {"succeeded", "degraded", "skipped"}:
        return "tooling result has an invalid overall status"
    if result.get("mise") not in {"available", "unavailable", "skipped"}:
        return "tooling result has an invalid mise status"
    if result.get("platforms") != TOOLING_PLATFORMS:
        return "tooling result has an invalid platform contract"
    recovery = result.get("recovery")
    if not isinstance(recovery, list) or not all(isinstance(command, str) and command for command in recovery):
        return "tooling result has invalid recovery commands"

    allowed = {
        "lock": {"succeeded", "failed", "skipped"},
        "install": {"succeeded", "failed", "skipped"},
        "hooks": {"succeeded", "failed", "skipped", "skipped-no-git"},
    }
    for name, statuses in allowed.items():
        stage = result.get(name)
        if not isinstance(stage, dict) or stage.get("status") not in statuses:
            return f"tooling result has an invalid {name} stage"
        if "error" not in stage:
            return f"tooling result is missing the {name} error field"
        error = stage["error"]
        if error is not None and not isinstance(error, str):
            return f"tooling result has an invalid {name} error"
        if stage["status"] == "failed" and not error:
            return f"tooling result is missing the {name} failure error"
        if stage["status"] != "failed" and error is not None:
            return f"tooling result has an unexpected {name} error"
    if result["lock"].get("path") != "mise.lock":
        return "tooling result has an invalid lock path"

    lock = destination / "mise.lock"
    if result["lock"]["status"] == "succeeded" and (not lock.is_file() or lock.stat().st_size == 0):
        return "tooling reported a successful lock without a nonempty mise.lock"
    if result["status"] == "succeeded":
        if result["mise"] != "available" or any(result[name]["status"] != "succeeded" for name in allowed):
            return "tooling result has inconsistent successful stages"
        if recovery:
            return "successful tooling result unexpectedly contains recovery commands"
    return None


def provision_tooling(destination: Path) -> dict[str, Any]:
    script = destination / "scripts/setup-tooling.py"
    if not script.is_file():
        return failed_tooling("scripts/setup-tooling.py is not present after the template update")

    try:
        completed = subprocess.run(
            [sys.executable, str(script), "--json"],
            cwd=destination,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        completed = subprocess.CompletedProcess([sys.executable, str(script), "--json"], 127, "", str(exc))
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = None
    if completed.returncode == 0 and isinstance(result, dict):
        error = tooling_result_error(result, destination)
        if error is None:
            return result
    else:
        error = (completed.stderr or completed.stdout or "tooling provisioner returned invalid output").strip()[-2_000:]
    return failed_tooling(error)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", "-d", type=Path, default=Path.cwd())
    parser.add_argument("--answers-file", default=".copier-answers.yml")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Inspect Copier, legacy task, and Beads state without querying tags or modifying files.",
    )
    parser.add_argument(
        "--vcs-ref",
        help=(
            "Specific template tag, commit, branch, or HEAD. Defaults to the newest "
            "published stable tag from the Git source recorded by Copier."
        ),
    )
    parser.add_argument("--prereleases", action="store_true")
    parser.add_argument("--conflict", choices=("inline", "rej"), default="inline")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--pretend", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--skip-docs-check", action="store_true")
    parser.add_argument("--skip-beads-check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    destination = git_root(args.destination.expanduser().resolve())
    preflight = project_preflight(destination, args.answers_file)
    if args.preflight:
        if args.json:
            print(json.dumps(preflight, indent=2, sort_keys=True))
        else:
            print(f"Recommended workflow: /{preflight['recommended_workflow']}")
            print(f"Reason: {preflight['reason']}")
            for path in preflight["legacy_task_files"]:
                print(f"  - {path}")
        return 0

    if preflight["recommended_workflow"] == "migrate-workflow":
        tasks = preflight["legacy_task_files"]
        details = "\n".join(f"  - {path}" for path in tasks)
        message = (
            f"{preflight['reason']}. Do not run Copier update yet; offer /migrate-workflow "
            "and run it only after the user agrees."
        )
        if details:
            message += f"\nLegacy task files:\n{details}"
        raise SystemExit(message)

    answers = destination / args.answers_file
    answer_data = load_answers(answers)
    source = str(answer_data.get("_src_path") or "").strip()
    if not source:
        msg = f"Copier answers do not contain _src_path: {answers}"
        raise SystemExit(msg)

    validate_template_source(source)

    requested_vcs_ref = args.vcs_ref
    effective_vcs_ref = requested_vcs_ref or default_vcs_ref(source, include_prereleases=args.prereleases)
    verified_source_commit = require_release_tag(source, effective_vcs_ref)

    before = git_status(destination)
    if before and not args.allow_dirty:
        preview = "\n".join(f"  {line}" for line in before[:25])
        msg = "Commit or stash changes before updating the template:\n" + preview
        raise SystemExit(msg)
    if unmerged_paths(destination):
        msg = "Resolve existing Git merge conflicts before updating the template"
        raise SystemExit(msg)

    baseline_rejects = reject_files(destination)
    try:
        run_update(
            destination,
            answers_file=args.answers_file,
            vcs_ref=effective_vcs_ref,
            use_prereleases=args.prereleases,
            defaults=not args.interactive,
            pretend=args.pretend,
            quiet=args.quiet or args.json,
            conflict=args.conflict,
            overwrite=True,
            unsafe=False,
        )
    except Exception as exc:  # Copier exposes multiple user-facing exception types.
        msg = f"Copier could not update {destination} to {effective_vcs_ref}: {exc}"
        raise SystemExit(msg) from exc

    conflicts: list[str] = []
    docs_validated = False
    beads_health: dict[str, Any] | None = None
    warnings: list[str] = []
    tooling = skipped_tooling()
    if not args.pretend:
        conflicts = scan_conflicts(destination, baseline_rejects=baseline_rejects)
        if conflicts:
            tooling = skipped_tooling(recovery=[TOOLING_RERUN])
            print("Copier produced unresolved conflicts:", file=sys.stderr)
            for path in conflicts:
                print(f"  - {path}", file=sys.stderr)
        else:
            tooling = provision_tooling(destination)
            if tooling["status"] != "succeeded":
                warnings.append("Tooling reconciliation is incomplete; run the reported recovery commands")

        if not conflicts and not args.skip_docs_check:
            checker = destination / "scripts/check-docs.py"
            if checker.exists():
                run(
                    ["uv", "run", str(checker)],
                    cwd=destination,
                    quiet=args.quiet or args.json,
                )
                docs_validated = True
            else:
                warnings.append("scripts/check-docs.py is not present; documentation validation skipped")

        if not conflicts and not args.skip_beads_check:
            if not bd_available(destination):
                warnings.append("bd is unavailable or its launcher cannot execute; Beads health checks skipped")
            else:
                beads_health = check_beads(destination)

    changed = git_status(destination) if not args.pretend else []
    changed_paths = {line[3:] for line in changed if len(line) > 3}
    revision_changed = answer_data.get("_commit") != load_answers(answers).get("_commit")
    answers_only = bool(changed_paths) and changed_paths <= {args.answers_file}
    if not args.pretend and revision_changed and answers_only:
        warnings.append(
            "Template revision changed but only the Copier answers file changed; "
            "verify conditional template destinations and expected rendered output"
        )
    updated_answers = load_answers(answers) if answers.exists() else {}
    result = {
        "destination": str(destination),
        "answers_file": str(answers),
        "template_source": source,
        "previous_commit": answer_data.get("_commit"),
        "requested_vcs_ref": requested_vcs_ref,
        "vcs_ref": effective_vcs_ref,
        "resolved_commit": updated_answers.get("_commit"),
        "verified_source_commit": verified_source_commit,
        "pretend": args.pretend,
        "conflicts": conflicts,
        "changed_files": changed,
        "docs_validated": docs_validated,
        "beads_checked": beads_health is not None,
        "beads_health": beads_health,
        "warnings": warnings,
        "tooling": tooling,
        "outstanding": [f"Tooling recovery: {command}" for command in tooling["recovery"]],
        "ready_to_resume_feature_work": bool(
            not args.pretend and not conflicts and tooling["status"] == "succeeded" and not changed
        ),
        "preflight": preflight,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        action = "Previewed" if args.pretend else "Applied"
        print(f"{action} dstack template update {effective_vcs_ref} in {destination}")
        if changed:
            print("Changed files:")
            for line in changed:
                print(f"  {line}")
        if beads_health is not None:
            print("Beads health checks passed:")
            for command in beads_health["commands"]:
                print(f"  - {command}")
        print(f"Tooling reconciliation: {tooling['status']}")
        for command in tooling["recovery"]:
            print(f"Tooling recovery: {command}")
        for warning in warnings:
            print(f"Warning: {warning}")
        print("Review the diff and commit the template update as a dedicated change.")
    return 2 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
