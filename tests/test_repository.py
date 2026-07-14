"""Repository, skill-package, Copier, and Skills CLI validation tests."""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from copier import run_copy

from tests.support import (
    commit_repository,
    initialize_git,
    merged_environment,
    run_command,
)


EXPECTED_SKILLS = {
    "audit-project",
    "dstack-core",
    "close-feature",
    "implement-feature",
    "migrate-workflow",
    "plan-features",
    "gh-pr-review",
    "setup-project",
    "start-feature",
    "update-project",
}

REQUIRED_SKILL_SUPPORT = (
    "skills/dstack-core/references/TRUST-AND-AUTHORITY.md",
    "skills/dstack-core/scripts/resolve-feature.py",
    "skills/gh-pr-review/scripts/review_state.py",
    "skills/migrate-workflow/references/MIGRATION.md",
    "skills/migrate-workflow/scripts/adopt-template.py",
    "skills/migrate-workflow/scripts/migrate-legacy-workflow.py",
    "skills/setup-project/copier.yml",
    "skills/setup-project/scripts/setup-project.py",
    "skills/setup-project/template/docs/src/features/_template/design.md",
    "skills/update-project/scripts/update-project.py",
)

REQUIRED_COPIER_QUESTIONS = (
    "project_name",
    "project_slug",
    "project_purpose",
    "project_users",
    "project_scope",
    "project_boundaries",
    "project_kind",
    "language_profiles",
    "repository_default_branch",
    "include_readme",
)

SETUP_BRIEF = {
    "project_purpose": 'Coordinate [reader](missing.md) 😀 devices with a literal \\ path, café text, and "quotes".',
    "project_users": 'Operators who own "reader" fleets [team].',
    "project_scope": "Provisioning, health checks, and `status` workflows.",
    "project_boundaries": "Firmware # updates and identity-provider <admin> remain external.",
    "project_kind": "service",
}
PUNCTUATED_PROJECT_NAME = 'A "quoted" \\ café 😀 [project]'

SETUP_BRIEF_ARGS = [
    "--purpose",
    SETUP_BRIEF["project_purpose"],
    "--users",
    SETUP_BRIEF["project_users"],
    "--scope",
    SETUP_BRIEF["project_scope"],
    "--boundaries",
    SETUP_BRIEF["project_boundaries"],
    "--project-kind",
    SETUP_BRIEF["project_kind"],
    "--language-profile",
    "other",
]

REQUIRED_TEMPLATE_FILES = (
    ".beads/formulas/feature-lifecycle.formula.toml",
    ".gitignore.jinja",
    "[[ _copier_conf.answers_file ]].jinja",
    "[% if include_readme %]README.md[% endif %].jinja",
    "AGENTS.md.jinja",
    ".config/rumdl.toml",
    "hk.pkl.jinja",
    "mise.toml.jinja",
    "docs/book.toml.jinja",
    "docs/src/SUMMARY.md.jinja",
    "docs/src/development/tooling.md.jinja",
    "docs/src/reference/tooling.md.jinja",
    "docs/src/features/_template/design.md",
    "docs/src/features/_template/index.md",
    "scripts/check-docs.py",
    "scripts/setup-tooling.py",
)

FORBIDDEN_NEW_PROJECT_TEMPLATE_FILES = (
    "MIGRATION.md",
    "scripts/bootstrap.py",
    "scripts/migrate-legacy-workflow.py",
)

REMOVED_CONTENT_FREE_DOCS = (
    "docs/src/index.md",
    "docs/src/architecture/index.md",
    "docs/src/operations/index.md",
    "docs/src/development/index.md",
    "docs/src/reference/index.md",
)

INITIAL_READER_MARKDOWN = {
    "SUMMARY.md",
    "development/feature-lifecycle.md",
    "development/tooling.md",
    "features/_template/design.md",
    "features/_template/index.md",
    "features/index.md",
    "introduction/documentation-conventions.md",
    "introduction/project-overview.md",
    "planned-features.md",
    "reference/tooling.md",
}

KIND_GUIDANCE = {
    "library": "compatibility",
    "cli": "exit behavior",
    "service": "observability",
    "application": "getting-started",
    "infrastructure": "inventory",
    "documentation": "publication",
    "other": "No documentation concern is presumed",
}

LEGACY_OR_GENERATED_FILENAMES = {
    "setup_project.py",
    "update_project.py",
    "adopt_template.py",
    "migrate_workflow.py",
    "validate_repository.py",
}

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def load_skill_manifest(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    assert match is not None, f"Invalid frontmatter: {skill_md}"
    manifest = yaml.safe_load(match.group(1))
    assert isinstance(manifest, dict), f"Frontmatter is not a mapping: {skill_md}"
    return manifest


def tracked_or_packaged_files(repository_root: Path) -> list[Path]:
    if (repository_root / ".git").exists():
        result = run_command(["git", "ls-files", "-z"], cwd=repository_root)
        return [
            repository_root / value
            for value in result.stdout.split("\0")
            if value and (repository_root / value).is_file()
        ]

    return [
        path
        for path in repository_root.rglob("*")
        if path.is_file()
        and not any(
            part in {".git", ".pytest_cache", ".ruff_cache", ".rumdl_cache", ".venv", "__pycache__"}
            for part in path.relative_to(repository_root).parts
        )
    ]


def setup_generated_project(
    source: Path,
    project: Path,
    *,
    kind: str = "service",
    name: str | None = None,
    entrypoint: str = "repository",
    include_readme: bool = True,
    brief: dict[str, str] | None = None,
    language_profiles: tuple[str, ...] = ("other",),
) -> dict[str, Any]:
    """Render a project while simulating an existing Skills CLI installation."""
    installed_skill = project / ".agents/skills/setup-project"
    installed_skill.mkdir(parents=True)
    (installed_skill / "SKILL.md").write_text(
        "---\nname: setup-project\ndescription: Test installation.\n---\n",
        encoding="utf-8",
    )
    (project / "skills-lock.json").write_text("{}\n", encoding="utf-8")
    setup = source / "skills/setup-project/scripts/setup-project.py"
    selected_brief = {**(brief or SETUP_BRIEF), "project_kind": kind}
    brief_args = [
        "--purpose",
        selected_brief["project_purpose"],
        "--users",
        selected_brief["project_users"],
        "--scope",
        selected_brief["project_scope"],
        "--boundaries",
        selected_brief["project_boundaries"],
        "--project-kind",
        selected_brief["project_kind"],
        *(value for profile in language_profiles for value in ("--language-profile", profile)),
    ]
    result = run_command(
        [
            "uv",
            "run",
            str(setup),
            *([name] if name else []),
            "--destination",
            str(project),
            *(["--template-source", str(source)] if entrypoint == "repository" else []),
            "--skip-post-setup",
            *([] if include_readme else ["--delete-readme"]),
            *brief_args,
            "--json",
        ],
        cwd=project,
    )
    return json.loads(result.stdout)


def configure_project_git(project: Path) -> None:
    run_command(["git", "config", "user.email", "test@example.com"], cwd=project)
    run_command(["git", "config", "user.name", "dstack Test"], cwd=project)
    run_command(["git", "config", "commit.gpgSign", "false"], cwd=project)
    run_command(["git", "config", "tag.gpgSign", "false"], cwd=project)


def write_logging_shims(bin_dir: Path, *names: str) -> Path:
    script = bin_dir / "profile-shim"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "name = Path(sys.argv[0]).name\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['DSTACK_SHIM_LOG']).open('a') as stream:\n"
        "    stream.write(name + ' ' + ' '.join(args) + '\\n')\n"
        "fail_check = os.environ.get('DSTACK_FAIL_CHECK') == '1'\n"
        "check_only = name == 'ruff' and '--fix' not in args and ('format' not in args or '--diff' in args)\n"
        "check_only = check_only or (name == 'biome' and '--write' not in args)\n"
        "check_only = check_only or (name == 'rustfmt' and '--check' in args)\n"
        "if fail_check and name in {'goimports', 'gofumpt'} and '-l' in args: print('needs-format')\n"
        "fail_tidy = os.environ.get('DSTACK_FAIL_GO_TIDY') == '1' and name == 'go' and '-diff' in args\n"
        "raise SystemExit(name == os.environ.get('DSTACK_FAIL_COMMAND') or fail_tidy or (fail_check and check_only))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    for name in names:
        (bin_dir / name).symlink_to(script)
    return script


def write_fake_mise(bin_dir: Path) -> Path:
    mise = bin_dir / "mise"
    mise.parent.mkdir(parents=True, exist_ok=True)
    mise.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "stage = 'hooks' if args and args[0] == 'x' else (args[0] if args else '')\n"
        "if log := os.environ.get('DSTACK_MISE_LOG'):\n"
        "    with Path(log).open('a') as stream:\n"
        "        stream.write(stage + '\\n')\n"
        "if os.environ.get('DSTACK_MISE_FAIL') == stage:\n"
        "    print(f'{stage} failed', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "if stage == 'lock':\n"
        "    (Path.cwd() / 'mise.lock').write_text('linux-x64\\nlinux-arm64\\nmacos-x64\\nmacos-arm64\\n')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    mise.chmod(0o755)
    return mise


def write_fake_bd(bin_dir: Path, log_path: Path) -> Path:
    """Create a deterministic embedded-mode-compatible Beads test double."""
    bd = bin_dir / "bd"
    bd.parent.mkdir(parents=True, exist_ok=True)
    bd.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "log = Path(os.environ['DSTACK_BD_LOG'])\n"
        "with log.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(' '.join(sys.argv[1:]) + '\\n')\n"
        "args = sys.argv[1:]\n"
        "if args == ['--version']:\n"
        "    print('bd fake-1.0.0')\n"
        "elif args[:2] == ['info', '--json']:\n"
        "    print(json.dumps({'database_path': '.beads/embeddeddolt', 'issue_count': 3, 'mode': 'direct'}))\n"
        "elif args and args[0] == 'init':\n"
        "    beads = Path.cwd() / '.beads'\n"
        "    beads.mkdir(exist_ok=True)\n"
        "    (beads / 'metadata.json').write_text('{}\\n', encoding='utf-8')\n"
        "    (beads / 'config.yaml').write_text('mode: fake\\n', encoding='utf-8')\n"
        "elif args and args[0] == 'list' and '--json' in args:\n"
        "    print(os.environ.get('DSTACK_BD_FEATURES', '[]'))\n"
        "elif args and args[0] == 'ready' and '--json' in args:\n"
        "    if '--type' in args:\n"
        "        features = json.loads(os.environ.get('DSTACK_BD_FEATURES', '[]'))\n"
        "        print(json.dumps([item for item in features if item.get('ready', True)]))\n"
        "    else:\n"
        "        print('[]')\n"
        "elif args[:3] == ['formula', 'show', 'feature-lifecycle']:\n"
        "    print(json.dumps({'formula': 'feature-lifecycle'}))\n"
        "else:\n"
        "    print('unsupported fake bd command: ' + ' '.join(args), file=sys.stderr)\n"
        "    raise SystemExit(64)\n",
        encoding="utf-8",
    )
    bd.chmod(0o755)
    return bd


def test_skill_set_and_frontmatter(repository_root: Path) -> None:
    skill_paths = sorted((repository_root / "skills").glob("*/SKILL.md"))
    loaded = [load_skill_manifest(skill_md) for skill_md in skill_paths]
    names = [str(manifest["name"]) for manifest in loaded]
    project = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]

    assert len(names) == len(EXPECTED_SKILLS)
    assert len(names) == len(set(names)), f"Duplicate skill names: {names}"
    assert set(names) == EXPECTED_SKILLS
    assert all(manifest.get("description") for manifest in loaded)
    for path, manifest in zip(skill_paths, loaded, strict=True):
        metadata = manifest.get("metadata")
        assert isinstance(metadata, dict), f"Missing metadata mapping: {path}"
        assert metadata.get("version") == version, f"Version mismatch: {path}"
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in metadata.items())
        allowed_tools = manifest.get("allowed-tools")
        assert isinstance(allowed_tools, str), f"Missing allowed-tools: {path}"
        assert allowed_tools.split(), f"Missing allowed-tools: {path}"
        assert len(allowed_tools.split()) == len(set(allowed_tools.split())), f"Duplicate allowed tool: {path}"

    tracked_text = "\n".join(
        candidate.read_text(encoding="utf-8", errors="ignore")
        for candidate in tracked_or_packaged_files(repository_root)
    )
    assert "DSTACK" + "_VERSION" not in tracked_text


