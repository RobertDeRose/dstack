from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_and_resources() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["name"] == "dstack"
    assert project["project"]["version"] == "0.5.0"
    assert project["project"]["scripts"]["dstack"] == "dstack.cli:main"
    assert project["build-system"]["build-backend"] == "setuptools.build_meta"
    assert (ROOT / "dstack/cli.py").is_file()
    assert (ROOT / "dstack/installer.py").is_file()
    assert (ROOT / "dstack/assets/APPEND_SYSTEM.md").is_file()
    assert not (ROOT / "bin/dstack").exists()
    assert not (ROOT / "package.json").exists()
    assert not (ROOT / "skills/dstack-beads-core").exists()
    lock = (ROOT / "uv.lock").read_text()
    assert 'name = "dstack"' in lock


def test_cli_is_a_normal_importable_python_package() -> None:
    from dstack import cli

    assert cli.main(["--help"]) == 0
    assert cli.main(["--version"]) == 0


def test_release_check_validates_installed_wheel_assets() -> None:
    script = (ROOT / "scripts/release-check.sh").read_text()
    assert 'install_skills --agent-dir "$agent_dir"' in script
    assert "from dstack.formula import load_formula" in script
    assert "dstack-beads-review-feature-spec" in script
    assert "review-feature-spec.md" in script
    assert "APPEND_SYSTEM.md" in script


def test_all_skill_and_prompt_frontmatter_parses() -> None:
    for path in [*(ROOT / "dstack/assets/skills").glob("*/SKILL.md"), *(ROOT / "dstack/assets/prompts").glob("*.md")]:
        text = path.read_text()
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert isinstance(yaml.safe_load(frontmatter), dict)
        if path.name == "SKILL.md":
            assert "dstackctl.py" not in text


def test_feature_planning_is_one_lossless_beads_only_methodology() -> None:
    prompt = (ROOT / "dstack/assets/prompts/plan-feature.md").read_text()
    alias = (ROOT / "dstack/assets/prompts/plan-features.md").read_text()
    skill = (ROOT / "dstack/assets/skills/dstack-beads-plan-feature/SKILL.md").read_text()

    assert "dstack-beads-plan-feature" in prompt
    assert "dstack-beads-plan-feature" in alias
    assert "deprecated" in alias.casefold()
    assert not (ROOT / "dstack/assets/skills/dstack-beads-plan-features").exists()

    compact = " ".join(skill.split())
    for phrase in (
        "relevant repository context",
        "consequential ambiguity",
        "alternatives",
        "Decisions and rationale",
        "Failure and compatibility expectations",
        "Documentation expectations",
        "Deferred questions",
        "feature plan",
        "--title",
        "--body-file",
        "--acceptance",
        "--priority",
        "open planned feature",
        "current molecule",
        "stable",
        "/review-feature-spec",
    ):
        assert phrase in compact
    for forbidden in (
        "feature initialize",
        "scaffold-design",
        "add-task",
        "git commit",
    ):
        assert forbidden not in compact


def test_review_materializes_and_authorizes_repository_aware_specification() -> None:
    review = " ".join((ROOT / "dstack/assets/skills/dstack-beads-review-feature-spec/SKILL.md").read_text().split())

    for phrase in (
        "feature initialize",
        "feature scaffold-design",
        "feature claim-spec",
        "feature inspect",
        "canonical design",
        "architecture, source, tests",
        "observable outcomes",
        "feature add-task",
        "native `bd update`",
        "native `bd dep add`",
        "native `bd dep remove`",
        "explicit human authorization",
        "invocation itself is not authorization",
        "feature approve-spec",
        "already initialized",
    ):
        assert phrase in review
    assert review.index("feature initialize") < review.index("feature claim-spec")
    assert review.index("feature claim-spec") < review.index("feature scaffold-design")
    assert review.index("feature scaffold-design") < review.rindex("feature inspect")
    assert review.rindex("feature inspect") < review.index("explicit human authorization")
    assert review.index("explicit human authorization") < review.index("feature approve-spec")


def test_mdbook_documentation_layout() -> None:
    docs = ROOT / "docs"
    source = docs / "src"
    assert (docs / "book.toml").is_file()
    assert (source / "SUMMARY.md").is_file()
    assert all(path.is_relative_to(source) for path in docs.rglob("*.md"))
    assert not (docs / "features").exists()
    assert list((source / "features").glob("*/design.md"))

    summary = (source / "SUMMARY.md").read_text()
    feature_index = (source / "features/index.md").read_text()
    for target in re.findall(r"\]\(([^)]+\.md)\)", summary):
        assert (source / target).is_file(), target
    assert summary.count("- [Feature Records](features/index.md)") == 1
    designs = list((source / "features").glob("*/design.md"))
    for design in designs:
        summary_target = design.relative_to(source).as_posix()
        assert f"]({summary_target})" in summary
        implementation = design.with_name("index.md")
        if not implementation.is_file():
            assert f"]({summary_target})" in summary
            continue
        assert f"]({implementation.relative_to(source).as_posix()})" in summary
        assert f"]({implementation.relative_to(source / 'features').as_posix()})" in feature_index


