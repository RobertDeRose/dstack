#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: S603, S607
"""Initialize or verify a dstack Beads documentation workflow."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


README_MARKER = "<!-- dstack:generated-readme -->"
UNIVERSAL_PATHS = (
    Path(".copier-answers.yml"),
    Path("AGENTS.md"),
    Path(".beads/formulas/feature-lifecycle.formula.toml"),
    Path("scripts/check-docs.py"),
    Path("docs/src/features/_template/design.md"),
    Path("docs/src/features/_template/index.md"),
)
FORMULA_VARS = (
    "feature_number=010",
    "feature_name=Example",
    "feature_slug=example",
    "design_path=docs/src/features/010-example/design.md",
    "implemented_path=docs/src/features/010-example/index.md",
    "base_branch=main",
)


def repository_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path(__file__).resolve().parents[1]


def run(command: Sequence[str], *, cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def summary_targets(root: Path) -> set[Path]:
    summary = root / "docs/src/SUMMARY.md"
    if not summary.exists():
        return set()
    targets: set[Path] = set()
    for raw in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", summary.read_text(encoding="utf-8")):
        target = raw.strip().split("#", 1)[0]
        if target and not target.startswith(("http://", "https://", "mailto:")):
            targets.add(Path("docs/src") / target)
    return targets


def verify_scaffold(root: Path) -> None:
    expected = set(UNIVERSAL_PATHS) | summary_targets(root)
    missing = [path for path in sorted(expected) if not (root / path).exists()]
    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        message = f"Workflow scaffold is incomplete:\n{details}"
        raise SystemExit(message)


def detect_migration_mode(root: Path) -> bool:
    if (root / "migration/workflow-migration.json").exists():
        return True
    features = root / "docs/src/features"
    if not features.exists():
        return False
    if any(features.glob("*/tasks.md")):
        return True
    numbered = re.compile(r"^[0-9]{3,}-[a-z0-9]+(?:-[a-z0-9]+)*$")
    return any(
        path.is_dir()
        and not path.name.startswith("_")
        and path.name != "index.md"
        and numbered.fullmatch(path.name) is None
        for path in features.iterdir()
    )


def ensure_trailing_newline(path: Path) -> None:
    if not path.is_file():
        return
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        path.write_bytes(content + b"\n")


def git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 and completed.stdout.strip() else None


def bd_available(root: Path) -> bool:
    if shutil.which("bd") is None:
        return False
    completed = subprocess.run(["bd", "--version"], cwd=root, check=False, capture_output=True, text=True)
    return completed.returncode == 0


def initialize_beads(root: Path, args: argparse.Namespace) -> None:
    if not bd_available(root):
        message = "The 'bd' command is not installed. Install Beads, or rerun with --skip-beads."
        raise SystemExit(message)
    command = ["bd", "init"]
    if args.quiet:
        command.append("--quiet")
    if args.skip_agents:
        command.append("--skip-agents")
    if args.beads_mode == "stealth":
        command.append("--stealth")
    elif args.beads_mode == "contributor":
        command.append("--contributor")
    elif args.beads_mode == "server":
        command.append("--server")
    run(command, cwd=root)
    for integration in args.setup:
        run(["bd", "setup", integration], cwd=root)
    if not args.skip_formula_check:
        command = ["bd", "mol", "seed", "feature-lifecycle"]
        for value in FORMULA_VARS:
            command.extend(("--var", value))
        run(command, cwd=root)
    ensure_trailing_newline(root / ".beads/metadata.json")
    ensure_trailing_newline(root / ".beads/config.yaml")


def delete_readme(root: Path, *, force: bool) -> None:
    readme = root / "README.md"
    if not readme.exists():
        return
    content = readme.read_text(encoding="utf-8")
    if README_MARKER not in content and not force:
        message = (
            "README.md no longer contains the dstack marker. "
            "Use --force-delete-readme only when deletion is intentional."
        )
        raise SystemExit(message)
    readme.unlink()
    print("Deleted README.md")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--beads-mode",
        choices=("default", "stealth", "contributor", "server"),
        default="stealth",
    )
    parser.add_argument("--setup", action="append", default=[], metavar="INTEGRATION")
    parser.add_argument("--skip-beads", action="store_true")
    parser.add_argument(
        "--skip-agents",
        dest="skip_agents",
        action="store_true",
        help="Do not let bd init install additional agent integrations (default).",
    )
    parser.add_argument(
        "--install-agents",
        dest="skip_agents",
        action="store_false",
        help="Allow bd init to install its default agent integrations.",
    )
    parser.set_defaults(skip_agents=True)
    parser.add_argument("--skip-formula-check", action="store_true")
    parser.add_argument(
        "--migration-mode",
        action="store_true",
        help="Validate legacy task/docs structures as warnings during adoption.",
    )
    parser.add_argument(
        "--strict-docs",
        action="store_true",
        help="Disable automatic migration-mode detection and require the current documentation contract.",
    )
    parser.add_argument("--delete-readme", action="store_true")
    parser.add_argument("--force-delete-readme", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = repository_root()
    verify_scaffold(root)
    if not args.skip_beads:
        initialize_beads(root, args)
    checker = ["uv", "run", "scripts/check-docs.py"]
    migration_mode = args.migration_mode or (not args.strict_docs and detect_migration_mode(root))
    if migration_mode:
        checker.append("--migration-mode")
        if not args.quiet:
            print("Detected a legacy workflow; running documentation checks in migration mode.")
    run(checker, cwd=root)
    ensure_trailing_newline(root / ".beads/metadata.json")
    ensure_trailing_newline(root / ".beads/config.yaml")
    if args.delete_readme:
        delete_readme(root, force=args.force_delete_readme)
    verify_scaffold(root)
    result = {
        "scaffold_verified": True,
        "migration_mode": migration_mode,
        "beads_initialized": not args.skip_beads,
        "beads_mode": None if args.skip_beads else args.beads_mode,
        "formula_verified": not args.skip_beads and not args.skip_formula_check,
        "docs_status": "passed",
        "outstanding": ["Beads initialization and verification"] if args.skip_beads else [],
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print("dstack workflow scaffold verified.")
    if not args.skip_beads:
        print("Beads initialized and feature-lifecycle formula verified.")
        print("Next: run 'bd prime' and 'bd ready --json', then use /plan-features or /migrate-workflow.")
    else:
        print("Beads initialization and verification were skipped and remain outstanding.")
        print("After initializing Beads, run 'bd prime' and 'bd ready --json'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