def test_reviewed_skill_contracts_are_explicit(repository_root: Path) -> None:
    def skill(name: str) -> str:
        return (repository_root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")

    migration = skill("migrate-workflow")
    migration_reference = (repository_root / "skills/migrate-workflow/references/MIGRATION.md").read_text(
        encoding="utf-8"
    )
    assert len(migration.splitlines()) < 200
    assert "references/MIGRATION.md" in migration
    for heading in (
        "## Baseline interpretation",
        "## Template source and revision",
        "## Task parser coverage",
        "## Dependency cycles",
        "## Beads import and recovery",
        "## Verification and completion",
    ):
        assert heading in migration_reference
    assert "baseline --write" in migration
    assert 'git diff --cached --quiet || git commit -m "chore: record pre-migration baseline"' in migration
    assert 'git diff --cached --quiet || git commit -m "chore: record workflow migration plan"' in migration
    assert migration.count('test -z "$(git status --porcelain)"') >= 3
    assert "Do not run `prepare` while scan output or decisions are uncommitted" in migration
    assert "bd init --stealth" in migration
    assert 'git commit -m "chore: initialize Beads workflow state"' in migration
    assert "Design Question Loop" in migration
    assert "migration:reconciliation" in migration
    assert "Only migration may retain" in migration
    assert "git add migration docs/src/planned-features.md docs/src/features" in migration
    assert "Gate 5 carries those decisions into Beads" in migration

    pr_review = skill("gh-pr-review")
    assert "# Purpose" not in pr_review
    assert pr_review.count("uv run <skill-dir>/scripts/fetch_comments.py") >= 3
    assert "every fetched item" in pr_review.casefold()
    assert "Context only" in pr_review
    assert "Regardless of whether this cycle created a commit" in pr_review
    assert "gh pr checks --watch --interval 10" in pr_review
    assert "intermediate workflow pause" in pr_review
    assert "successful copilot review request" in " ".join(pr_review.casefold().split())
    assert "scripts/review_state.py" in pr_review

    setup = skill("setup-project")
    assert "command -v bd" in setup
    assert "Do not run `bd prime` when `bd` is unavailable" in setup
    assert "Run /update-project instead?" in setup
    assert "only when the user agrees" in setup
    assert "has no overwrite mode" in setup
    assert "one question at a time" in setup
    assert all(flag in setup for flag in ("--purpose", "--users", "--scope", "--boundaries", "--project-kind"))
    setup_script = (repository_root / "skills/setup-project/scripts/setup-project.py").read_text(encoding="utf-8")
    assert "def initialize_beads(" in setup_script
    assert "def verify_scaffold(" in setup_script
    assert 'parser.add_argument("--overwrite"' not in setup_script
    assert 'parser.add_argument("--skip-bootstrap"' not in setup_script
    assert "overwrite=False" in setup_script
    assert "unsafe=False" in setup_script
    assert "Beads initialization and verification remain outstanding" in setup_script
    assert 'default="stealth"' in setup_script
    assert "git commit -F <file>" in setup
    assert "git merge --ff-only" in setup
    for agents_path in (
        repository_root / "AGENTS.md",
        repository_root / "skills/setup-project/template/AGENTS.md.jinja",
    ):
        agents = agents_path.read_text(encoding="utf-8")
        normalized_agents = " ".join(agents.split())
        assert "git commit -F <file>" in agents
        assert "multiple `-m` flags" in agents
        assert "escaped `\\n`" in agents
        assert "git merge --ff-only" in agents
        assert "never create a merge commit" in agents
        assert "Initial reviewers always use fresh context" in agents
        assert "one context builder plus four reviewers" in normalized_agents
        assert "one context builder plus two reviewers" in normalized_agents
        assert "resume only the original reviewers whose domains changed" in normalized_agents
        assert "original packet when one exists" in normalized_agents
    for relative in FORBIDDEN_NEW_PROJECT_TEMPLATE_FILES:
        assert not (repository_root / "skills/setup-project/template" / relative).exists()

    planning = skill("plan-features")
    assert "every native implementation task is executable without another" in planning
    assert "create no implementation tasks" in planning
    assert "only imported migration work" in planning

    implementation = skill("implement-feature")
    normalized_implementation = " ".join(implementation.split())
    assert "git rev-parse HEAD" in implementation
    assert "resolve-feature.py --next" not in implementation
    assert "feat/<num>-<slug>" in implementation
    assert "dstack.activeFeature" in implementation
    assert "git config --unset-all dstack.activeFeature" in implementation
    assert "immediately return to this selection step" in normalized_implementation
    assert "remaining open child is blocked by missing user decisions" in normalized_implementation
    assert "exactly one initial reviewer with `context: fresh`" in normalized_implementation
    assert "Resume the same reviewer" in implementation
    assert "A separate context builder is unnecessary" in implementation
    assert "Use a fresh replacement only if the original" in normalized_implementation
    assert "distinct uncovered risk or an explicit user request" in normalized_implementation
    assert "specific no-commit justification" in implementation
    assert "<implementation-epic-id>" not in implementation

    closeout = skill("close-feature")
    normalized_closeout = " ".join(closeout.split())
    assert "resolve-feature.py --next" not in closeout
    assert "feat/<num>-<slug>" in closeout
    assert "do not reuse pre-fix results" in " ".join(closeout.casefold().split())
    assert "scripts/check-docs.py" in closeout
    assert "git -C <base-worktree> merge --ff-only" in closeout
    assert "git -C <base-worktree> status --porcelain" in closeout
    assert "never fall back to a merge commit" in closeout
    assert "Launch exactly one fresh, read-only context builder" in closeout
    assert "launch exactly two reviewers with `context: fresh`" in closeout
    assert "Resume only the reviewer whose domain changed" in normalized_closeout
    assert "no findings, recommendations, or verdict" in normalized_closeout
    assert "reads additional source only when needed" in normalized_closeout
    assert "Refresh the shared packet only after broad" in normalized_closeout
    assert "distinct uncovered risk or an explicit user request" in normalized_closeout
    assert "AGENTS.md" in closeout

    audit = skill("audit-project")
    assert "Do not report a correction as verified from a pre-fix result" in audit

    start = skill("start-feature")
    assert "git show-ref --verify --quiet refs/heads/feat/<num>-<slug>" in start
    assert "Branch exists but has no worktree" in start
    assert "<implementation-epic-id>" not in start
    assert "resolve-feature.py" in start
    assert "canonical" in start.casefold()
    assert "git -C <worktree-path> config dstack.activeFeature" in start
    assert "Launch exactly one fresh, read-only context builder" in start
    assert "Launch exactly four role reviewers with `context: fresh`" in start
    assert "resume only its original reviewer" in start
    normalized_start = " ".join(start.split())
    assert "must not contain findings, recommendations, or a verdict" in normalized_start
    assert "reads additional source only when needed" in normalized_start
    assert "Refresh the shared packet only after broad" in normalized_start
    assert "distinct uncovered risk or the user explicitly requires one" in normalized_start

    for lifecycle_path in (
        repository_root / "docs/src/development/feature-lifecycle.md",
        repository_root / "skills/setup-project/template/docs/src/development/feature-lifecycle.md.jinja",
    ):
        lifecycle = " ".join(lifecycle_path.read_text(encoding="utf-8").split())
        assert "no findings, recommendations, or verdict" in lifecycle
        assert "read extra source" in lifecycle
        assert "confidence reviewers" in lifecycle
        assert "Refresh a shared packet only after broad" in lifecycle
        assert "original is unavailable or" in lifecycle

    update = skill("update-project")
    assert "Run /migrate-workflow now?" in update
    assert "--preflight --json" in update
    assert "path-accounting ledger" in update
    assert "every changed path" in update.casefold()
    normalized_update = " ".join(update.split())
    assert "readiness to resume feature work, which must be false while migration is required" in normalized_update
    assert "conflicts or degraded tooling remain" in normalized_update
    assert "the lock is stale or missing" in normalized_update
    assert "a changed path is unclassified" in normalized_update

    for name in ("audit-project", "close-feature", "implement-feature", "gh-pr-review"):
        description = str(load_skill_manifest(repository_root / "skills" / name / "SKILL.md")["description"])
        assert "Use when" in description, f"Missing invocation trigger in {name}: {description}"

    trust_skills = (
        "audit-project",
        "close-feature",
        "gh-pr-review",
        "migrate-workflow",
        "setup-project",
        "update-project",
    )
    for name in trust_skills:
        content = skill(name)
        assert "Shared trust contract" in content, name
        assert "../dstack-core/references/TRUST-AND-AUTHORITY.md" in content, name


@pytest.mark.parametrize("relative_path", REQUIRED_SKILL_SUPPORT)
def test_required_skill_support_exists(repository_root: Path, relative_path: str) -> None:
    assert (repository_root / relative_path).is_file(), relative_path


def test_security_sensitive_skills_require_shared_contract(repository_root: Path) -> None:
    contract = repository_root / "skills/dstack-core/references/TRUST-AND-AUTHORITY.md"
    assert contract.is_file()
    names = ("audit-project", "close-feature", "gh-pr-review", "migrate-workflow", "setup-project", "update-project")
    for name in names:
        text = (repository_root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "../dstack-core/references/TRUST-AND-AUTHORITY.md" in text
        assert "normative for this workflow" in text


def test_repository_contains_no_stale_tracked_files(repository_root: Path) -> None:
    stale = []
    for path in tracked_or_packaged_files(repository_root):
        relative = path.relative_to(repository_root)
        if (
            path.name in LEGACY_OR_GENERATED_FILENAMES
            or path.suffix in {".pyc", ".pyo"}
            or any(
                part in {"__pycache__", ".pytest_cache", ".ruff_cache", ".rumdl_cache", ".venv"}
                for part in relative.parts
            )
        ):
            stale.append(relative.as_posix())
    assert stale == []


def test_hk_rumdl_avoids_nonstandard_diff_headers(repository_root: Path) -> None:
    config = (repository_root / "hk.pkl").read_text(encoding="utf-8")
    assert 'check = "rumdl check --config .config/rumdl.toml {{ files }}"' in config
    assert 'check_diff = "rumdl check --config .config/rumdl.toml --diff {{ files }}"' not in config


def test_reader_docs_publish_the_generated_tooling_contract(repository_root: Path) -> None:
    docs = repository_root / "docs/src"
    architecture = (docs / "architecture/index.md").read_text(encoding="utf-8")
    operations = (docs / "operations/index.md").read_text(encoding="utf-8")
    development = (docs / "development/index.md").read_text(encoding="utf-8")
    reference = (docs / "reference/index.md").read_text(encoding="utf-8")
    mise_template = (repository_root / "skills/setup-project/template/mise.toml.jinja").read_text(encoding="utf-8")
    mise = tomllib.loads(re.sub(r"\[% if .*?%\].*?\[% endif %\]\n?", "", mise_template, flags=re.DOTALL))
    tooling_module = load_tooling_module(repository_root)

    assert "ignores user-global mise configuration" in architecture
    assert "An update with conflicts never executes newly rendered project code" in architecture
    assert "mise lock --yes --platform linux-x64,linux-arm64,macos-x64,macos-arm64" in operations
    assert "python3 scripts/setup-tooling.py --json" in operations
    assert 'stash = "git"' in development
    assert "intentionally omits dstack's `release` task" in development

    generated_commands = development.split("## Generated project command contract", 1)[1]
    assert set(re.findall(r"^mise run ([\w:]+)", generated_commands, flags=re.MULTILINE)) == set(mise["tasks"])
    contributor_guide = (
        repository_root / "skills/setup-project/template/docs/src/development/tooling.md.jinja"
    ).read_text(encoding="utf-8")
    assert set(re.findall(r"^mise run ([\w:]+)", contributor_guide, flags=re.MULTILINE)) == set(mise["tasks"])

    tooling_reference = reference.split("## Generated tooling files", 1)[1].split("## Tooling result schema", 1)[0]
    files_table, tools_table = tooling_reference.split("### Universal tools", 1)
    assert set(re.findall(r"^\| `([^`]+)`", files_table, flags=re.MULTILINE)) == {
        "mise.toml",
        "mise.lock",
        "hk.pkl",
        ".config/rumdl.toml",
        "scripts/setup-tooling.py",
        "docs/src/development/tooling.md",
        "docs/src/reference/tooling.md",
    }
    assert dict(re.findall(r"^\| `([^`]+)`\s+\| `([^`]+)`", tools_table, flags=re.MULTILINE)) == mise["tools"]

    schema_match = re.search(r"## Tooling result schema.*?```json\n(.*?)\n```", reference, flags=re.DOTALL)
    assert schema_match is not None
    schema = json.loads(schema_match.group(1))
    assert set(schema) == {"status", "mise", "lock", "install", "hooks", "platforms", "recovery"}
    assert set(schema["lock"]) == {"status", "path", "error"}
    assert set(schema["install"]) == {"status", "error"}
    assert set(schema["hooks"]) == {"status", "error"}
    assert schema["platforms"] == list(tooling_module.PLATFORMS)
    assert set(schema["status"].split(" | ")) == {"succeeded", "degraded", "skipped"}
    assert set(schema["mise"].split(" | ")) == {"available", "unavailable", "skipped"}
    for stage in ("lock", "install"):
        assert set(schema[stage]["status"].split(" | ")) == {"succeeded", "failed", "skipped"}
    assert set(schema["hooks"]["status"].split(" | ")) == {
        "succeeded",
        "failed",
        "skipped",
        "skipped-no-git",
    }
    normalized_reference = " ".join(reference.split())
    assert "ready_to_resume_feature_work" in normalized_reference
    assert "independently verified nonempty `mise.lock`" in normalized_reference


def test_copier_entry_points_are_consistent(repository_root: Path) -> None:
    root_config = yaml.safe_load((repository_root / "copier.yml").read_text(encoding="utf-8"))
    bundled_config = yaml.safe_load((repository_root / "skills/setup-project/copier.yml").read_text(encoding="utf-8"))

    assert root_config["_subdirectory"] == "skills/setup-project/template"
    assert bundled_config["_subdirectory"] == "template"
    assert "project_mode" not in root_config
    assert "project_mode" not in bundled_config
    for question in REQUIRED_COPIER_QUESTIONS:
        assert question in root_config
        assert question in bundled_config
        assert root_config[question] == bundled_config[question]


def load_setup_module(repository_root: Path) -> Any:
    path = repository_root / "skills/setup-project/scripts/setup-project.py"
    spec = importlib.util.spec_from_file_location("dstack_setup_project", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tooling_module(repository_root: Path) -> Any:
    path = repository_root / "skills/setup-project/template/scripts/setup-tooling.py"
    spec = importlib.util.spec_from_file_location("dstack_setup_tooling", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_update_module(repository_root: Path) -> Any:
    path = repository_root / "skills/update-project/scripts/update-project.py"
    spec = importlib.util.spec_from_file_location("dstack_update_project", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_project_requires_and_validates_the_project_brief(repository_root: Path) -> None:
    module = load_setup_module(repository_root)

    with pytest.raises(SystemExit, match=r"requires --purpose, --users, --scope, --boundaries, --project-kind"):
        module.project_brief(module.parse_args([]))

    for kind in module.PROJECT_KINDS:
        values = [kind if value == SETUP_BRIEF["project_kind"] else value for value in SETUP_BRIEF_ARGS]
        assert module.project_brief(module.parse_args(values)) == SETUP_BRIEF | {"project_kind": kind}

    for invalid, message in (
        ("   ", "must not be blank"),
        ("bad\nvalue", "must be a single line"),
        ("\nleading", "must be a single line"),
        ("trailing\r", "must be a single line"),
        ("\rwrapped\n", "must be a single line"),
        ("bad\x00value", "must be a single line"),
    ):
        invalid_args = module.parse_args(
            [invalid if value == SETUP_BRIEF["project_purpose"] else value for value in SETUP_BRIEF_ARGS]
        )
        with pytest.raises(SystemExit, match=message):
            module.project_brief(invalid_args)


@pytest.mark.parametrize(
    ("failure", "has_git", "expected"),
    [
        (None, True, ("succeeded", "succeeded", "succeeded", "succeeded")),
        ("missing", True, ("degraded", "skipped", "skipped", "skipped")),
        ("lock", True, ("degraded", "failed", "skipped", "skipped")),
        ("install", True, ("degraded", "succeeded", "failed", "skipped")),
        ("hooks", True, ("degraded", "succeeded", "succeeded", "failed")),
        (None, False, ("degraded", "succeeded", "succeeded", "skipped-no-git")),
    ],
)
def test_tooling_provisioner_reports_independent_stage_outcomes(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
    has_git: bool,
    expected: tuple[str, str, str, str],
) -> None:
    module = load_tooling_module(repository_root)
    project = tmp_path / "project"
    project.mkdir()
    if has_git:
        (project / ".git").mkdir()
    commands: list[list[str]] = []

    monkeypatch.setattr(module.shutil, "which", lambda _command: None if failure == "missing" else "/bin/mise")

    def fake_run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd == project
        commands.append(command)
        stage_name = "hooks" if command[1] == "x" else command[1]
        if stage_name == "lock" and failure != "lock":
            (project / "mise.lock").write_text("resolved\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, int(failure == stage_name), "", f"{stage_name} failed")

    monkeypatch.setattr(module, "run", fake_run)
    result = module.provision(project)

    assert (
        result["status"],
        result["lock"]["status"],
        result["install"]["status"],
        result["hooks"]["status"],
    ) == expected
    assert result["platforms"] == ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"]
    assert all(isinstance(command, str) and command for command in result["recovery"])
    if failure is None and has_git:
        assert commands == [module.LOCK_COMMAND, module.INSTALL_COMMAND, module.HOOK_COMMAND]
        assert result["recovery"] == []
    if failure == "lock":
        assert result["lock"]["error"] == "lock failed"
    if failure == "install":
        assert result["install"]["error"] == "install failed"
    if failure == "hooks":
        assert result["hooks"]["error"] == "hooks failed"


def test_tooling_provisioner_isolates_project_lock_from_global_mise_tools(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_tooling_module(repository_root)
    captured: dict[str, Any] = {}

    def fake_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.run(["mise", "install"], tmp_path)

    assert captured["env"]["MISE_GLOBAL_CONFIG_FILE"] == os.devnull


def test_tooling_provisioner_converts_launch_errors_to_structured_failure(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_tooling_module(repository_root)
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/broken/mise")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("broken")))

    result = module.provision(tmp_path)

    assert result["status"] == "degraded"
    assert result["lock"] == {"status": "failed", "path": "mise.lock", "error": "broken"}
    assert result["recovery"][-1] == "python3 scripts/setup-tooling.py --json"


def test_setup_project_rejects_invalid_tooling_success(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_setup_module(repository_root)
    valid_shape = {
        "status": "succeeded",
        "mise": "available",
        "lock": {"status": "succeeded", "path": "mise.lock", "error": None},
        "install": {"status": "succeeded", "error": None},
        "hooks": {"status": "succeeded", "error": None},
        "platforms": module.TOOLING_PLATFORMS,
        "recovery": [],
    }

    for payload in ({"status": "succeeded"}, valid_shape):
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        monkeypatch.setattr(module.subprocess, "run", lambda *_args, _completed=completed, **_kwargs: _completed)
        result = module.provision_tooling(tmp_path)
        assert result["status"] == "degraded"
        assert result["lock"]["status"] == "failed"
        assert result["recovery"] == [module.TOOLING_RERUN]


def test_language_profile_selection_is_canonical_and_strict(repository_root: Path, tmp_path: Path) -> None:
    setup = load_setup_module(repository_root)
    update = load_update_module(repository_root)

    assert setup.canonical_language_profiles(["go", "python"]) == ["python", "go"]
    for invalid in ([], ["python", "python"], ["python", "other"], ["unknown"]):
        with pytest.raises(SystemExit):
            setup.canonical_language_profiles(invalid)

    for manifest in update.PROFILE_MANIFESTS:
        (tmp_path / manifest).touch()
    assert update.detected_language_profiles(tmp_path) == list(update.LANGUAGE_PROFILES[:-1])
    assert update.updated_language_profiles(["other"], ["other"], []) == ["other"]
    assert update.updated_language_profiles(["other"], ["typescript", "python"], []) == ["python", "typescript"]
    assert update.updated_language_profiles(["python", "go"], ["python"], ["rust"]) == ["python", "go"]
    assert update.updated_language_profiles(["python"], ["other"], ["python"]) == ["other"]
    with pytest.raises(SystemExit, match="added and removed"):
        update.updated_language_profiles(["python"], ["python"], ["python"])
    with pytest.raises(SystemExit, match="must not be empty"):
        update.updated_language_profiles(["python"], [], ["python"])


def test_language_profile_matrix_renders_both_entrypoints(repository_root: Path, tmp_path: Path) -> None:
    recognized = ("python", "typescript", "rust", "go", "elixir", "nix")
    selections = [
        list(selection)
        for size in range(1, len(recognized) + 1)
        for selection in itertools.combinations(recognized, size)
    ] + [["other"]]
    ignores = {
        "python": ".venv/",
        "typescript": "node_modules/",
        "rust": "target/",
        "go": "coverage.out",
        "elixir": "_build/",
        "nix": ".direnv/",
    }
    data = {
        "project_name": "Profile Matrix",
        "project_slug": "profile-matrix",
        **SETUP_BRIEF,
        "repository_default_branch": "main",
        "include_readme": True,
    }

    root_source = tmp_path / "root-source"
    (root_source / "skills/setup-project").mkdir(parents=True)
    shutil.copy2(repository_root / "copier.yml", root_source / "copier.yml")
    shutil.copytree(
        repository_root / "skills/setup-project/template",
        root_source / "skills/setup-project/template",
    )
    bundled_source = tmp_path / "bundled-source"
    shutil.copytree(repository_root / "skills/setup-project", bundled_source)

    for entrypoint, source in (("repository", root_source), ("bundled", bundled_source)):
        for index, profiles in enumerate(selections):
            project = tmp_path / f"{entrypoint}-{index}"
            run_copy(
                str(source),
                project,
                data=data | {"language_profiles": profiles},
                defaults=True,
                quiet=True,
                unsafe=False,
            )
            answers = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))
            assert answers["language_profiles"] == profiles
            assert set(tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))["tasks"]) == {
                "check",
                "fix",
                "docs:check",
                "docs:build",
                "docs:serve",
            }
            assert (project / "hk.pkl").is_file()
            rendered_ignores = (project / ".gitignore").read_text(encoding="utf-8")
            for profile, marker in ignores.items():
                assert (marker in rendered_ignores) == (profile in profiles)
            for forbidden in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "mix.exs", "flake.nix"):
                assert not (project / forbidden).exists()
            shutil.rmtree(project)

    for source_index, source in enumerate((root_source, bundled_source)):
        invalid_values = (
            [],
            ["python", "python"],
            ["unknown"],
            ["python", "other"],
            {"python": True},
            ["go", "python"],
        )
        for invalid_index, invalid in enumerate(invalid_values):
            with pytest.raises((ValueError, ZeroDivisionError)):
                run_copy(
                    str(source),
                    tmp_path / f"invalid-{source_index}-{invalid_index}",
                    data=data | {"language_profiles": invalid},
                    defaults=True,
                    quiet=True,
                    unsafe=False,
                )

    with pytest.raises(SystemExit):
        load_setup_module(repository_root).canonical_language_profiles([])


@pytest.mark.integration
def test_python_profile_renders_exact_contract(tagged_template_source: Path, tmp_path: Path) -> None:
    project = tmp_path / "python-profile"
    payload = setup_generated_project(tagged_template_source, project, language_profiles=("python",))
    mise = tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))
    hk = (project / "hk.pkl").read_text(encoding="utf-8")
    development = (project / "docs/src/development/tooling.md").read_text(encoding="utf-8")
    reference = (project / "docs/src/reference/tooling.md").read_text(encoding="utf-8")

    assert payload["language_profiles"] == ["python"]
    assert mise["tools"]["ruff"] == "latest"
    assert mise["tools"]["ty"] == "latest"
    assert "aube" not in mise["tools"]
    assert "biome" not in mise["tools"]
    for command in (
        "ruff check --force-exclude {{ files }}",
        "ruff check --force-exclude --fix {{ files }}",
        "ruff format --quiet --force-exclude --diff {{ files }}",
        "ruff format --quiet --force-exclude {{ files }}",
        "ty check {{ files }}",
        "uv run pytest",
    ):
        assert command in hk
    assert hk.index('["ruff"]') < hk.index('["ruff-format"]') < hk.index('["ty"]')
    assert hk.index('["pytest"]') > hk.index('["check"]')
    assert "Pytest must be declared by the project" in " ".join(development.split())
    assert "Recorded language profiles: `python`" in reference
    assert not (project / "pyproject.toml").exists()
    run_command(["pkl", "eval", "hk.pkl"], cwd=project)
    run_command(["uv", "run", "scripts/check-docs.py"], cwd=project)

    bin_dir = tmp_path / "python-bin"
    log = tmp_path / "python.log"
    write_logging_shims(bin_dir, "ruff", "ty", "uv")
    environment = merged_environment(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", DSTACK_SHIM_LOG=str(log))
    (project / "scripts/check-docs.py").unlink()
    (project / "scripts/setup-tooling.py").unlink()
    run_command(["hk", "check", "-a", "-S", "ruff", "-S", "ruff-format", "-S", "ty"], cwd=project, env=environment)
    assert not log.exists()

    source = project / "example.py"
    source.write_text("value=1\n", encoding="utf-8")
    tests = project / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text("def test_example(): assert True\n", encoding="utf-8")
    original = source.read_bytes()

    run_command(["hk", "check", "-a", "-S", "ruff", "-S", "ruff-format", "-S", "ty"], cwd=project, env=environment)
    check_log = log.read_text(encoding="utf-8")
    assert "ruff check --force-exclude" in check_log
    assert "ruff format --quiet --force-exclude --diff" in check_log
    assert "ty check" in check_log
    assert source.read_bytes() == original

    log.write_text("", encoding="utf-8")
    fix_environment = environment | {"DSTACK_FAIL_CHECK": "1"}
    run_command(
        ["hk", "fix", "-a", "-f", "-S", "ruff", "-S", "ruff-format", "-S", "ty"],
        cwd=project,
        env=fix_environment,
    )
    fix_log = log.read_text(encoding="utf-8")
    assert "ruff check --force-exclude --fix" in fix_log
    assert "ruff format --quiet --force-exclude" in fix_log

    log.write_text("", encoding="utf-8")
    run_command(["hk", "check", "-a", "-S", "pytest"], cwd=project, env=environment)
    assert log.read_text(encoding="utf-8") == ""
    (project / "pyproject.toml").write_text("[project]\nname='example'\nversion='0.1.0'\n", encoding="utf-8")
    failed_environment = environment | {"DSTACK_FAIL_COMMAND": "uv"}
    failure = run_command(["hk", "check", "-a", "-S", "pytest"], cwd=project, env=failed_environment, expected=1)
    assert "requires project-owned pytest" in failure.stderr
    log.write_text("", encoding="utf-8")
    run_command(["hk", "check", "-a", "-S", "pytest"], cwd=project, env=environment)
    assert "uv run python -c import pytest" in log.read_text(encoding="utf-8")
    assert "pytest" not in run_command(["hk", "run", "pre-commit", "-a", "-P"], cwd=project).stdout
    assert "pytest" not in run_command(["hk", "fix", "-a", "-P"], cwd=project).stdout


@pytest.mark.integration
def test_typescript_profile_renders_exact_contract(tagged_template_source: Path, tmp_path: Path) -> None:
    project = tmp_path / "typescript-profile"
    payload = setup_generated_project(tagged_template_source, project, language_profiles=("typescript",))
    mise = tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))
    hk = (project / "hk.pkl").read_text(encoding="utf-8")
    development = (project / "docs/src/development/tooling.md").read_text(encoding="utf-8")
    reference = (project / "docs/src/reference/tooling.md").read_text(encoding="utf-8")

    assert payload["language_profiles"] == ["typescript"]
    assert mise["tools"]["node"] == "lts"
    assert mise["tools"]["aube"] == "latest"
    assert mise["tools"]["biome"] == "latest"
    assert list(mise["tools"]).count("node") == 1
    assert "ruff" not in mise["tools"]
    for command in (
        "biome check --no-errors-on-unmatched {{ files }}",
        "biome check --write --no-errors-on-unmatched {{ files }}",
        "aube exec vitest --version",
        "aube exec vitest run",
    ):
        assert command in hk
    assert hk.index('["vitest"]') > hk.index('["check"]')
    assert "Vitest must be declared by the project" in " ".join(development.split())
    assert "Recorded language profiles: `typescript`" in reference
    assert not (project / "package.json").exists()
    run_command(["pkl", "eval", "hk.pkl"], cwd=project)
    run_command(["uv", "run", "scripts/check-docs.py"], cwd=project)

    bin_dir = tmp_path / "typescript-bin"
    log = tmp_path / "typescript.log"
    write_logging_shims(bin_dir, "biome", "aube")
    environment = merged_environment(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", DSTACK_SHIM_LOG=str(log))
    run_command(["hk", "check", "-a", "-S", "biome"], cwd=project, env=environment)
    assert not log.exists()

    source = project / "example.ts"
    source.write_text("const value=1\n", encoding="utf-8")
    test_file = project / "example.test.ts"
    test_file.write_text("test('example', () => {})\n", encoding="utf-8")
    original = source.read_bytes()

    run_command(["hk", "check", "-a", "-S", "biome"], cwd=project, env=environment)
    assert "biome check --no-errors-on-unmatched" in log.read_text(encoding="utf-8")
    assert source.read_bytes() == original
    log.write_text("", encoding="utf-8")
    fix_environment = environment | {"DSTACK_FAIL_CHECK": "1"}
    run_command(["hk", "fix", "-a", "-f", "-S", "biome"], cwd=project, env=fix_environment)
    assert "biome check --write --no-errors-on-unmatched" in log.read_text(encoding="utf-8")

    log.write_text("", encoding="utf-8")
    run_command(["hk", "check", "-a", "-S", "vitest"], cwd=project, env=environment)
    assert log.read_text(encoding="utf-8") == ""
    (project / "package.json").write_text('{"name":"example","devDependencies":{"vitest":"1"}}\n', encoding="utf-8")
    failed_environment = environment | {"DSTACK_FAIL_COMMAND": "aube"}
    failure = run_command(["hk", "check", "-a", "-S", "vitest"], cwd=project, env=failed_environment, expected=1)
    assert "requires project-owned Vitest" in failure.stderr
    log.write_text("", encoding="utf-8")
    run_command(["hk", "check", "-a", "-S", "vitest"], cwd=project, env=environment)
    vitest_log = log.read_text(encoding="utf-8")
    assert "aube exec vitest --version" in vitest_log
    assert "aube exec vitest run" in vitest_log
    assert "vitest" not in run_command(["hk", "run", "pre-commit", "-a", "-P"], cwd=project).stdout
    assert "vitest" not in run_command(["hk", "fix", "-a", "-P"], cwd=project).stdout


@pytest.mark.integration
def test_rust_profile_renders_exact_contract(tagged_template_source: Path, tmp_path: Path) -> None:
    project = tmp_path / "rust-profile"
    payload = setup_generated_project(tagged_template_source, project, language_profiles=("rust",))
    mise = tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))
    hk = (project / "hk.pkl").read_text(encoding="utf-8")
    development = (project / "docs/src/development/tooling.md").read_text(encoding="utf-8")
    reference = (project / "docs/src/reference/tooling.md").read_text(encoding="utf-8")

    assert payload["language_profiles"] == ["rust"]
    assert mise["tools"]["rust"] == "latest"
    assert "go" not in mise["tools"]
    for command in (
        "rustfmt --check --edition 2024 {{ files }}",
        "rustfmt --edition 2024 {{ files }}",
        "cargo clippy --all-targets --all-features -- -D warnings",
        "cargo test --all-targets --all-features",
    ):
        assert command in hk
    assert "Root `Cargo.toml` enables" in development
    assert "Recorded language profiles: `rust`" in reference
    assert "target/" in (project / ".gitignore").read_text(encoding="utf-8")
    assert not (project / "Cargo.toml").exists()
    run_command(["pkl", "eval", "hk.pkl"], cwd=project)
    run_command(["uv", "run", "scripts/check-docs.py"], cwd=project)

    bin_dir = tmp_path / "rust-bin"
    log = tmp_path / "rust.log"
    write_logging_shims(bin_dir, "rustfmt", "cargo")
    environment = merged_environment(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", DSTACK_SHIM_LOG=str(log))
    run_command(["hk", "check", "-a", "-S", "rustfmt"], cwd=project, env=environment)
    assert not log.exists()

    source = project / "main.rs"
    source.write_text("fn main() {}\n", encoding="utf-8")
    original = source.read_bytes()
    run_command(["hk", "check", "-a", "-S", "rustfmt"], cwd=project, env=environment)
    assert "rustfmt --check --edition 2024" in log.read_text(encoding="utf-8")
    assert source.read_bytes() == original
    log.write_text("", encoding="utf-8")
    run_command(
        ["hk", "fix", "-a", "-f", "-S", "rustfmt"],
        cwd=project,
        env=environment | {"DSTACK_FAIL_CHECK": "1"},
    )
    assert "rustfmt --edition 2024" in log.read_text(encoding="utf-8")

    log.write_text("", encoding="utf-8")
    run_command(["hk", "check", "-a", "-S", "cargo-clippy", "-S", "cargo-test"], cwd=project, env=environment)
    assert log.read_text(encoding="utf-8") == ""
    (project / "Cargo.toml").write_text('[package]\nname="example"\nversion="0.1.0"\n', encoding="utf-8")
    run_command(["hk", "check", "-a", "-S", "cargo-clippy", "-S", "cargo-test"], cwd=project, env=environment)
    cargo_log = log.read_text(encoding="utf-8")
    assert "cargo clippy --all-targets --all-features -- -D warnings" in cargo_log
    assert "cargo test --all-targets --all-features" in cargo_log
    assert "cargo-" not in run_command(["hk", "run", "pre-commit", "-a", "-P"], cwd=project).stdout
    assert "cargo-" not in run_command(["hk", "fix", "-a", "-P"], cwd=project).stdout


@pytest.mark.integration
def test_go_profile_renders_exact_contract(tagged_template_source: Path, tmp_path: Path) -> None:
    project = tmp_path / "go-profile"
    payload = setup_generated_project(tagged_template_source, project, language_profiles=("go",))
    mise = tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))
    hk = (project / "hk.pkl").read_text(encoding="utf-8")
    development = (project / "docs/src/development/tooling.md").read_text(encoding="utf-8")
    reference = (project / "docs/src/reference/tooling.md").read_text(encoding="utf-8")

    assert payload["language_profiles"] == ["go"]
    assert {
        name: mise["tools"][name] for name in ("go", "gofumpt", "go:golang.org/x/tools/cmd/goimports", "golangci-lint")
    } == {
        "go": "latest",
        "gofumpt": "latest",
        "go:golang.org/x/tools/cmd/goimports": "latest",
        "golangci-lint": "latest",
    }
    assert "rust" not in mise["tools"]
    for command in (
        r"test -z \"$(goimports -l {{ files }})\"",
        "goimports -w {{ files }}",
        r"test -z \"$(gofumpt -l {{ files }})\"",
        "gofumpt -w {{ files }}",
        "go mod tidy -diff && go mod verify",
        "golangci-lint run",
        "go test ./...",
    ):
        assert command in hk
    assert hk.index('["goimports"]') < hk.index('["gofumpt"]')
    assert "Root `go.mod` enables" in development
    assert "Recorded language profiles: `go`" in reference
    assert "coverage.out" in (project / ".gitignore").read_text(encoding="utf-8")
    assert not (project / "go.mod").exists()
    run_command(["pkl", "eval", "hk.pkl"], cwd=project)
    run_command(["uv", "run", "scripts/check-docs.py"], cwd=project)

    bin_dir = tmp_path / "go-bin"
    log = tmp_path / "go.log"
    write_logging_shims(bin_dir, "goimports", "gofumpt", "go", "golangci-lint")
    environment = merged_environment(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", DSTACK_SHIM_LOG=str(log))
    run_command(
        [
            "hk",
            "check",
            "-a",
            "-S",
            "goimports",
            "-S",
            "gofumpt",
            "-S",
            "go-mod",
            "-S",
            "golangci-lint",
            "-S",
            "go-test",
        ],
        cwd=project,
        env=environment,
    )
    assert not log.exists()

    source = project / "main.go"
    source.write_text("package main\n", encoding="utf-8")
    original = source.read_bytes()
    run_command(["hk", "check", "-a", "-S", "goimports", "-S", "gofumpt"], cwd=project, env=environment)
    source_log = log.read_text(encoding="utf-8")
    assert "goimports -l" in source_log
    assert "gofumpt -l" in source_log
    assert source.read_bytes() == original
    log.write_text("", encoding="utf-8")
    run_command(
        ["hk", "fix", "-a", "-f", "-S", "goimports", "-S", "gofumpt"],
        cwd=project,
        env=environment | {"DSTACK_FAIL_CHECK": "1"},
    )
    fix_log = log.read_text(encoding="utf-8")
    assert "goimports -w" in fix_log
    assert "gofumpt -w" in fix_log

    log.write_text("", encoding="utf-8")
    (project / "go.mod").write_text("module example.test/project\n\ngo 1.24\n", encoding="utf-8")
    original_module = (project / "go.mod").read_bytes()
    run_command(
        ["hk", "check", "-a", "-S", "go-mod", "-S", "golangci-lint", "-S", "go-test"], cwd=project, env=environment
    )
    module_log = log.read_text(encoding="utf-8")
    assert "go mod tidy -diff" in module_log
    assert "go mod verify" in module_log
    assert "golangci-lint run" in module_log
    assert "go test ./..." in module_log
    assert (project / "go.mod").read_bytes() == original_module
    log.write_text("", encoding="utf-8")
    run_command(
        ["hk", "fix", "-a", "-f", "-S", "go-mod"],
        cwd=project,
        env=environment | {"DSTACK_FAIL_GO_TIDY": "1"},
    )
    assert "go mod tidy\n" in log.read_text(encoding="utf-8")
    assert "go-mod" not in run_command(["hk", "run", "pre-commit", "-a", "-P"], cwd=project).stdout
    assert "go-mod" in run_command(["hk", "fix", "-a", "-P"], cwd=project).stdout


def test_setup_project_rejects_unknown_project_kind(repository_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = load_setup_module(repository_root)
    args = ["unknown" if value == SETUP_BRIEF["project_kind"] else value for value in SETUP_BRIEF_ARGS]
    with pytest.raises(SystemExit):
        module.parse_args(args)
    error = capsys.readouterr().err
    assert all(kind in error for kind in module.PROJECT_KINDS)


@pytest.mark.parametrize("relative_path", REQUIRED_TEMPLATE_FILES)
def test_copier_template_contains_required_files(
    repository_root: Path,
    relative_path: str,
) -> None:
    template = repository_root / "skills/setup-project/template"
    assert (template / relative_path).is_file(), relative_path


@pytest.mark.parametrize("relative_path", FORBIDDEN_NEW_PROJECT_TEMPLATE_FILES)
def test_new_project_template_excludes_migration_only_files(
    repository_root: Path,
    relative_path: str,
) -> None:
    template = repository_root / "skills/setup-project/template"
    assert not (template / relative_path).exists(), relative_path


@pytest.mark.parametrize("relative_path", REMOVED_CONTENT_FREE_DOCS)
def test_new_project_template_omits_content_free_reader_pages(repository_root: Path, relative_path: str) -> None:
    template_source = repository_root / "skills/setup-project/template" / f"{relative_path}.jinja"
    assert not template_source.exists(), relative_path


def test_feature_design_placeholders_remain_literal(repository_root: Path) -> None:
    design = (repository_root / "skills/setup-project/template/docs/src/features/_template/design.md").read_text(
        encoding="utf-8"
    )
    assert "{{ feature_number }}" in design


def test_ci_keeps_slow_and_external_suites_separate(repository_root: Path) -> None:
    validate = (repository_root / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    external = (repository_root / ".github/workflows/external-validation.yml").read_text(encoding="utf-8")

    assert 'pytest -m "not integration and not external"' in validate
    assert 'pytest "${{ matrix.path }}" -m integration' in validate
    assert "actions/setup-node" not in validate
    assert "actions/setup-python@v6" in validate
    assert "astral-sh/setup-uv@v8" in validate

    assert "workflow_dispatch:" in external
    assert "schedule:" in external
    assert "tags:" in external
    assert '      - "v*"' in external
    assert "pytest -m external" in external
    assert "actions/setup-node@v6" in external
    assert "jdx/mise-action@e6a8b3978addb5a52f2b4cd9d91eafa7f0ab959d" in external
    assert "install: false" in external


PYTHON_SOURCES = sorted(
    path
    for path in Path(__file__).resolve().parents[1].rglob("*.py")
    if not any(part in {".git", ".venv", "__pycache__"} for part in path.parts)
)


@pytest.mark.parametrize(
    "python_source",
    PYTHON_SOURCES,
    ids=lambda path: path.relative_to(Path(__file__).resolve().parents[1]).as_posix(),
)
def test_python_sources_compile(python_source: Path) -> None:
    compile(python_source.read_text(encoding="utf-8"), str(python_source), "exec")


@pytest.mark.integration
def test_setup_project_uses_bundled_skill_template_and_records_remote_update_state(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    installed_skill = tmp_path / "installed/setup-project"
    shutil.copytree(repository_root / "skills/setup-project", installed_skill)
    project = tmp_path / "bundled-project"
    result = run_command(
        [
            "uv",
            "run",
            str(installed_skill / "scripts/setup-project.py"),
            "--destination",
            str(project),
            "--skip-post-setup",
            "--no-git-init",
            *SETUP_BRIEF_ARGS,
            "--json",
        ],
        cwd=tmp_path,
    )
    payload = json.loads(result.stdout)
    manifest = load_skill_manifest(installed_skill / "SKILL.md")
    version = manifest["metadata"]["version"]
    answers = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))

    assert payload["template_source"] == str(installed_skill)
    assert payload["template_source_kind"] == "bundled"
    assert payload["render_vcs_ref"] is None
    assert payload["update_source"] == "gh:RobertDeRose/dstack"
    assert payload["skill_version"] == version
    assert payload["vcs_ref"] == f"v{version}"
    assert answers["_src_path"] == "gh:RobertDeRose/dstack"
    assert answers["_commit"] == f"v{version}"
    assert {key: answers[key] for key in SETUP_BRIEF} == SETUP_BRIEF
    assert {key: payload[key] for key in SETUP_BRIEF} == SETUP_BRIEF
    assert str(installed_skill) not in (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert (project / "docs/src/SUMMARY.md").is_file()
    for relative in FORBIDDEN_NEW_PROJECT_TEMPLATE_FILES:
        assert not (project / relative).exists(), relative


@pytest.mark.integration
@pytest.mark.parametrize("no_git", [False, True])
def test_setup_project_provisions_tooling_and_reports_no_git_separately(
    repository_root: Path,
    tagged_template_source: Path,
    tmp_path: Path,
    no_git: bool,
) -> None:
    project = tmp_path / f"tooling-{no_git}"
    bin_dir = tmp_path / "bin"
    write_fake_mise(bin_dir)
    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/setup-project/scripts/setup-project.py"),
            "--destination",
            str(project),
            "--template-source",
            str(tagged_template_source),
            "--skip-beads",
            *(["--no-git-init"] if no_git else []),
            *SETUP_BRIEF_ARGS,
            "--json",
        ],
        cwd=tmp_path,
        env=merged_environment(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}"),
    )
    payload = json.loads(result.stdout)

    assert payload["tooling"]["lock"] == {"status": "succeeded", "path": "mise.lock", "error": None}
    assert payload["tooling"]["install"]["status"] == "succeeded"
    assert payload["tooling"]["hooks"]["status"] == ("skipped-no-git" if no_git else "succeeded")
    assert payload["tooling"]["status"] == ("degraded" if no_git else "succeeded")
    assert (project / "mise.lock").read_text(encoding="utf-8").splitlines() == [
        "linux-x64",
        "linux-arm64",
        "macos-x64",
        "macos-arm64",
    ]
    assert payload["outstanding"] == (
        ["Tooling recovery: MISE_GLOBAL_CONFIG_FILE=/dev/null mise x -- hk install --mise"] if no_git else []
    ) + ["Beads initialization and verification"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("failure", "expected_stages", "recovery"),
    [
        ("missing", ("unavailable", "skipped", "skipped", "skipped"), ["python3 scripts/setup-tooling.py --json"]),
        (
            "lock",
            ("available", "failed", "skipped", "skipped"),
            [
                "MISE_GLOBAL_CONFIG_FILE=/dev/null mise lock --yes --platform "
                "linux-x64,linux-arm64,macos-x64,macos-arm64",
                "python3 scripts/setup-tooling.py --json",
            ],
        ),
        (
            "install",
            ("available", "succeeded", "failed", "skipped"),
            ["MISE_GLOBAL_CONFIG_FILE=/dev/null mise install --locked", "python3 scripts/setup-tooling.py --json"],
        ),
        (
            "hooks",
            ("available", "succeeded", "succeeded", "failed"),
            ["MISE_GLOBAL_CONFIG_FILE=/dev/null mise x -- hk install --mise"],
        ),
    ],
)
def test_setup_project_preserves_scaffold_and_reports_tooling_failures(
    repository_root: Path,
    tagged_template_source: Path,
    tmp_path: Path,
    failure: str,
    expected_stages: tuple[str, str, str, str],
    recovery: list[str],
) -> None:
    project = tmp_path / failure
    bin_dir = tmp_path / f"bin-{failure}"
    bin_dir.mkdir()
    if failure == "missing":
        for command in ("uv", "git", "mdbook"):
            executable = shutil.which(command)
            assert executable is not None
            (bin_dir / command).symlink_to(executable)
        path = str(bin_dir)
    else:
        write_fake_mise(bin_dir)
        path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"

    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/setup-project/scripts/setup-project.py"),
            "--destination",
            str(project),
            "--template-source",
            str(tagged_template_source),
            "--skip-beads",
            *SETUP_BRIEF_ARGS,
            "--json",
        ],
        cwd=tmp_path,
        env=merged_environment(PATH=path, DSTACK_MISE_FAIL=failure),
    )
    payload = json.loads(result.stdout)
    tooling = payload["tooling"]

    assert (
        tooling["mise"],
        tooling["lock"]["status"],
        tooling["install"]["status"],
        tooling["hooks"]["status"],
    ) == expected_stages
    assert tooling["status"] == "degraded"
    assert tooling["recovery"] == recovery
    assert payload["outstanding"] == [
        *(f"Tooling recovery: {command}" for command in recovery),
        "Beads initialization and verification",
    ]
    assert (project / ".copier-answers.yml").is_file()
    assert payload["docs_validated"] is True