def test_core_principles_and_architecture_are_first_class_docs() -> None:
    principles = (ROOT / "docs/src/development/index.md").read_text()
    architecture = (ROOT / "docs/src/architecture/index.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    system_additive = (ROOT / "dstack/assets/APPEND_SYSTEM.md").read_text()
    for phrase in ("KISS and YAGNI", "Documentation is not workflow state"):
        assert phrase in principles
    for contract in (principles, agents, system_additive):
        normalized = " ".join(contract.split()).casefold()
        assert "formulas define how dstack creates" in normalized
    assert "Git owns code" in system_additive
    assert "project-alignment audit" in architecture
    assert "baseline_commit" not in " ".join(architecture.split())
    assert "docs/src/development/index.md" in agents
    assert "post-merge bookkeeping commit" in agents


def test_alignment_review_skill_uses_beads_native_authority() -> None:
    skill = (ROOT / "dstack/assets/skills/dstack-beads-project-alignment-review/SKILL.md").read_text()
    documentation = (ROOT / "docs/src/development/documentation.md").read_text()
    compact = " ".join(skill.split())
    for required in (
        "current specifications",
        "alignment add-correction",
        "documentation impact",
        "alignment finish-plan AUDIT --summary-file",
        "do not create a packet",
    ):
        assert required.casefold() in compact.casefold()
    for obsolete in ("dstack.alignment-plan/", "PLAN.json", "--plan-file", "accepted_corrections"):
        assert obsolete not in skill
    normalized_docs = " ".join(documentation.split())
    assert "Alignment review authority is Beads-native" in documentation
    assert "does not create an external plan packet" in normalized_docs
    assert "Documentation is deferred to the final closeout or landing".casefold() in normalized_docs.casefold()


def test_active_instructions_preserve_explicit_delivery_recovery() -> None:
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "dstack/assets/APPEND_SYSTEM.md",
        ROOT / "dstack/assets/skills/dstack-beads-close-feature/SKILL.md",
        ROOT / "dstack/assets/skills/dstack-beads-project-alignment-land/SKILL.md",
    ]
    combined = " ".join(path.read_text() for path in paths)
    assert "During normal delivery" in combined
    assert "bookkeeping commit" in combined
    assert "user-authorized recovery" in combined


def test_feature_quality_contract_is_shared_across_docs_and_skills() -> None:
    principles = (ROOT / "docs/src/development/index.md").read_text()
    plan = (ROOT / "dstack/assets/skills/dstack-beads-plan-feature/SKILL.md").read_text()
    review = (ROOT / "dstack/assets/skills/dstack-beads-review-feature-spec/SKILL.md").read_text()
    implement = (ROOT / "dstack/assets/skills/dstack-beads-implement-feature/SKILL.md").read_text()
    close = (ROOT / "dstack/assets/skills/dstack-beads-close-feature/SKILL.md").read_text()

    for phrase in (
        "Feature design quality contract",
        "user/developer outcome",
        "observable behavior",
        "Tests prove externally meaningful behavior",
        "End user/operator",
        "Developer/reviewer",
        "Future agent/auditor",
        "coverage-percentage gate",
    ):
        assert phrase in principles
    for phrase in ("outcome and why", "observable success", "documentation expectations"):
        assert phrase in " ".join(plan.split())
    for phrase in (
        "happy path",
        "failure recovery",
        "Documentation impact",
        "local Markdown links",
    ):
        assert phrase in " ".join(review.split())
    for phrase in ("externally meaningful behavior", "failure handling", "Documentation impact"):
        assert phrase in " ".join(implement.split())
    assert "Defer durable documentation to closeout" in " ".join(implement.split())
    for phrase in ("externally meaningful behavior", "failure handling", "Documentation impact"):
        assert phrase in " ".join(close.split())
    assert "sole final reconciliation" in " ".join(close.split())


