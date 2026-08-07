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
# ruff: noqa: EM102, S603, S607
"""Create and initialize a new Copier-managed dstack project."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from copier import run_copy
from packaging.version import InvalidVersion, Version


SKILL_DIR = Path(__file__).resolve().parents[1]
CORE_SCRIPTS = SKILL_DIR.parent / "dstack-core" / "scripts"
BEADS_HOOKS_SPEC = importlib.util.spec_from_file_location("dstack_beads_hooks", CORE_SCRIPTS / "beads_hooks.py")
if BEADS_HOOKS_SPEC is None or BEADS_HOOKS_SPEC.loader is None:
    raise SystemExit(f"Beads hook helper is missing from {CORE_SCRIPTS}")
BEADS_HOOKS_MODULE: Any = importlib.util.module_from_spec(BEADS_HOOKS_SPEC)
BEADS_HOOKS_SPEC.loader.exec_module(BEADS_HOOKS_MODULE)
install_and_verify_beads_hooks = BEADS_HOOKS_MODULE.install_and_verify_beads_hooks
skipped_beads_hooks = BEADS_HOOKS_MODULE.skipped_beads_hooks
unavailable_beads_hooks = BEADS_HOOKS_MODULE.unavailable_beads_hooks

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from layout_contract import render_package_configs, validate_layout  # noqa: E402


SKILL_MANIFEST = SKILL_DIR / "SKILL.md"
BUNDLED_TEMPLATE_SOURCE = SKILL_DIR
DEFAULT_UPDATE_SOURCE = "gh:RobertDeRose/dstack"
FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---(?:\n|\Z)", re.DOTALL)
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
PROJECT_KINDS = ("library", "cli", "service", "application", "infrastructure", "documentation", "other")
LANGUAGE_PROFILES = ("python", "typescript", "rust", "go", "elixir", "nix", "other")
BRIEF_FLAGS = {
    "project_purpose": "--purpose",
    "project_users": "--users",
    "project_scope": "--scope",
    "project_boundaries": "--boundaries",
}
REQUIRED_GENERATED_PATHS = (
    Path(".copier-answers.yml"),
    Path("AGENTS.md"),
    Path(".beads/formulas/dstack-feature.formula.toml"),
    Path("docs/book.toml"),
    Path("docs/src/SUMMARY.md"),
    Path("docs/src/planned-features.md"),
    Path("docs/src/features/_template/design.md"),
    Path("docs/src/features/_template/index.md"),
    Path("docs/src/development/tooling.md"),
    Path("docs/src/reference/tooling.md"),
    Path("mise.toml"),
    Path("hk.pkl"),
    Path(".config/rumdl.toml"),
    Path("contextlint.config.json"),
    Path("scripts/check-docs.py"),
    Path("scripts/setup-tooling.py"),
)

# A project-local skills installation can exist before the project scaffold does.
ALLOWED_EXISTING_ENTRIES = {".git", "skills-lock.json"}


def load_yaml_mapping(path: Path, *, label: str) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        message = f"Unable to read {label} from {path}: {exc}"
        raise SystemExit(message) from exc
    if not isinstance(loaded, dict):
        message = f"{label.capitalize()} must be a mapping: {path}"
        raise SystemExit(message)
    return loaded


def load_skill_version(path: Path = SKILL_MANIFEST) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Unable to read installed skill metadata from {path}: {exc}"
        raise SystemExit(message) from exc
    match = FRONTMATTER_PATTERN.match(text)
    if match is None:
        message = f"Installed skill has invalid frontmatter: {path}"
        raise SystemExit(message)
    try:
        manifest = yaml.safe_load(match.group("frontmatter"))
    except yaml.YAMLError as exc:
        message = f"Unable to parse installed skill metadata from {path}: {exc}"
        raise SystemExit(message) from exc
    if not isinstance(manifest, dict):
        message = f"Installed skill frontmatter must be a mapping: {path}"
        raise SystemExit(message)
    metadata = manifest.get("metadata")
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        message = f"Installed skill metadata.version must be a stable X.Y.Z value: {path}"
        raise SystemExit(message)
    return version


def record_update_state(path: Path, *, source: str, commit: str, channel: str) -> None:
    """Record the exact reachable template revision used for rendering."""
    data = load_yaml_mapping(path, label="Copier answers")
    recorded: dict[str, Any] = {
        "_commit": commit,
        "_src_path": source,
        "dstack_template_channel": channel,
    }
    recorded.update({key: value for key, value in data.items() if key not in recorded})
    rendered = yaml.safe_dump(recorded, allow_unicode=True, sort_keys=False)
    path.write_text(
        "# This file is managed by Copier. Do not edit it manually.\n" + rendered,
        encoding="utf-8",
    )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundled_file_digests(root: Path) -> dict[str, str]:
    paths = [root / "copier.yml", *(root / "template").rglob("*")]
    return {
        path.relative_to(root).as_posix(): _file_digest(path)
        for path in paths
        if path.is_file() and not any(part in {"__pycache__", ".DS_Store"} for part in path.relative_to(root).parts)
    }


def _archive_file_digests(repository: Path, commit: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "archive",
            "--format=tar",
            commit,
            "--",
            "skills/setup-project/copier.yml",
            "skills/setup-project/template",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        message = f"Selected template commit {commit} does not contain the setup-project template"
        raise SystemExit(message)
    prefix = "skills/setup-project/"
    digests: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            for member in archive:
                if not member.isfile() or not member.name.startswith(prefix):
                    continue
                relative = member.name.removeprefix(prefix)
                if relative != "copier.yml" and not relative.startswith("template/"):
                    continue
                if any(part in {"__pycache__", ".DS_Store"} for part in Path(relative).parts):
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise SystemExit(f"Unable to read selected template file {relative}")
                digest = hashlib.sha256()
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                digests[relative] = digest.hexdigest()
    except tarfile.TarError as exc:
        raise SystemExit(f"Unable to read the selected template archive: {exc}") from exc
    return digests


def _clone_revision_digests(source: str, commit: str, checkout: Path) -> dict[str, str]:
    clone_source = git_source(source)
    cloned = subprocess.run(
        ["git", "clone", "--quiet", "--no-checkout", clone_source, str(checkout)],
        check=False,
        capture_output=True,
        text=True,
    )
    if cloned.returncode != 0:
        message = f"Unable to verify the bundled template against {source!r}: {cloned.stderr.strip()}"
        raise SystemExit(message)
    return _archive_file_digests(checkout, commit)


def _template_revision_digests(source: str, commit: str) -> dict[str, str]:
    local_root = local_git_root(source)
    if local_root is not None:
        return _archive_file_digests(local_root, commit)

    with tempfile.TemporaryDirectory(prefix="dstack-bundled-template-") as temporary:
        checkout = Path(temporary) / "source"
        initialized = subprocess.run(
            ["git", "init", "--quiet", str(checkout)],
            check=False,
            capture_output=True,
            text=True,
        )
        fetched = None
        if initialized.returncode == 0:
            remote = subprocess.run(
                ["git", "-C", str(checkout), "remote", "add", "origin", git_source(source)],
                check=False,
                capture_output=True,
                text=True,
            )
            if remote.returncode == 0:
                fetched = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(checkout),
                        "fetch",
                        "--quiet",
                        "--filter=blob:none",
                        "--no-tags",
                        "--depth=1",
                        "origin",
                        commit,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
        if fetched is not None and fetched.returncode == 0:
            return _archive_file_digests(checkout, commit)
        shutil.rmtree(checkout, ignore_errors=True)
        return _clone_revision_digests(source, commit, checkout)


def verify_bundled_revision(source: str, commit: str) -> None:
    expected = _bundled_file_digests(BUNDLED_TEMPLATE_SOURCE)
    selected = _template_revision_digests(source, commit)
    if expected != selected:
        message = (
            "The installed setup-project template does not match the selected template commit. "
            "Update the installed dstack skills or choose an explicit --template-source."
        )
        raise SystemExit(message)


def validate_template_source(source: str) -> None:
    if any(character in source for character in ("\n", "\r", "\x00")):
        message = "Template source contains prohibited control characters"
        raise SystemExit(message)
    if Path(source).expanduser().exists():
        return
    if source.startswith(("gh:", "gl:", "https://", "ssh://", "git@")):
        return
    message = (
        "Unsupported template source. Use an existing local path or an explicit "
        "gh:, gl:, https://, ssh://, or git@ source."
    )
    raise SystemExit(message)


def git_source(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source.removeprefix('gh:')}.git"
    if source.startswith("gl:"):
        return f"https://gitlab.com/{source.removeprefix('gl:')}.git"
    return source


def tagged_version(tag: str) -> Version | None:
    if not tag.startswith("v"):
        return None
    try:
        version = Version(tag.removeprefix("v"))
    except InvalidVersion:
        return None
    return version if len(version.release) == 3 else None


def local_git_root(source: str) -> Path | None:
    path = Path(source).expanduser()
    if not path.exists():
        return None
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    return Path(completed.stdout.strip()) if completed.returncode == 0 else None


def release_refs(source: str) -> dict[str, str]:
    root = local_git_root(source)
    if root is not None:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "for-each-ref",
                "--format=%(refname:short) %(objectname) %(*objectname)",
                "refs/tags/v*",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        refs: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            tag, direct, *peeled = line.split()
            refs[tag] = peeled[0] if peeled else direct
        return refs

    completed = subprocess.run(
        ["git", "ls-remote", "--tags", git_source(source), "refs/tags/v*"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = f"Unable to discover dstack release tags from {source!r}"
        raise SystemExit(message)
    direct: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        sha, ref = line.split()
        tag = ref.removeprefix("refs/tags/")
        if tag.endswith("^{}"):
            peeled[tag.removesuffix("^{}")] = sha
        else:
            direct[tag] = sha
    return {tag: peeled.get(tag, sha) for tag, sha in direct.items()}


def latest_stable(source: str) -> tuple[str, str]:
    releases = [
        (version, tag, sha)
        for tag, sha in release_refs(source).items()
        if (version := tagged_version(tag)) is not None and not version.is_prerelease and not version.is_devrelease
    ]
    if not releases:
        message = f"No stable dstack release tags found in {source!r}"
        raise SystemExit(message)
    _, tag, sha = max(releases)
    return tag, sha


def source_head(source: str) -> tuple[str, str]:
    root = local_git_root(source)
    if root is not None:
        branch = (
            subprocess.run(
                ["git", "-C", str(root), "symbolic-ref", "--short", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
            or "HEAD"
        )
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{commit}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return branch, sha

    completed = subprocess.run(
        ["git", "ls-remote", "--symref", git_source(source), "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = f"Unable to resolve the default branch HEAD from {source!r}"
        raise SystemExit(message)
    branch = "HEAD"
    sha = ""
    for line in completed.stdout.splitlines():
        if line.startswith("ref:") and line.endswith("\tHEAD"):
            branch = line.split()[1].removeprefix("refs/heads/")
        elif line.endswith("\tHEAD"):
            sha = line.split()[0]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        message = f"The default branch HEAD from {source!r} did not resolve to a commit"
        raise SystemExit(message)
    return branch, sha


def explicit_ref(source: str, requested: str) -> tuple[str, str]:
    root = local_git_root(source)
    if root is not None:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", f"{requested}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return requested, completed.stdout.strip()
        message = f"Template revision {requested!r} is not available from {source!r}"
        raise SystemExit(message)

    patterns = [requested, f"refs/heads/{requested}", f"refs/tags/{requested}", f"refs/tags/{requested}^{{}}"]
    completed = subprocess.run(
        ["git", "ls-remote", git_source(source), *patterns],
        check=False,
        capture_output=True,
        text=True,
    )
    refs = {ref: sha for sha, ref in (line.split() for line in completed.stdout.splitlines())}
    sha = refs.get(f"refs/tags/{requested}^{{}}") or refs.get(f"refs/tags/{requested}")
    sha = sha or refs.get(f"refs/heads/{requested}") or refs.get(requested)
    if not sha and re.fullmatch(r"[0-9a-f]{40}", requested):
        with tempfile.TemporaryDirectory(prefix="dstack-revision-") as temporary:
            subprocess.run(["git", "init", "--bare", temporary], check=True, capture_output=True)
            fetched = subprocess.run(
                ["git", "-C", temporary, "fetch", "--depth=1", git_source(source), requested],
                check=False,
                capture_output=True,
                text=True,
            )
            if fetched.returncode == 0:
                sha = requested
    if completed.returncode != 0 or not sha:
        message = f"Template revision {requested!r} is not available from {source!r}"
        raise SystemExit(message)
    return requested, sha


def selected_revision(source: str, channel: str, requested: str | None) -> tuple[str, str]:
    if requested:
        return explicit_ref(source, requested)
    return latest_stable(source) if channel == "stable" else source_head(source)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        message = "Project name must contain at least one letter or number"
        raise ValueError(message)
    return slug


def project_brief(args: argparse.Namespace) -> dict[str, str]:
    missing = [flag for field, flag in BRIEF_FLAGS.items() if not getattr(args, field.removeprefix("project_"))]
    if args.project_kind is None:
        missing.append("--project-kind")
    if missing:
        message = "New-project setup requires " + ", ".join(missing)
        if "--project-kind" in missing:
            message += "; accepted kinds: " + ", ".join(PROJECT_KINDS)
        raise SystemExit(message)

    brief: dict[str, str] = {}
    for field, flag in BRIEF_FLAGS.items():
        raw_value = getattr(args, field.removeprefix("project_"))
        if any(character in raw_value for character in ("\x00", "\r", "\n")):
            message = f"{flag} must be a single line without NUL, CR, or LF characters"
            raise SystemExit(message)
        value = raw_value.strip()
        if not value:
            message = f"{flag} must not be blank"
            raise SystemExit(message)
        brief[field] = value
    brief["project_kind"] = args.project_kind
    return brief


def canonical_language_profiles(values: Sequence[str]) -> list[str]:
    if not values:
        message = "New-project setup requires --language-profile"
        raise SystemExit(message)
    unknown = sorted(set(values) - set(LANGUAGE_PROFILES))
    if unknown:
        raise SystemExit("Unknown language profile: " + ", ".join(unknown))
    if len(values) != len(set(values)):
        message = "Language profiles must not contain duplicates"
        raise SystemExit(message)
    if "other" in values and len(values) > 1:
        message = "The other language profile cannot be combined with recognized profiles"
        raise SystemExit(message)
    return [profile for profile in LANGUAGE_PROFILES if profile in values]


def run_checked(command: Sequence[str], *, cwd: Path, quiet: bool) -> subprocess.CompletedProcess[str]:
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


def bd_available(cwd: Path) -> bool:
    if shutil.which("bd") is None:
        return False
    completed = subprocess.run(["bd", "--version"], cwd=cwd, check=False, capture_output=True, text=True)
    return completed.returncode == 0


BEADS_CONTROL_PATHS = {
    ".beads/.gitignore",
    ".beads/README.md",
    ".beads/config.yaml",
    ".beads/interactions.jsonl",
    ".beads/metadata.json",
    ".beads/formulas/dstack-feature.formula.toml",
}


def validate_setup_beads_authority(destination: Path, prefix: str) -> None:
    context = json.loads(run_checked(["bd", "context", "--json"], cwd=destination, quiet=True).stdout)
    location = json.loads(run_checked(["bd", "where", "--json"], cwd=destination, quiet=True).stdout)
    metadata = json.loads((destination / ".beads/metadata.json").read_text(encoding="utf-8"))
    expected_beads = (destination / ".beads").resolve()
    expected_database = prefix.replace("-", "_")
    problems: list[str] = []
    for value, expected, description in (
        (context.get("beads_dir"), expected_beads, "context beads_dir"),
        (context.get("repo_root"), destination.resolve(), "context repo_root"),
        (location.get("path"), expected_beads, "where path"),
    ):
        try:
            matches = Path(str(value)).resolve() == expected
        except (OSError, RuntimeError, ValueError):
            matches = False
        if not matches:
            problems.append(description)
    try:
        database_path = Path(str(location.get("database_path", ""))).resolve()
        if not database_path.is_relative_to(expected_beads):
            problems.append("where database_path")
    except (OSError, RuntimeError, ValueError):
        problems.append("where database_path")
    if context.get("database") != expected_database or metadata.get("dolt_database") != expected_database:
        problems.append("database identity")
    if location.get("prefix") != prefix:
        problems.append("issue prefix")
    if not metadata.get("project_id") or context.get("project_id") != metadata.get("project_id"):
        problems.append("project_id")
    if context.get("dolt_mode") != "embedded" or context.get("is_redirected") is True:
        problems.append("embedded non-redirected mode")
    if problems:
        message = "Collaborative Beads authority validation failed: " + ", ".join(problems)
        raise SystemExit(message)


def initialize_beads(destination: Path, args: argparse.Namespace, *, prefix: str, quiet: bool) -> dict[str, Any]:
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=destination, check=False, capture_output=True, text=True
    )
    if git_root.returncode != 0 or Path(git_root.stdout.strip()).resolve() != destination.resolve():
        message = "Collaborative Beads initialization requires the destination to be its own Git repository"
        raise SystemExit(message)
    beads_dir = destination / ".beads"
    formula = beads_dir / "formulas/dstack-feature.formula.toml"
    if (
        not beads_dir.is_dir()
        or beads_dir.is_symlink()
        or any(path.is_symlink() for path in beads_dir.rglob("*"))
        or any(path.name != "formulas" for path in beads_dir.iterdir())
        or not formula.is_file()
    ):
        message = "Native Beads initialization requires a nonsymlinked formula-only .beads directory"
        raise SystemExit(message)

    before_result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=destination, check=False, capture_output=True, text=True
    )
    before = before_result.stdout.strip() if before_result.returncode == 0 else ""
    command = ["bd", "init", "--non-interactive", "--skip-agents", "--skip-hooks", "--prefix", prefix]
    if quiet:
        command.append("--quiet")
    run_checked(command, cwd=destination, quiet=quiet)
    validate_setup_beads_authority(destination, prefix)
    run_checked(["bd", "formula", "show", "dstack-feature", "--json"], cwd=destination, quiet=True)

    after = run_checked(["git", "rev-parse", "HEAD"], cwd=destination, quiet=True).stdout.strip()
    if after == before:
        message = "Native bd init did not create its collaborative-control commit"
        raise SystemExit(message)
    if before:
        changed_output = run_checked(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", before, after],
            cwd=destination,
            quiet=True,
        ).stdout
    else:
        changed_output = run_checked(
            ["git", "show", "--pretty=", "--name-only", after], cwd=destination, quiet=True
        ).stdout
    allowed = BEADS_CONTROL_PATHS | {".gitignore"}
    unexpected = sorted(set(changed_output.splitlines()) - allowed)
    if unexpected:
        raise SystemExit("Native bd init committed unexpected project paths: " + ", ".join(unexpected))

    readme = destination / ".beads/README.md"
    readme_text = readme.read_text(encoding="utf-8")
    if not readme_text.startswith("<!-- rumdl-disable -->"):
        readme.write_text("<!-- rumdl-disable -->\n\n" + readme_text.lstrip(), encoding="utf-8")
    run_checked(
        ["mise", "x", "--", "hk", "run", "pre-commit", ".gitignore", *sorted(BEADS_CONTROL_PATHS)],
        cwd=destination,
        quiet=quiet,
    )
    run_checked(["git", "add", ".beads/README.md"], cwd=destination, quiet=True)
    identity = subprocess.run(
        ["git", "log", "-1", "--format=%an%x00%ae"],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    identity_args: list[str] = []
    if identity.returncode == 0:
        name, separator, email = identity.stdout.strip().partition("\0")
        if separator and name and email:
            identity_args = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    run_checked(
        ["git", *identity_args, "commit", "--amend", "-m", "chore: initialize Beads workflow state"],
        cwd=destination,
        quiet=quiet,
    )
    beads_hooks = install_and_verify_beads_hooks(destination, available=True, quiet=quiet)
    for integration in args.setup:
        run_checked(["bd", "setup", integration], cwd=destination, quiet=quiet)
    return beads_hooks


def verify_scaffold(destination: Path) -> None:
    missing = [path for path in REQUIRED_GENERATED_PATHS if not (destination / path).is_file()]
    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        message = f"Workflow scaffold is incomplete:\n{details}"
        raise SystemExit(message)
    forbidden = [Path("scripts/bootstrap.py"), Path("scripts/migrate-legacy-workflow.py"), Path("MIGRATION.md")]
    unexpected = [path for path in forbidden if (destination / path).exists()]
    if unexpected:
        details = "\n".join(f"  - {path}" for path in unexpected)
        message = f"New-project scaffold contains migration-only files:\n{details}"
        raise SystemExit(message)


def validate_docs(destination: Path, *, quiet: bool) -> None:
    command = [sys.executable, "scripts/check-docs.py"]
    if quiet:
        command.append("--json")
    run_checked(command, cwd=destination, quiet=quiet)


TOOLING_RERUN = "python3 scripts/setup-tooling.py --json"
TOOLING_PLATFORMS = ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"]


def skipped_tooling() -> dict[str, Any]:
    return {
        "status": "skipped",
        "mise": "skipped",
        "lock": {"status": "skipped", "path": "mise.lock", "error": None},
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
    command = [sys.executable, "scripts/setup-tooling.py", "--json"]
    completed = subprocess.run(command, cwd=destination, check=False, capture_output=True, text=True)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = None
    error = tooling_result_error(result, destination) if isinstance(result, dict) else None
    if completed.returncode == 0 and isinstance(result, dict) and error is None:
        return result

    error = (
        error
        or (completed.stderr or completed.stdout or "tooling provisioner returned invalid output").strip()[-2_000:]
    )
    return {
        "status": "degraded",
        "mise": "skipped",
        "lock": {"status": "failed", "path": "mise.lock", "error": error},
        "install": {"status": "skipped", "error": None},
        "hooks": {"status": "skipped", "error": None},
        "platforms": TOOLING_PLATFORMS,
        "recovery": [TOOLING_RERUN],
    }


def own_git_repository(destination: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=destination, check=False, capture_output=True, text=True
    )
    return result.returncode == 0 and Path(result.stdout.strip()).resolve() == destination.resolve()


def initialize_git(destination: Path, branch: str, *, quiet: bool) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return False
    if shutil.which("git") is None:
        message = "Git is required for Copier-managed template updates"
        raise SystemExit(message)

    result = subprocess.run(
        ["git", "-C", str(destination), "init", "-b", branch],
        check=False,
        capture_output=quiet,
        text=True,
    )
    if result.returncode != 0:
        run_checked(["git", "init"], cwd=destination, quiet=quiet)
        run_checked(["git", "branch", "-M", branch], cwd=destination, quiet=quiet)
    return True


def is_skills_cli_entry(entry: Path) -> bool:
    """Accept an installed skills tree, but not unrelated files beside it."""
    if not entry.is_dir():
        return False
    skill_root = entry if entry.name == "skills" else entry / "skills"
    if not skill_root.is_dir() or not any(skill_root.glob("*/SKILL.md")):
        return False
    return all(path.is_relative_to(skill_root) for path in entry.rglob("*"))


def unexpected_entries(destination: Path) -> list[Path]:
    if not destination.exists():
        return []
    return sorted(
        (
            entry
            for entry in destination.iterdir()
            if entry.name not in ALLOWED_EXISTING_ENTRIES and not is_skills_cli_entry(entry)
        ),
        key=lambda entry: entry.name,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_name", nargs="?", help="Human-readable project name; defaults to basename($PWD).")
    parser.add_argument(
        "--destination",
        "-d",
        type=Path,
        default=Path.cwd(),
        help="Destination directory; defaults to the current directory.",
    )
    parser.add_argument("--project-slug")
    parser.add_argument("--purpose", help="One-sentence description of the problem and intended outcome.")
    parser.add_argument("--users", help="One-sentence description of the intended users.")
    parser.add_argument("--scope", help="One-sentence description of current supported scope.")
    parser.add_argument("--boundaries", help="One-sentence description of key exclusions and ownership boundaries.")
    parser.add_argument("--project-kind", choices=PROJECT_KINDS)
    parser.add_argument(
        "--language-profile",
        action="append",
        default=[],
        choices=LANGUAGE_PROFILES,
        help="Implementation language profile; repeat for polyglot repositories.",
    )
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--repository-layout",
        choices=("single-package", "monorepo"),
        default="single-package",
    )
    parser.add_argument(
        "--monorepo-package",
        action="append",
        default=[],
        metavar="JSON",
        help="Exact package object as JSON; repeat once per explicit package.",
    )
    parser.add_argument(
        "--template-source",
        help="Template Git source; defaults to gh:RobertDeRose/dstack.",
    )
    parser.add_argument("--vcs-ref", help="One-shot template tag, branch, or commit override.")
    channel = parser.add_mutually_exclusive_group()
    channel.add_argument("--stable", action="store_true", help="Use the newest stable release tag (default).")
    channel.add_argument("--unstable", action="store_true", help="Use the source default branch HEAD.")
    parser.add_argument("--delete-readme", action="store_true")
    parser.add_argument("--no-git-init", action="store_true")
    parser.add_argument("--skip-post-setup", action="store_true")
    parser.add_argument("--skip-beads", action="store_true")
    parser.add_argument(
        "--beads-mode",
        choices=("default",),
        default="default",
    )
    parser.add_argument(
        "--setup",
        action="append",
        default=[],
        metavar="INTEGRATION",
        help="Run bd setup for an integration after bd init; repeatable.",
    )
    parser.add_argument("--preflight", action="store_true", help="Validate and report layout without rendering.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    destination = args.destination.expanduser().resolve()
    answers = destination / ".copier-answers.yml"
    if answers.exists():
        message = (
            f"{destination} is already Copier-managed. /setup-project will not modify it; "
            "offer /update-project and run it only after the user agrees."
        )
        raise SystemExit(message)

    existing = unexpected_entries(destination)
    if existing and not args.preflight:
        shown = "\n".join(f"  - {entry.name}" for entry in existing[:25])
        raise SystemExit(
            "Destination contains project files. New-project setup will not adopt or migrate them. "
            "Use /migrate-workflow for an existing project:\n" + shown
        )

    project_name = (args.project_name or Path.cwd().name).strip()
    if not project_name:
        message = "Project name cannot be empty"
        raise SystemExit(message)
    project_slug = args.project_slug or slugify(project_name)
    try:
        package_answers = [json.loads(value) for value in args.monorepo_package]
        layout_preflight = validate_layout(args.repository_layout, package_answers, destination)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid repository layout: {exc}") from exc
    if args.preflight:
        if args.json:
            print(json.dumps(layout_preflight, indent=2, sort_keys=True))
        else:
            print(f"Repository layout: {layout_preflight['repository_layout']}")
            for package in layout_preflight["packages"]:
                print(f"  - {package['slug']}: {package['destination']} (occupied={package['occupied']})")
        return 0

    brief = project_brief(args)
    if args.repository_layout == "monorepo":
        profile_set = {profile for package in package_answers for profile in package["language_profiles"]}
        language_profiles = [profile for profile in LANGUAGE_PROFILES if profile in profile_set]
        if "other" in language_profiles and len(language_profiles) > 1:
            language_profiles.remove("other")
    else:
        language_profiles = canonical_language_profiles(args.language_profile)

    skill_version = load_skill_version()
    channel = "unstable" if args.unstable else "stable"
    update_source = args.template_source or DEFAULT_UPDATE_SOURCE
    validate_template_source(update_source)
    selected_ref, resolved_template_commit = selected_revision(update_source, channel, args.vcs_ref)
    using_bundled_template = args.template_source is None
    if using_bundled_template:
        verify_bundled_revision(update_source, resolved_template_commit)
        template_source = str(BUNDLED_TEMPLATE_SOURCE)
        render_vcs_ref = None
    else:
        template_source = update_source
        render_vcs_ref = resolved_template_commit
    source_root = local_git_root(update_source)
    recorded_update_source = str(source_root.resolve()) if source_root is not None else update_source

    destination.mkdir(parents=True, exist_ok=True)
    run_copy(
        template_source,
        destination,
        data={
            "project_name": project_name,
            "project_slug": project_slug,
            **brief,
            "language_profiles": language_profiles,
            "repository_layout": args.repository_layout,
            "monorepo_packages": package_answers,
            "repository_default_branch": args.default_branch,
            "include_readme": not args.delete_readme,
            "dstack_template_channel": channel,
        },
        vcs_ref=render_vcs_ref,
        defaults=True,
        overwrite=False,
        quiet=args.quiet or args.json,
        unsafe=False,
    )

    if not answers.exists():
        message = "Copier completed without creating .copier-answers.yml"
        raise SystemExit(message)
    record_update_state(
        answers,
        source=recorded_update_source,
        commit=resolved_template_commit,
        channel=channel,
    )
    try:
        layout_render = render_package_configs(layout_preflight, destination)
    except ValueError as exc:
        raise SystemExit(f"Unable to render repository layout: {exc}") from exc
    recorded_vcs_ref = selected_ref

    git_initialized = False
    if not args.no_git_init:
        git_initialized = initialize_git(destination, args.default_branch, quiet=args.quiet or args.json)

    beads_is_available = bd_available(destination)
    beads_initialized = False
    beads_hooks = skipped_beads_hooks("post-setup was skipped")
    docs_validated = False
    post_setup_ran = False
    outstanding: list[str] = []
    tooling = skipped_tooling() if args.skip_post_setup else provision_tooling(destination)
    outstanding.extend(f"Tooling recovery: {command}" for command in tooling["recovery"])
    if not args.skip_post_setup:
        verify_scaffold(destination)
        if args.skip_beads:
            outstanding.append("Beads initialization and verification")
            beads_hooks = skipped_beads_hooks("skipped by --skip-beads")
        elif beads_is_available and own_git_repository(destination):
            beads_hooks = initialize_beads(destination, args, prefix=project_slug, quiet=args.quiet or args.json)
            beads_initialized = beads_hooks["status"] == "succeeded"
            if beads_hooks["recovery"]:
                outstanding.extend(f"Beads hook recovery: {command}" for command in beads_hooks["recovery"])
        elif beads_is_available:
            outstanding.append("Beads initialization requires a project-local Git repository")
            beads_hooks = skipped_beads_hooks("Beads initialization requires a project-local Git repository")
        else:
            outstanding.append("Beads initialization and verification")
            beads_hooks = unavailable_beads_hooks("bd is unavailable or its launcher cannot execute")
            outstanding.extend(f"Beads hook recovery: {command}" for command in beads_hooks["recovery"])
        validate_docs(destination, quiet=args.quiet or args.json)
        docs_validated = True
        verify_scaffold(destination)
        post_setup_ran = True
    else:
        outstanding.append("Post-setup scaffold and documentation validation")
        if not args.skip_beads:
            outstanding.append("Beads initialization and verification")

    result = {
        "project_name": project_name,
        "project_slug": project_slug,
        **brief,
        "language_profiles": language_profiles,
        "repository_layout": args.repository_layout,
        "monorepo_packages": package_answers,
        "layout_preflight": layout_preflight,
        "layout_render": layout_render,
        "destination": str(destination),
        "template_source": template_source,
        "template_source_kind": "bundled" if using_bundled_template else "override",
        "template_channel": channel,
        "update_source": recorded_update_source,
        "skill_version": skill_version,
        "vcs_ref": recorded_vcs_ref,
        "render_vcs_ref": render_vcs_ref,
        "resolved_template_commit": resolved_template_commit,
        "copier_answers": str(answers),
        "git_initialized": git_initialized,
        "post_setup_ran": post_setup_ran,
        "docs_validated": docs_validated,
        "beads_available": beads_is_available,
        "beads_initialized": beads_initialized,
        "beads_hooks": beads_hooks,
        "readme_created": (destination / "README.md").exists(),
        "tooling": tooling,
        "outstanding": outstanding,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Created dstack project: {project_name}")
        print(f"Destination: {destination}")
        print(f"Template: {template_source} ({recorded_vcs_ref or 'unversioned override'})")
        print(f"Future update source: {recorded_update_source}")
        print(f"Copier state: {answers}")
        if beads_initialized:
            print("Beads initialized and hooks verified. Next: run 'bd prime', then use /plan-features.")
        elif args.skip_beads:
            print("Beads initialization and verification remain outstanding because --skip-beads was supplied.")
        elif not beads_is_available:
            print("warning: bd is unavailable; Beads initialization and verification remain outstanding")
            print("Install Beads, then rerun guarded collaborative initialization before the first commit.")
        if docs_validated:
            print("Documentation scaffold validation passed.")
        print(f"Tooling provisioning: {tooling['status']}")
        for command in tooling["recovery"]:
            print(f"Tooling recovery: {command}")
        print(f"Beads hooks: {beads_hooks['status']}")
        for command in beads_hooks["recovery"]:
            print(f"Beads hook recovery: {command}")
        print("Commit the initial scaffold before applying Copier updates.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130) from None