@pytest.mark.integration
def test_setup_project_skip_does_not_execute_override_project_code(
    repository_root: Path,
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "executed"
    provisioner = tagged_template_source / "skills/setup-project/template/scripts/setup-tooling.py"
    provisioner.write_text(
        f"#!/usr/bin/env python3\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    commit_repository(tagged_template_source, "Malicious provisioner fixture", "v1.1.0")
    project = tmp_path / "skipped"

    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/setup-project/scripts/setup-project.py"),
            "--destination",
            str(project),
            "--template-source",
            str(tagged_template_source),
            "--vcs-ref",
            "v1.1.0",
            "--skip-post-setup",
            *SETUP_BRIEF_ARGS,
            "--json",
        ],
        cwd=tmp_path,
    )
    payload = json.loads(result.stdout)

    assert payload["tooling"]["status"] == "skipped"
    assert not marker.exists()
    assert (project / "scripts/setup-tooling.py").is_file()


@pytest.mark.integration
def test_setup_project_refuses_existing_copier_state_without_mutation(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "managed-project"
    project.mkdir()
    answers = project / ".copier-answers.yml"
    original = "_src_path: gh:example/project\n_commit: v1.2.3\n"
    answers.write_text(original, encoding="utf-8")

    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/setup-project/scripts/setup-project.py"),
            "--destination",
            str(project),
        ],
        cwd=tmp_path,
        expected=1,
    )

    assert "offer /update-project and run it only after the user agrees" in result.stderr
    assert answers.read_text(encoding="utf-8") == original
    assert sorted(path.name for path in project.iterdir()) == [".copier-answers.yml"]


