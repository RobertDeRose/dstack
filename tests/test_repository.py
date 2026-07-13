"""Repository, skill-package, Copier, and Skills CLI validation tests."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

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
]

REQUIRED_TEMPLATE_FILES = (
    ".beads/formulas/feature-lifecycle.formula.toml",
    ".gitignore.jinja",
    "[[ _copier_conf.answers_file ]].jinja",
    "[% if include_readme %]README.md[% endif %].jinja",
    "AGENTS.md.jinja",
    "docs/book.toml.jinja",
    "docs/src/SUMMARY.md.jinja",
    "docs/src/features/_template/design.md",
    "docs/src/features/_template/index.md",
    "scripts/check-docs.py",
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
    "features/_template/design.md",
    "features/_template/index.md",
    "features/index.md",
    "introduction/documentation-conventions.md",
    "introduction/project-overview.md",
    "planned-features.md",
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
    for relative in FORBIDDEN_NEW_PROJECT_TEMPLATE_FILES:
        assert not (repository_root / "skills/setup-project/template" / relative).exists()

    implementation = skill("implement-feature")
    assert "git rev-parse HEAD" in implementation
    assert "resolve-feature.py --next" not in implementation
    assert "feat/<num>-<slug>" in implementation
    assert "specific no-commit justification" in implementation
    assert "<implementation-epic-id>" not in implementation

    closeout = skill("close-feature")
    assert "resolve-feature.py --next" not in closeout
    assert "feat/<num>-<slug>" in closeout
    assert "do not reuse pre-fix results" in " ".join(closeout.casefold().split())
    assert "scripts/check-docs.py" in closeout

    audit = skill("audit-project")
    assert "Do not report a correction as verified from a pre-fix result" in audit

    start = skill("start-feature")
    assert "git show-ref --verify --quiet refs/heads/feat/<num>-<slug>" in start
    assert "Branch exists but has no worktree" in start
    assert "<implementation-epic-id>" not in start
    assert "resolve-feature.py" in start
    assert "canonical" in start.casefold()

    update = skill("update-project")
    assert "Run /migrate-workflow now?" in update
    assert "--preflight --json" in update
    assert "path-accounting ledger" in update
    assert "every changed path" in update.casefold()
    assert (
        "readiness to resume feature work, which must be false while migration is required or a changed path is "
        "unclassified" in " ".join(update.split())
    )

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

        answers = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))
        expected_brief = {**SETUP_BRIEF, "project_kind": kind}
        assert {field: answers[field] for field in expected_brief} == expected_brief
        assert {field: payload[field] for field in expected_brief} == expected_brief
        assert answers["project_name"] == PUNCTUATED_PROJECT_NAME
        assert payload["readme_created"] is include_readme
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

        book = tomllib.loads((project / "docs/book.toml").read_text(encoding="utf-8"))["book"]
        assert book["title"] == PUNCTUATED_PROJECT_NAME
        assert book["description"] == SETUP_BRIEF["project_purpose"]

        summary = (docs / "SUMMARY.md").read_text(encoding="utf-8")
        assert re.findall(r"\]\(([^)]+)\)", summary) == [
            "introduction/project-overview.md",
            "introduction/documentation-conventions.md",
            "development/feature-lifecycle.md",
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
    commit_repository(project, "Project-specific documentation")

    (tagged_template_source / "skills/setup-project/template/.dstack-release.jinja").write_text(
        "v0.0.2\n", encoding="utf-8"
    )
    commit_repository(tagged_template_source, "dstack v0.0.2", "v0.0.2")

    update = tagged_template_source / "skills/update-project/scripts/update-project.py"
    run_command(
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
    )

    assert (project / ".dstack-release").read_text(encoding="utf-8") == "v0.0.2\n"
    assert "Project-owned update." in project_overview.read_text(encoding="utf-8")


@pytest.mark.integration
def test_update_project_uses_latest_release_tag_ignores_venv_and_uses_portable_beads_checks(
    tagged_template_source: Path,
    tmp_path: Path,
) -> None:
    project = tmp_path / "example-project"
    setup_generated_project(tagged_template_source, project)
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
    assert payload["outstanding"] == []
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