def test_public_feature_lifecycle_has_no_start_methodology() -> None:
    assert not (ROOT / "dstack/assets/prompts/start-feature.md").exists()
    assert not (ROOT / "dstack/assets/skills/dstack-beads-start-feature").exists()

    for path in (ROOT / "README.md", ROOT / "docs/src/development/feature-lifecycle.md"):
        text = path.read_text()
        for command in (
            "/plan-feature",
            "/review-feature-spec",
            "/implement-feature",
            "/close-feature",
        ):
            assert command in text
        assert "/start-feature" not in text

    for path in (
        ROOT / "dstack/assets/skills/dstack-beads-review-feature-spec/SKILL.md",
        ROOT / "dstack/assets/skills/dstack-beads-implement-feature/SKILL.md",
        ROOT / "dstack/assets/skills/dstack-beads-close-feature/SKILL.md",
    ):
        assert "/start-feature" not in path.read_text()

    installer = (ROOT / "dstack/installer.py").read_text()
    assert '"start-feature"' in installer
    assert '"plan-feature"' in installer

    cli = (ROOT / "dstack/cli.py").read_text()
    for operation in ("initialize", "scaffold-design", "add-task"):
        assert f'feature_sub, "{operation}"' in cli

    authority = " ".join(
        (
            (ROOT / "docs/src/development/index.md").read_text() + (ROOT / "docs/src/architecture/index.md").read_text()
        ).split()
    )
    assert "planned feature intent" in authority
    assert "accepted product and architecture" in authority


def test_feature_execution_stops_and_validation_fail_closed() -> None:
    implement = " ".join((ROOT / "dstack/assets/skills/dstack-beads-implement-feature/SKILL.md").read_text().split())
    close = " ".join((ROOT / "dstack/assets/skills/dstack-beads-close-feature/SKILL.md").read_text().split())

    for phrase in (
        "Review the complete candidate diff",
        "git commit --bead",
        "evidence commits",
        "feature finish-task",
    ):
        assert phrase in implement
    assert implement.index("Review the complete candidate diff") < implement.index("git commit --bead")
    assert implement.index("git commit --bead") < implement.index("evidence commits")
    assert implement.index("evidence commits") < implement.index("feature finish-task")
    for phrase in (
        "fails",
        "times out",
        "is interrupted",
        "wrong scope",
        "unexpectedly skips",
        "weaker coverage",
        "report the exact command",
    ):
        assert phrase in implement
    assert "`--all` repeats only over native ready implementation tasks" in implement
    assert "focused validation" in implement
    assert "Do not run `feature finish-workstream`" in implement
    assert "those require a separate user command" in implement
    assert "feature finish-workstream" in close
    assert "feature scaffold-reconciliation" in close
    assert "docs validate" in close
    assert "full/release validation" in close
    assert "stop before `feature finish-closeout` or delivery" in close

    workflow = " ".join((ROOT / "docs/src/development/feature-lifecycle.md").read_text().split())
    assert "fresh agent session" in workflow
    assert "Beads, Git, and durable repository documentation alone" in workflow


def test_feature_lifecycle_skills_pass_explicit_feature_context() -> None:
    skill_paths = [
        ROOT / "dstack/assets/skills/dstack-beads-review-feature-spec/SKILL.md",
        ROOT / "dstack/assets/skills/dstack-beads-implement-feature/SKILL.md",
        ROOT / "dstack/assets/skills/dstack-beads-close-feature/SKILL.md",
    ]
    for path in skill_paths:
        text = " ".join(path.read_text().split())
        assert "pass" in text.casefold() and "explicit" in text.casefold()
        assert "worktree" in text.casefold()


def test_skills_are_short_and_decision_oriented() -> None:
    for path in (ROOT / "dstack/assets/skills").glob("*/SKILL.md"):
        lines = path.read_text().splitlines()
        assert len(lines) <= 100, f"{path} is {len(lines)} lines"
        assert "Read the `dstack-beads-core` skill and every core reference" not in path.read_text()


def test_no_git_sha_mapping_or_shadow_state_contract() -> None:
    text = "\n".join(path.read_text() for path in (ROOT / "dstack/assets/skills").glob("**/*.md"))
    assert "external_ref=git" not in text
    assert "reviewer replacement" not in text.casefold()
    assert "dstack:delivery-ready" not in text
    assert "tasks.md" not in text or "Do not create `tasks.md`" in text
    assert not (ROOT / "dstack/git_evidence.py").exists()
    assert not (ROOT / "dstack/setup.py").exists()
    assert not (ROOT / "dstack/assets/prompts/setup-project.md").exists()
    assert not (ROOT / "dstack/assets/skills/dstack-beads-setup-project").exists()