@pytest.mark.integration
def test_setup_project_routes_existing_non_skill_project_files_to_migration(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "existing-project"
    workflow = project / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: Existing CI\n", encoding="utf-8")

    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/setup-project/scripts/setup-project.py"),
            "--destination",
            str(project),
        ],
        cwd=tmp_path,
        expected=1,
    )

    assert "Use /migrate-workflow for an existing project" in result.stderr
    assert workflow.read_text(encoding="utf-8") == "name: Existing CI\n"
    assert not (project / ".copier-answers.yml").exists()


@pytest.mark.integration
def test_setup_project_uses_directory_name_and_preserves_template_tokens(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "example-project"
    setup_generated_project(tagged_template_source, project)

    assert (project / ".copier-answers.yml").is_file()
    assert "# example-project" in (project / "README.md").read_text(encoding="utf-8")
    assert "{{ feature_number }}" in (project / "docs/src/features/_template/design.md").read_text(encoding="utf-8")

    run_command(["uv", "run", str(project / "scripts/check-docs.py")], cwd=project)


@pytest.mark.integration
@pytest.mark.parametrize("entrypoint", ["repository", "bundled"])
@pytest.mark.parametrize(("kind", "guidance"), list(KIND_GUIDANCE.items()))
def test_setup_project_renders_the_factual_book_matrix(
    tagged_template_source: Path,
    tmp_path: Path,
    entrypoint: str,
    kind: str,
    guidance: str,
) -> None:
    expected_name = 'A "quoted" &#92; café 😀 &#91;project&#93;'
    expected_purpose = (
        'Coordinate &#91;reader&#93;(missing.md) 😀 devices with a literal &#92; path, café text, and "quotes".'
    )
    expected_users = 'Operators who own "reader" fleets &#91;team&#93;.'
    expected_scope = "Provisioning, health checks, and &#96;status&#96; workflows."
    expected_boundaries = "Firmware &#35; updates and identity-provider &lt;admin&gt; remain external."

    for include_readme in (False, True):
        project = tmp_path / f"{entrypoint}-{kind}-{include_readme}"
        payload = setup_generated_project(
            tagged_template_source,
            project,
            kind=kind,
            name=PUNCTUATED_PROJECT_NAME,
            entrypoint=entrypoint,
            include_readme=include_readme,
        )

        docs = project / "docs/src"
        assert {path.relative_to(docs).as_posix() for path in docs.rglob("*.md")} == INITIAL_READER_MARKDOWN
        assert all(not (project / relative).exists() for relative in REMOVED_CONTENT_FREE_DOCS)
        assert (project / "README.md").exists() is include_readme
        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "git commit -F <file>" in agents
        assert "multiple `-m` flags" in agents
        assert "escaped `\\n`" in agents
        assert "git merge --ff-only" in agents
        assert "never create a merge commit" in agents
        assert "Initial reviewers always use fresh context" in agents
        assert "one context builder plus four reviewers" in agents
        assert "one context builder plus two reviewers" in agents
        assert "resume only the original reviewers whose domains changed" in agents
        assert "original packet when one exists" in agents

        mise_config = tomllib.loads((project / "mise.toml").read_text(encoding="utf-8"))
        assert mise_config["tools"] == {
            "hk": "1.49.0",
            "node": "lts",
            "mdbook": "latest",
            "uv": "latest",
            "rumdl": "latest",
            "typos": "latest",
            "npm:markdown-table-formatter": "latest",
        }
        assert mise_config["tasks"] == {
            "check": {"description": "Run repository validation", "run": "hk check -a"},
            "fix": {"description": "Apply deterministic repository fixes", "run": "hk fix -a"},
            "docs:check": {
                "description": "Validate and build the documentation",
                "depends": ["docs:build"],
                "run": "uv run scripts/check-docs.py",
            },
            "docs:build": {"description": "Build the documentation site", "run": "mdbook build docs"},
            "docs:serve": {
                "description": "Serve the documentation site locally",
                "usage": 'arg "[port]" help="Port to serve on" default="3000"',
                "run": ('#!/usr/bin/env bash\nset -euo pipefail\nmdbook serve docs --port "${usage_port:-3000}"\n'),
            },
        }
        assert mise_config["env"] == {"HK_MISE": 1}
        assert "hooks" not in mise_config

        hk_config = (project / "hk.pkl").read_text(encoding="utf-8")
        assert hk_config.count("v1.49.0/hk@1.49.0") == 2
        assert hk_config.count('stash = "git"') == 1
        step_config = hk_config.split("\nhooks {", 1)[0]
        assert set(re.findall(r'^  \["([^\"]+)"\] =', step_config, flags=re.MULTILINE)) == {
            "byte_order_marker",
            "check_case_conflict",
            "check_executables_have_shebangs",
            "check_merge_conflict",
            "detect_private_key",
            "docs",
            "fix_smart_quotes",
            "markdown-table-formatter",
            "mise",
            "newlines",
            "rumdl",
            "trailing_whitespace",
            "typos",
        }
        for dependency in (
            'depends = "byte_order_marker"',
            'depends = "fix_smart_quotes"',
            'depends = "markdown-table-formatter"',
            'depends = "newlines"',
            'depends = "rumdl"',
            'depends = "trailing_whitespace"',
            'depends = "mise"',
        ):
            assert dependency in hk_config
        assert set(re.findall(r'^  \["(pre-commit|check|fix)"\]', hk_config, flags=re.MULTILINE)) == {
            "pre-commit",
            "check",
            "fix",
        }
        assert (project / ".config/rumdl.toml").is_file()
        assert "mise.lock" not in (project / ".gitignore").read_text(encoding="utf-8")

        answers = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))
        expected_brief = {**SETUP_BRIEF, "project_kind": kind}
        assert {field: answers[field] for field in expected_brief} == expected_brief
        assert {field: payload[field] for field in expected_brief} == expected_brief
        assert answers["project_name"] == PUNCTUATED_PROJECT_NAME
        assert payload["readme_created"] is include_readme
        assert payload["tooling"]["status"] == "skipped"
        assert payload["tooling"]["recovery"] == ["python3 scripts/setup-tooling.py --json"]
        assert payload["template_source_kind"] == ("override" if entrypoint == "repository" else "bundled")
        assert answers["_src_path"] == (
            str(tagged_template_source) if entrypoint == "repository" else "gh:RobertDeRose/dstack"
        )

        overview = (docs / "introduction/project-overview.md").read_text(encoding="utf-8")
        assert overview == (
            f"\n# {expected_name} overview\n\n"
            f"- Project kind: `{kind}`\n\n"
            "## Purpose\n\n"
            f"{expected_purpose}\n\n"
            "## Intended users\n\n"
            f"{expected_users}\n\n"
            "## Current scope\n\n"
            f"{expected_scope}\n\n"
            "Future behavior belongs in [Planned features](../planned-features.md) until delivered.\n\n"
            "## Boundaries\n\n"
            f"{expected_boundaries}\n"
        )
        roadmap = (docs / "planned-features.md").read_text(encoding="utf-8")
        assert all(
            line in roadmap
            for line in (
                f"- Purpose: {expected_purpose}",
                f"- Current scope: {expected_scope}",
                f"- Boundaries: {expected_boundaries}",
            )
        )
        assert guidance in (docs / "introduction/documentation-conventions.md").read_text(encoding="utf-8")
        if include_readme:
            readme = (project / "README.md").read_text(encoding="utf-8")
            assert f"# {expected_name}" in readme
            assert expected_purpose in readme
            assert "mise run docs:check" in readme
            assert "mise run docs:serve" in readme
            assert "uv run scripts/check-docs.py" not in readme

        book = tomllib.loads((project / "docs/book.toml").read_text(encoding="utf-8"))["book"]
        assert book["title"] == PUNCTUATED_PROJECT_NAME
        assert book["description"] == SETUP_BRIEF["project_purpose"]

        summary = (docs / "SUMMARY.md").read_text(encoding="utf-8")
        assert re.findall(r"\]\(([^)]+)\)", summary) == [
            "introduction/project-overview.md",
            "introduction/documentation-conventions.md",
            "development/tooling.md",
            "development/feature-lifecycle.md",
            "reference/tooling.md",
            "planned-features.md",
            "features/index.md",
        ]

        reader_text = "\n".join(
            path.read_text(encoding="utf-8") for path in docs.rglob("*.md") if "_template" not in path.parts
        )
        assert all(
            phrase not in reader_text for phrase in ("Describe the", "Explain how", "Summarize current", "Record only")
        )
        run_command(["uv", "run", str(project / "scripts/check-docs.py")], cwd=project)
        run_command(["mdbook", "build", "docs"], cwd=project)


@pytest.mark.external
def test_generated_tooling_contract_end_to_end(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    if shutil.which("mise") is None:
        pytest.skip("Live generated-tooling validation requires mise")

    project = tmp_path / "tooling"
    setup_generated_project(tagged_template_source, project)
    fix_target = project / "fix.md"
    fix_target.write_text("# Fix target\n", encoding="utf-8")
    configure_project_git(project)
    commit_repository(project, "Initial generated project")
    run_command(["mise", "trust", "-y"], cwd=project)

    tooling = json.loads(run_command(["python3", "scripts/setup-tooling.py", "--json"], cwd=project).stdout)
    assert tooling["status"] == "succeeded"
    lock = (project / "mise.lock").read_text(encoding="utf-8")
    assert all(platform in lock for platform in ("linux-x64", "linux-arm64", "macos-x64", "macos-arm64"))
    run_command(["git", "add", "mise.lock"], cwd=project)
    run_command(["git", "commit", "--no-verify", "-m", "Commit resolved tooling"], cwd=project)

    tasks = json.loads(run_command(["mise", "tasks", "--json"], cwd=project).stdout)
    assert {task["name"] for task in tasks} == {"check", "fix", "docs:check", "docs:build", "docs:serve"}
    run_command(["mise", "x", "--", "hk", "config", "dump"], cwd=project)
    legacy_hook = project / ".git/hooks/pre-commit"
    if not legacy_hook.is_file():
        hook_config = run_command(["git", "config", "--local", "--get-regexp", "^hook\\."], cwd=project).stdout
        assert "hk" in hook_config
    run_command(["mise", "run", "check"], cwd=project)
    run_command(["mise", "run", "docs:build"], cwd=project)

    markdown = project / "race.md"
    markdown.write_text("# Race\n\n| A | B |\n|---|---|\n| one | two |  \n", encoding="utf-8")
    mise_toml = project / "mise.toml"
    mise_toml.write_text(
        mise_toml.read_text(encoding="utf-8").replace('hk = "1.49.0"', 'hk="1.49.0"  '),
        encoding="utf-8",
    )
    run_command(["git", "add", "race.md", "mise.toml"], cwd=project)
    readme = project / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nUnstaged project note.\n", encoding="utf-8")

    run_command(["git", "commit", "-m", "Exercise installed hook"], cwd=project)
    run_command(["mise", "fmt", "--check"], cwd=project)
    assert readme.read_text(encoding="utf-8").endswith("\nUnstaged project note.\n")
    assert markdown.is_file()

    fix_target.write_text("# Updated target  \n", encoding="utf-8")
    run_command(["mise", "run", "fix"], cwd=project)
    assert fix_target.read_text(encoding="utf-8") == "# Updated target\n"
    assert "fix.md" in run_command(["git", "status", "--short"], cwd=project).stdout

    run_command(["git", "restore", "--staged", "fix.md"], cwd=project)
    run_command(["git", "restore", "README.md", "fix.md"], cwd=project)
    run_command(["mise", "run", "check"], cwd=project)
    assert run_command(["git", "status", "--short"], cwd=project).stdout == ""


@pytest.mark.integration
def test_book_toml_round_trips_accepted_single_line_controls(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    controls = "".join(chr(value) for value in (*range(1, 10), 11, 12, *range(14, 32), 127))
    name = f"Control {controls} project"
    purpose = f"Control {controls} purpose."
    setup_generated_project(
        tagged_template_source,
        tmp_path / "controls",
        name=name,
        brief={**SETUP_BRIEF, "project_purpose": purpose},
    )
    book = tomllib.loads((tmp_path / "controls/docs/book.toml").read_text(encoding="utf-8"))["book"]
    assert book["title"] == name
    assert book["description"] == purpose


@pytest.mark.integration
def test_copier_update_applies_new_release_and_preserves_project_changes(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "example-project"
    setup_generated_project(tagged_template_source, project)
    configure_project_git(project)
    commit_repository(project, "Initial generated project")

    project_overview = project / "docs/src/introduction/project-overview.md"
    project_overview.write_text(
        project_overview.read_text(encoding="utf-8") + "\nProject-owned update.\n",
        encoding="utf-8",
    )
    (project / "mise.lock").write_text("stale\n", encoding="utf-8")
    commit_repository(project, "Project-specific documentation and stale lock")

    (tagged_template_source / "skills/setup-project/template/.dstack-release.jinja").write_text(
        "v0.0.2\n", encoding="utf-8"
    )
    commit_repository(tagged_template_source, "dstack v0.0.2", "v0.0.2")

    update = tagged_template_source / "skills/update-project/scripts/update-project.py"
    fake_bin = tmp_path / "bin"
    write_fake_mise(fake_bin)
    result = run_command(
        [
            "uv",
            "run",
            str(update),
            "--destination",
            str(project),
            "--vcs-ref",
            "v0.0.2",
            "--skip-beads-check",
            "--json",
        ],
        cwd=tagged_template_source,
        env=merged_environment(PATH=f"{fake_bin}:{os.environ['PATH']}"),
    )

    payload = json.loads(result.stdout)
    assert payload["tooling"]["status"] == "succeeded"
    assert payload["conflicts"] == []
    assert payload["ready_to_resume_feature_work"] is False
    assert (project / "mise.lock").read_text(encoding="utf-8") != "stale\n"
    assert (project / ".dstack-release").read_text(encoding="utf-8") == "v0.0.2\n"
    assert "Project-owned update." in project_overview.read_text(encoding="utf-8")


@pytest.mark.integration
def test_update_project_uses_latest_release_tag_ignores_venv_and_uses_portable_beads_checks(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "example-project"
    setup_generated_project(tagged_template_source, project, language_profiles=("python",))
    configure_project_git(project)
    commit_repository(project, "Initial generated project")

    # A dependency environment may legitimately contain conflict-marker examples.
    ignored = project / ".venv/lib/python3.13/site-packages/example.py"
    ignored.parent.mkdir(parents=True)
    ignored.write_text(
        "<<<<<<< example\nleft\n=======\nright\n>>>>>>> example\n",
        encoding="utf-8",
    )

    update = tagged_template_source / "skills/update-project/scripts/update-project.py"
    packaged_ref = "v0.0.2"
    (tagged_template_source / "skills/setup-project/template/.dstack-release.jinja").write_text(
        packaged_ref + "\n", encoding="utf-8"
    )
    commit_repository(tagged_template_source, f"dstack {packaged_ref}", packaged_ref)

    fake_bin = tmp_path / "bin"
    bd_log = tmp_path / "bd.log"
    write_fake_bd(fake_bin, bd_log)
    write_fake_mise(fake_bin)
    environment = merged_environment(
        PATH=f"{fake_bin}:{os.environ['PATH']}",
        DSTACK_BD_LOG=str(bd_log),
    )
    result = run_command(
        [
            "uv",
            "run",
            str(update),
            "--destination",
            str(project),
            "--json",
        ],
        cwd=tagged_template_source,
        env=environment,
    )
    payload = json.loads(result.stdout)

    assert payload["vcs_ref"] == packaged_ref
    assert payload["conflicts"] == []
    assert payload["beads_checked"] is True
    assert (project / ".dstack-release").read_text(encoding="utf-8") == packaged_ref + "\n"
    commands = bd_log.read_text(encoding="utf-8").splitlines()
    assert "info --json" in commands
    assert "ready --json --limit 1" in commands
    assert "formula show feature-lifecycle --json" in commands
    assert all(not command.startswith("doctor") for command in commands)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("lock", ("failed", "skipped", "skipped")),
        ("install", ("succeeded", "failed", "skipped")),
        ("hooks", ("succeeded", "succeeded", "failed")),
    ],
)
def test_update_project_preserves_update_and_reports_degraded_tooling(
    tagged_template_source: Path,
    tmp_path: Path,
    failure: str,
    expected: tuple[str, str, str],
) -> None:
    project = tmp_path / failure
    setup_generated_project(tagged_template_source, project)
    configure_project_git(project)
    commit_repository(project, "Initial generated project")
    (tagged_template_source / "skills/setup-project/template/.dstack-release.jinja").write_text(
        "v0.0.2\n", encoding="utf-8"
    )
    commit_repository(tagged_template_source, "dstack v0.0.2", "v0.0.2")
    fake_bin = tmp_path / f"bin-{failure}"
    write_fake_mise(fake_bin)

    result = run_command(
        [
            "uv",
            "run",
            str(tagged_template_source / "skills/update-project/scripts/update-project.py"),
            "--destination",
            str(project),
            "--vcs-ref",
            "v0.0.2",
            "--skip-beads-check",
            "--json",
        ],
        cwd=tagged_template_source,
        env=merged_environment(
            PATH=f"{fake_bin}:{os.environ['PATH']}",
            DSTACK_MISE_FAIL=failure,
        ),
    )
    payload = json.loads(result.stdout)

    assert (
        payload["tooling"]["lock"]["status"],
        payload["tooling"]["install"]["status"],
        payload["tooling"]["hooks"]["status"],
    ) == expected
    assert payload["tooling"]["status"] == "degraded"
    assert payload["ready_to_resume_feature_work"] is False
    assert payload["outstanding"]
    assert (project / ".dstack-release").read_text(encoding="utf-8") == "v0.0.2\n"
    assert (project / ".copier-answers.yml").is_file()


@pytest.mark.integration
def test_update_project_skips_generated_code_when_copier_conflicts(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "conflict"
    setup_generated_project(tagged_template_source, project)
    configure_project_git(project)
    commit_repository(project, "Initial generated project")
    readme = project / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("mise run check", "mise run project-check"))
    commit_repository(project, "Customize check command")

    template_readme = tagged_template_source / (
        "skills/setup-project/template/[% if include_readme %]README.md[% endif %].jinja"
    )
    template_readme.write_text(
        template_readme.read_text(encoding="utf-8").replace("mise run check", "mise run upstream-check"),
        encoding="utf-8",
    )
    commit_repository(tagged_template_source, "dstack v0.0.2", "v0.0.2")
    fake_bin = tmp_path / "bin-conflict"
    log = tmp_path / "mise.log"
    write_fake_mise(fake_bin)

    result = run_command(
        [
            "uv",
            "run",
            str(tagged_template_source / "skills/update-project/scripts/update-project.py"),
            "--destination",
            str(project),
            "--vcs-ref",
            "v0.0.2",
            "--skip-beads-check",
            "--json",
        ],
        cwd=tagged_template_source,
        env=merged_environment(
            PATH=f"{fake_bin}:{os.environ['PATH']}",
            DSTACK_MISE_LOG=str(log),
        ),
        expected=2,
    )
    payload = json.loads(result.stdout)

    assert "README.md" in payload["conflicts"]
    assert payload["tooling"]["status"] == "skipped"
    assert payload["tooling"]["recovery"] == ["python3 scripts/setup-tooling.py --json"]
    assert payload["ready_to_resume_feature_work"] is False
    assert not log.exists()


@pytest.mark.parametrize("malformation", ["missing-error", "successful-error"])
def test_update_project_rejects_malformed_stage_errors(
    repository_root: Path,
    tmp_path: Path,
    malformation: str,
) -> None:
    module = load_update_module(repository_root)
    (tmp_path / "mise.lock").write_text("resolved\n", encoding="utf-8")
    result: dict[str, Any] = {
        "status": "succeeded",
        "mise": "available",
        "lock": {"status": "succeeded", "path": "mise.lock", "error": None},
        "install": {"status": "succeeded", "error": None},
        "hooks": {"status": "succeeded", "error": None},
        "platforms": module.TOOLING_PLATFORMS,
        "recovery": [],
    }
    if malformation == "missing-error":
        result["install"].pop("error")
    else:
        result["hooks"]["error"] = "unexpected"

    assert module.tooling_result_error(result, tmp_path) is not None


@pytest.mark.integration
@pytest.mark.parametrize(
    ("payload", "creates_empty_lock"),
    [
        ({"status": "succeeded", "recovery": []}, False),
        (
            {
                "status": "succeeded",
                "mise": "available",
                "lock": {"status": "succeeded", "path": "mise.lock", "error": None},
                "install": {"status": "succeeded", "error": None},
                "hooks": {"status": "succeeded", "error": None},
                "platforms": ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"],
                "recovery": [],
            },
            True,
        ),
    ],
)
def test_update_project_rejects_invalid_or_unverified_tooling_success(
    tagged_template_source: Path,
    tmp_path: Path,
    payload: dict[str, Any],
    creates_empty_lock: bool,
) -> None:
    project = tmp_path / "invalid-tooling"
    setup_generated_project(tagged_template_source, project)
    configure_project_git(project)
    commit_repository(project, "Initial generated project")

    provisioner = tagged_template_source / "skills/setup-project/template/scripts/setup-tooling.py"
    provisioner.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "from pathlib import Path\n"
        + ("Path('mise.lock').write_text('')\n" if creates_empty_lock else "")
        + f"print(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )
    commit_repository(tagged_template_source, "dstack v0.0.2", "v0.0.2")

    result = run_command(
        [
            "uv",
            "run",
            str(tagged_template_source / "skills/update-project/scripts/update-project.py"),
            "--destination",
            str(project),
            "--vcs-ref",
            "v0.0.2",
            "--skip-beads-check",
            "--json",
        ],
        cwd=tagged_template_source,
    )
    update = json.loads(result.stdout)

    assert update["tooling"]["status"] == "degraded"
    assert update["tooling"]["lock"]["status"] == "failed"
    assert update["ready_to_resume_feature_work"] is False
    assert update["outstanding"] == ["Tooling recovery: python3 scripts/setup-tooling.py --json"]


@pytest.mark.integration
def test_update_project_refuses_a_non_git_destination(repository_root: Path, tmp_path: Path) -> None:
    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/update-project/scripts/update-project.py"),
            "--destination",
            str(tmp_path),
            "--preflight",
            "--json",
        ],
        cwd=tmp_path,
        expected=1,
    )
    assert "Copier updates require a Git repository" in result.stderr
    assert not (tmp_path / ".copier-answers.yml").exists()