def test_public_help_is_mechanical_and_side_effect_free() -> None:
    from dstack import cli

    parser = cli.build_ctl_parser()
    parsers: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []

    def collect(current: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        parsers.append((path, current))
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    collect(child, (*path, name))

    collect(parser, ())
    before = subprocess.check_output(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT, text=True)
    for _, current in parsers:
        assert current.description and "mechanics" in current.description.casefold()
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction) or action.dest == "help":
                continue
            assert action.help and action.help != argparse.SUPPRESS
    assert cli.main(["--help"]) == 0
    after = subprocess.check_output(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT, text=True)
    assert after == before


def test_install_skills_is_available_without_beads_or_mdbook(tmp_path: Path) -> None:
    from dstack import cli

    assert cli.main(["install_skills", "--agent-dir", str(tmp_path / "agent")]) == 0
    assert (tmp_path / "agent/APPEND_SYSTEM.md").is_file()


def test_installed_system_guidance_is_compact() -> None:
    guidance = (ROOT / "dstack/assets/APPEND_SYSTEM.md").read_text()
    assert len(guidance.split()) <= 350
    assert "Central rule:" in guidance
    assert "audit_required" in guidance
    assert "dstack ctl" in guidance


def test_installed_skills_do_not_include_core_skill(tmp_path: Path) -> None:
    from dstack.installer import install_skills

    payload = install_skills(tmp_path / "agent")
    assert "dstack-beads-core" not in payload["skills"]
    assert not (tmp_path / "agent/skills/dstack-beads-core").exists()


def test_delivery_policy_has_no_planned_features_ledger_special_case() -> None:
    source = (ROOT / "dstack/delivery.py").read_text()
    assert "planned-features.md" not in source
    assert "status-only documentation change" not in source


def test_packaged_formulas_are_authoritative_without_tracked_beads_copies() -> None:
    tracked = subprocess.check_output(["git", "ls-files", ".beads/formulas"], cwd=ROOT, text=True)
    assert tracked.strip() == ""
    for name in ("dstack-feature", "dstack-project-alignment"):
        assert (ROOT / "dstack/assets/formulas" / f"{name}.formula.toml").is_file()
    helper = (ROOT / "dstack/formula.py").read_text()
    assert "destination.unlink(missing_ok=True)" in helper


def test_documented_runtime_support_matches_installable_cli() -> None:
    readme = (ROOT / "README.md").read_text()
    compatibility = (ROOT / "docs/src/reference/compatibility.md").read_text()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert "uv tool install" in readme
    assert "dstack install_skills" in readme
    assert "Beads 1.2.2 exactly" in readme
    assert "Python 3.14" in readme
    assert "available on `PATH`" in readme
    assert "package-relative locked runtime" not in readme
    assert "Python: 3.14" in compatibility
    assert project["project"]["requires-python"] == ">=3.14,<3.15"


def test_setup_workflow_is_removed_and_formula_sync_is_controller_owned() -> None:
    readme = " ".join((ROOT / "README.md").read_text().split())
    architecture = " ".join((ROOT / "docs/src/architecture/index.md").read_text().split())
    agents = " ".join((ROOT / "AGENTS.md").read_text().split())
    assert "/setup-project" not in readme
    assert "formulas define how dStack creates and reviews new work".casefold() in readme.casefold()
    assert "Closed historical work is not rewritten" in readme
    assert "No setup workflow" in architecture
    central = "formulas define how dStack creates and reviews new work; they are not schemas that existing work must migrate to"
    assert central.casefold() in agents.casefold()


def test_acceptance_preflight_fails_without_bd(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PATH"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "tests/acceptance"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "real Beads is required: install bd on PATH" in result.stderr


def test_tracked_beads_configuration_contains_no_machine_local_paths() -> None:
    config = "\n".join(
        line for line in (ROOT / ".beads/config.yaml").read_text().splitlines() if not line.lstrip().startswith("#")
    )
    assert not re.search(r'(?m)^\s*[^\n]+:\s*["\']?/(?:Users|home|private|tmp)/', config)
    assert "~/" not in config


def test_feature_scaffolds_cover_operator_developer_and_audit_surfaces() -> None:
    commands = (ROOT / "dstack/commands.py").read_text()
    for phrase in (
        "Planned intent",
        "Planned acceptance",
        "End user and operator",
        "Usage and configuration",
        "Deployment, upgrade, and rollback",
        "Operations, troubleshooting, and recovery",
        "Developer and reviewer",
        "Architecture and structure",
        "Interfaces, contracts, and maintenance",
        "Future auditor",
        "Decisions and rationale",
        "Invariants, regression evidence, and known limitations",
    ):
        assert phrase in commands