@pytest.mark.integration
def test_update_preflight_routes_legacy_tasks_without_beads_to_migration(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "legacy-managed-project"
    feature = project / "docs/src/features/alpha"
    feature.mkdir(parents=True)
    (feature / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (project / "tasks.md").write_text("# Project tasks\n", encoding="utf-8")
    (project / "vendor/example").mkdir(parents=True)
    (project / "vendor/example/tasks.md").write_text("# Vendored tasks\n", encoding="utf-8")
    (project / ".copier-answers.yml").write_text(
        "_src_path: gh:RobertDeRose/dstack\n_commit: v0.0.1\n",
        encoding="utf-8",
    )
    formula = project / ".beads/formulas/feature-lifecycle.formula.toml"
    formula.parent.mkdir(parents=True)
    formula.write_text('formula = "feature-lifecycle"\n', encoding="utf-8")
    initialize_git(project, "legacy managed project")
    update = repository_root / "skills/update-project/scripts/update-project.py"

    result = run_command(
        ["uv", "run", str(update), "--destination", str(project), "--preflight", "--json"],
        cwd=project,
    )
    payload = json.loads(result.stdout)
    assert payload["recommended_workflow"] == "migrate-workflow"
    assert payload["beads_state_present"] is False
    assert payload["legacy_task_files"] == ["docs/src/features/alpha/tasks.md", "tasks.md"]

    blocked = run_command(
        ["uv", "run", str(update), "--destination", str(project), "--json"],
        cwd=project,
        expected=1,
    )
    assert "offer /migrate-workflow and run it only after the user agrees" in blocked.stderr
    assert "Legacy task files:" in blocked.stderr

    (project / ".beads/metadata.json").write_text("{}\n", encoding="utf-8")
    initialized = run_command(
        ["uv", "run", str(update), "--destination", str(project), "--preflight", "--json"],
        cwd=project,
    )
    initialized_payload = json.loads(initialized.stdout)
    assert initialized_payload["recommended_workflow"] == "update-project"
    assert initialized_payload["beads_state_present"] is True


@pytest.mark.integration
def test_pre_f010_unmanaged_project_adoption_is_unsupported(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy-project"
    (legacy / "docs/src/features/alpha").mkdir(parents=True)
    summary = legacy / "docs/src/SUMMARY.md"
    summary.write_text("# Summary\n\n# Custom Architecture\n", encoding="utf-8")
    initialize_git(legacy, "Legacy project")
    original_summary = summary.read_text(encoding="utf-8")

    adopt = tagged_template_source / "skills/migrate-workflow/scripts/adopt-template.py"
    result = run_command(
        [
            "uv",
            "run",
            str(adopt),
            "--destination",
            str(legacy),
            "--template-source",
            str(tagged_template_source),
            "--vcs-ref",
            "v0.0.1",
            "--json",
        ],
        cwd=tagged_template_source,
        expected=1,
    )

    assert 'Question "project_purpose" is required' in result.stderr
    assert summary.read_text(encoding="utf-8") == original_summary
    assert not (legacy / ".copier-answers.yml").exists()


@pytest.mark.integration
def test_pre_f010_managed_project_adoption_is_unsupported(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "managed-legacy-project"
    project.mkdir()
    answers = project / ".copier-answers.yml"
    original_answers = (
        f"_src_path: {tagged_template_source}\n"
        "_commit: v0.0.0\n"
        "project_name: Managed legacy project\n"
        "project_slug: managed-legacy-project\n"
        "project_description: Existing managed project.\n"
        "repository_default_branch: trunk\n"
        "include_readme: false\n"
    )
    answers.write_text(original_answers, encoding="utf-8")
    initialize_git(project, "managed legacy project")

    adopt = tagged_template_source / "skills/migrate-workflow/scripts/adopt-template.py"
    result = run_command(
        [
            "uv",
            "run",
            str(adopt),
            "--destination",
            str(project),
            "--vcs-ref",
            "v0.0.1",
            "--json",
        ],
        cwd=tagged_template_source,
        expected=1,
    )

    assert 'Question "project_purpose" is required' in result.stderr
    assert answers.read_text(encoding="utf-8") == original_answers


def test_tested_workflow_gaps_are_explicit(repository_root: Path) -> None:
    plan = (repository_root / "skills/plan-features/SKILL.md").read_text(encoding="utf-8")
    start = (repository_root / "skills/start-feature/SKILL.md").read_text(encoding="utf-8")
    close = (repository_root / "skills/close-feature/SKILL.md").read_text(encoding="utf-8")
    migrate = (repository_root / "skills/migrate-workflow/SKILL.md").read_text(encoding="utf-8")
    assert "process decisions chronologically" in plan
    assert "implementation_repository" in plan
    assert "roadmap-only" in start
    assert "create a worktree in the planning repository" in start
    assert all(state in close for state in ("passed", "failed", "unavailable", "waived", "not-applicable"))
    assert "documentation validation after archival" in migrate


@pytest.mark.integration
def test_setup_helper_runs_post_setup_without_generating_bootstrap(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "new-project"
    fake_bin = tmp_path / "bin"
    bd_log = tmp_path / "bd.log"
    write_fake_bd(fake_bin, bd_log)
    write_fake_mise(fake_bin)
    result = run_command(
        [
            "uv",
            "run",
            str(repository_root / "skills/setup-project/scripts/setup-project.py"),
            "--destination",
            str(project),
            "--no-git-init",
            *SETUP_BRIEF_ARGS,
            "--json",
        ],
        cwd=tmp_path,
        env=merged_environment(
            PATH=f"{fake_bin}:{os.environ['PATH']}",
            DSTACK_BD_LOG=str(bd_log),
        ),
    )
    payload = json.loads(result.stdout)

    assert payload["post_setup_ran"] is True
    assert payload["docs_validated"] is True
    assert payload["beads_initialized"] is True
    assert payload["tooling"]["hooks"]["status"] == "skipped-no-git"
    assert payload["outstanding"] == ["Tooling recovery: MISE_GLOBAL_CONFIG_FILE=/dev/null mise x -- hk install --mise"]
    commands = bd_log.read_text(encoding="utf-8").splitlines()
    assert "--version" in commands
    assert "init --skip-agents --stealth --quiet" in commands
    assert "formula show feature-lifecycle --json" in commands
    for relative in FORBIDDEN_NEW_PROJECT_TEMPLATE_FILES:
        assert not (project / relative).exists(), relative


def test_migration_supports_json_and_deduplicates_notes(repository_root: Path) -> None:
    script = (repository_root / "skills/migrate-workflow/scripts/migrate-legacy-workflow.py").read_text(
        encoding="utf-8"
    )
    assert 'parser.add_argument("--json"' in script
    assert '["bd", "show", issue_id, "--json"]' in script
    assert "if note in str(notes)" in script


@pytest.mark.external
def test_skills_cli_discovers_all_skills(repository_root: Path) -> None:
    result = run_command(
        ["npx", "--yes", "skills@latest", "add", ".", "--list"],
        cwd=repository_root,
    )
    output = ANSI_ESCAPE.sub("", result.stdout)

    assert f"Found {len(EXPECTED_SKILLS)} skills" in output
    for skill in EXPECTED_SKILLS:
        assert skill in output


def test_template_formula_names_feature_tasks_and_uses_one_epic_container(repository_root: Path) -> None:
    formula_path = repository_root / "skills/setup-project/template/.beads/formulas/feature-lifecycle.formula.toml"
    formula = tomllib.loads(formula_path.read_text(encoding="utf-8"))
    steps = formula["steps"]
    implementation = next(step for step in steps if step["id"] == "implementation")

    assert implementation["type"] == "task"
    assert all(step["title"].startswith("F{{feature_number}} — ") for step in steps)
    assert all("workflow:feature" not in step["labels"] for step in steps)
    assert all("workflow:feature-lifecycle" in step["labels"] for step in steps)
    for step in steps:
        assert step["metadata"]["feature_number"] == "{{feature_number}}"
        assert step["metadata"]["feature_slug"] == "{{feature_slug}}"
        assert step["metadata"]["feature_name"] == "{{feature_name}}"

    plan = (repository_root / "skills/plan-features/SKILL.md").read_text(encoding="utf-8")
    assert "The returned root is the feature epic" in plan
    assert "not a second feature epic or a milestone" in " ".join(plan.split())


@pytest.mark.integration
def test_feature_resolver_selects_epics_by_human_reference_and_readiness(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    features = [
        {
            "id": "passport-mol-active",
            "title": "F005 — Already active",
            "issue_type": "epic",
            "status": "in_progress",
            "priority": 0,
            "ready": True,
            "metadata": {
                "feature_number": "005",
                "feature_slug": "already-active",
                "feature_name": "Already active",
            },
        },
        {
            "id": "passport-mol-1p9",
            "title": "F020 — Core payloads and state",
            "issue_type": "epic",
            "status": "open",
            "priority": 2,
            "ready": True,
            "metadata": {
                "feature_number": "020",
                "feature_slug": "core-payloads-and-state",
                "feature_name": "Core payloads and state",
            },
        },
        {
            "id": "passport-mol-tzq",
            "title": "F010 — Conduit REST list response validation",
            "issue_type": "epic",
            "status": "open",
            "priority": 1,
            "ready": True,
            "metadata": {
                "feature_number": "010",
                "feature_slug": "conduit-rest-list-response-validation",
                "feature_name": "Conduit REST list response validation",
            },
        },
    ]
    fake_bin = tmp_path / "bin"
    bd_log = tmp_path / "bd.log"
    write_fake_bd(fake_bin, bd_log)
    environment = merged_environment(
        PATH=f"{fake_bin}:{os.environ['PATH']}",
        DSTACK_BD_LOG=str(bd_log),
        DSTACK_BD_FEATURES=json.dumps(features),
    )
    resolver = repository_root / "skills/dstack-core/scripts/resolve-feature.py"

    next_result = run_command(
        ["uv", "run", str(resolver), "--root", str(tmp_path), "--next", "--json"],
        cwd=tmp_path,
        env=environment,
    )
    selected = json.loads(next_result.stdout)
    assert selected["id"] == "passport-mol-tzq"
    assert selected["feature_reference"] == "010-conduit-rest-list-response-validation"
    assert selected["recommended_command"] == "/start-feature 010-conduit-rest-list-response-validation"

    named_result = run_command(
        [
            "uv",
            "run",
            str(resolver),
            "Core payloads and state",
            "--root",
            str(tmp_path),
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
    )
    named = json.loads(named_result.stdout)
    assert named["id"] == "passport-mol-1p9"
    assert named["feature_reference"] == "020-core-payloads-and-state"
    commands = bd_log.read_text(encoding="utf-8").splitlines()
    assert any(command.startswith("ready --type epic --label workflow:feature") for command in commands)
    assert all("list --ready" not in command for command in commands)


def test_setup_is_bundled_while_update_and_adoption_use_release_tags(repository_root: Path) -> None:
    setup = (repository_root / "skills/setup-project/scripts/setup-project.py").read_text(encoding="utf-8")
    assert "BUNDLED_TEMPLATE_SOURCE = SKILL_DIR" in setup
    assert "load_skill_version" in setup
    assert "record_update_state" in setup
    assert "using_bundled_template = args.template_source is None" in setup
    assert "default=DEFAULT_TEMPLATE_SOURCE" not in setup

    update = (repository_root / "skills/update-project/scripts/update-project.py").read_text(encoding="utf-8")
    assert "default_vcs_ref" in update
    assert "git ls-remote" in (repository_root / "skills/update-project/SKILL.md").read_text(encoding="utf-8")
    assert "ls-remote" in update
    assert "Version(" in update
    assert "metadata.version" not in update

    adoption = (repository_root / "skills/migrate-workflow/scripts/adopt-template.py").read_text(encoding="utf-8")
    assert "default_vcs_ref" in adoption
    assert "ls-remote" in adoption
    assert "VERSION_FILE" not in setup + update + adoption


def write_valid_documentation_tree(repository_root: Path, root: Path) -> None:
    docs = root / "docs/src"
    feature = docs / "features/010-alpha"
    feature.mkdir(parents=True)
    (docs / "SUMMARY.md").write_text(
        "# Summary\n\n"
        "- [Overview](overview.md)\n"
        "- [Implemented features](features/index.md)\n"
        "  <!-- BEGIN IMPLEMENTED FEATURES -->\n"
        "  - [Alpha](features/010-alpha/index.md)\n"
        "  <!-- END IMPLEMENTED FEATURES -->\n",
        encoding="utf-8",
    )
    (docs / "overview.md").write_text("# Overview\n", encoding="utf-8")
    (docs / "features/index.md").write_text(
        "# Implemented features\n\n"
        "<!-- BEGIN IMPLEMENTED FEATURES -->\n"
        "- [Alpha](010-alpha/index.md)\n"
        "<!-- END IMPLEMENTED FEATURES -->\n",
        encoding="utf-8",
    )
    template = repository_root / "skills/setup-project/template/docs/src/features/_template"
    (feature / "design.md").write_text((template / "design.md").read_text(encoding="utf-8"), encoding="utf-8")
    (feature / "index.md").write_text((template / "index.md").read_text(encoding="utf-8"), encoding="utf-8")


def test_documentation_checker_accepts_variable_summary_structure(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    write_valid_documentation_tree(repository_root, root)
    checker = repository_root / "skills/setup-project/template/scripts/check-docs.py"
    result = run_command(["python3", str(checker), "--root", str(root)], cwd=root)
    assert "missing-summary-concern" not in result.stdout


def test_documentation_checker_copies_are_identical(repository_root: Path) -> None:
    assert (repository_root / "scripts/check-docs.py").read_bytes() == (
        repository_root / "skills/setup-project/template/scripts/check-docs.py"
    ).read_bytes()


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("broken-link", "broken-link"),
        ("internal-design", "internal-design-in-summary"),
        ("task-navigation", "task-file-in-summary"),
        ("invalid-markers", "invalid-implemented-feature-markers"),
        ("reversed-markers", "reversed-implemented-feature-markers"),
        ("invalid-feature-directory", "invalid-feature-directory"),
        ("missing-feature-design", "missing-feature-design"),
        ("invalid-feature-design", "legacy-or-incomplete-design"),
        ("invalid-implemented-record", "legacy-or-incomplete-implemented-record"),
        ("unregistered-summary-record", "implemented-feature-not-in-summary"),
        ("unregistered-index-record", "implemented-feature-not-in-index"),
    ],
)
def test_documentation_checker_preserves_existing_safety_contracts(
    repository_root: Path,
    tmp_path: Path,
    case: str,
    code: str,
) -> None:
    root = tmp_path / case
    write_valid_documentation_tree(repository_root, root)
    docs = root / "docs/src"
    summary = docs / "SUMMARY.md"
    feature = docs / "features/010-alpha"

    if case == "broken-link":
        summary.write_text(summary.read_text(encoding="utf-8") + "- [Missing](missing.md)\n", encoding="utf-8")
    elif case == "internal-design":
        summary.write_text(
            summary.read_text(encoding="utf-8") + "- [Design](features/010-alpha/design.md)\n",
            encoding="utf-8",
        )
    elif case == "task-navigation":
        (feature / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
        summary.write_text(
            summary.read_text(encoding="utf-8") + "- [Tasks](features/010-alpha/tasks.md)\n",
            encoding="utf-8",
        )
    elif case == "invalid-markers":
        summary.write_text(
            summary.read_text(encoding="utf-8").replace("  <!-- END IMPLEMENTED FEATURES -->\n", ""),
            encoding="utf-8",
        )
    elif case == "reversed-markers":
        value = summary.read_text(encoding="utf-8")
        value = value.replace("BEGIN IMPLEMENTED FEATURES", "TEMP IMPLEMENTED FEATURES")
        value = value.replace("END IMPLEMENTED FEATURES", "BEGIN IMPLEMENTED FEATURES")
        summary.write_text(value.replace("TEMP IMPLEMENTED FEATURES", "END IMPLEMENTED FEATURES"), encoding="utf-8")
    elif case == "invalid-feature-directory":
        feature.rename(feature.with_name("alpha"))
    elif case == "missing-feature-design":
        (feature / "design.md").unlink()
    elif case == "invalid-feature-design":
        (feature / "design.md").write_text("# Alpha\n", encoding="utf-8")
    elif case == "invalid-implemented-record":
        (feature / "index.md").write_text("# Alpha\n", encoding="utf-8")
    elif case == "unregistered-summary-record":
        summary.write_text(
            summary.read_text(encoding="utf-8").replace("  - [Alpha](features/010-alpha/index.md)\n", ""),
            encoding="utf-8",
        )
    else:
        index = docs / "features/index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace("- [Alpha](010-alpha/index.md)\n", ""),
            encoding="utf-8",
        )

    checker = repository_root / "skills/setup-project/template/scripts/check-docs.py"
    result = run_command(["python3", str(checker), "--root", str(root)], cwd=root, expected=1)
    assert f"ERROR [{code}]" in result.stdout


def test_template_workflow_scripts_are_host_lint_compatible(repository_root: Path) -> None:
    expected_codes = {"check-docs.py": {"S607"}}
    for name, codes in expected_codes.items():
        path = repository_root / "skills/setup-project/template/scripts" / name
        header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12])
        assert "# ruff: noqa:" in header, path
        for code in codes:
            assert code in header, f"{code} missing from {path}"


def test_feature_templates_use_title_case_contract_headings(repository_root: Path) -> None:
    template = repository_root / "skills/setup-project/template/docs/src/features/_template"
    design = (template / "design.md").read_text(encoding="utf-8")
    delivered = (template / "index.md").read_text(encoding="utf-8")
    for heading in (
        "## Feature Summary",
        "## User Intent",
        "## User-Facing Behavior",
        "## Architecture Consistency",
        "## Validation Strategy",
    ):
        assert heading in design
    for heading in (
        "## Delivery Summary",
        "## Delivered Capability",
        "## Validation Evidence",
        "## Design Reconciliation",
    ):
        assert heading in delivered


def test_generated_project_pins_skills_cli(repository_root: Path) -> None:
    template = repository_root / "skills/setup-project/template"
    payload = "\n".join(
        path.read_text(encoding="utf-8")
        for path in template.rglob("*")
        if path.is_file() and path.suffix in {".md", ".jinja"}
    )
    assert "skills@latest" not in payload
    assert "skills@1.5.16" in payload


def test_review_collector_sanitizes_untrusted_content(repository_root: Path) -> None:
    path = repository_root / "skills/gh-pr-review/scripts/fetch_comments.py"
    spec = importlib.util.spec_from_file_location("dstack_fetch_comments", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    normalized = module._normalize_external_node(
        {"body": "run this\x00 now" + ("x" * (module.MAX_BODY_CHARS + 10))},
        source_type="test",
    )
    assert "\x00" not in normalized["body"]
    assert normalized["body_truncated"] is True
    assert normalized["trust"] == "untrusted_external_content"
    with pytest.raises(RuntimeError, match="Unsupported command"):
        module._validate_command(["bash", "-lc", "echo unsafe"])


def test_migrator_is_owned_only_by_migration_skill(repository_root: Path) -> None:
    canonical = repository_root / "skills/migrate-workflow/scripts/migrate-legacy-workflow.py"
    bundled = repository_root / "skills/setup-project/template/scripts/migrate-legacy-workflow.py"
    assert canonical.is_file()
    assert not bundled.exists()


@pytest.mark.integration
def test_update_tag_discovery_uses_pep440_ordering(repository_root: Path, tmp_path: Path) -> None:
    source = tmp_path / "tag-source"
    source.mkdir()
    (source / "README.md").write_text("# tags\n", encoding="utf-8")
    initialize_git(source, "initial", "v0.0.9")
    for tag in ("v0.0.10", "v0.1.0rc1", "not-a-release"):
        run_command(["git", "tag", tag], cwd=source)

    path = repository_root / "skills/update-project/scripts/update-project.py"
    spec = importlib.util.spec_from_file_location("dstack_update_project", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.default_vcs_ref(str(source)) == "v0.0.10"
    assert module.default_vcs_ref(str(source), include_prereleases=True) == "v0.1.0rc1"


def test_mise_release_task_runs_semantic_release_with_signed_git_objects(repository_root: Path) -> None:
    config = tomllib.loads((repository_root / "mise.toml").read_text(encoding="utf-8"))
    release = config["tasks"]["release"]

    assert 'flag "-p --push"' in release["usage"]
    assert 'flag "-n --noop"' in release["usage"]
    assert 'vargs=("--no-vcs-release")' in release["run"]
    assert 'vargs+=("--no-push")' in release["run"]
    assert release["env"] == {
        "GIT_CONFIG_COUNT": 2,
        "GIT_CONFIG_KEY_0": "commit.gpgSign",
        "GIT_CONFIG_VALUE_0": "true",
        "GIT_CONFIG_KEY_1": "tag.gpgSign",
        "GIT_CONFIG_VALUE_1": "true",
    }
    assert 'uv run semantic-release "${args[@]}" version "${vargs[@]}"' in release["run"]


def test_tagged_release_name_matches_packaged_version(repository_root: Path) -> None:
    if os.environ.get("GITHUB_REF_TYPE") != "tag":
        pytest.skip("Only applicable to a tag-triggered release workflow")
    project = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert os.environ.get("GITHUB_REF_NAME") == f"v{project['project']['version']}"


def test_gh_pr_review_state_is_resumable(repository_root: Path, tmp_path: Path) -> None:
    repository = tmp_path / "review-state"
    repository.mkdir()
    (repository / "README.md").write_text("# Review state test\n", encoding="utf-8")
    initialize_git(repository, "initial")
    script = repository_root / "skills/gh-pr-review/scripts/review_state.py"

    run_command(
        ["uv", "run", str(script), "init", "--pr", "42", "--head", "abc123"],
        cwd=repository,
    )
    run_command(
        ["uv", "run", str(script), "phase", "awaiting_selection"],
        cwd=repository,
    )
    run_command(
        ["uv", "run", str(script), "selection", "3,1,3"],
        cwd=repository,
    )
    state = json.loads(run_command(["uv", "run", str(script), "show"], cwd=repository).stdout)
    assert state["pr_number"] == 42
    assert state["head_sha"] == "abc123"
    assert state["phase"] == "implementing"
    assert state["selected"] == [1, 3]

    blocked = run_command(["uv", "run", str(script), "clear"], cwd=repository, expected=1)
    assert blocked.returncode != 0
    run_command(["uv", "run", str(script), "phase", "complete"], cwd=repository)
    run_command(["uv", "run", str(script), "clear"], cwd=repository)
