from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_and_resources() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    assert package["name"] == "dstack"
    assert package["version"] == "0.4.3"
    assert package["pi"]["skills"] == ["./skills"]
    assert package["pi"]["prompts"] == ["./prompts"]


def test_mdbook_is_pinned_and_validated_in_ci() -> None:
    mise = tomllib.loads((ROOT / "mise.toml").read_text())
    assert mise["tools"]["aqua:rust-lang/mdBook"] == "0.5.3"
    workflow = (ROOT / ".github/workflows/tests.yml").read_text()
    assert "docs validate" in workflow
    conventions = (ROOT / "docs/src/development/documentation.md").read_text()
    for phrase in (
        "Put documentation where a reader would look",
        "End users and operators",
        "Developers and reviewers",
        "Future agents and auditors",
        "SUMMARY.md",
        "No separate agent",
    ):
        assert phrase in conventions


def test_all_skill_and_prompt_frontmatter_parses() -> None:
    for path in [*ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("prompts/*.md")]:
        text = path.read_text()
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert isinstance(yaml.safe_load(frontmatter), dict)


def test_feature_planning_is_one_lossless_beads_only_methodology() -> None:
    prompt = (ROOT / "prompts/plan-feature.md").read_text()
    alias = (ROOT / "prompts/plan-features.md").read_text()
    skill = (ROOT / "skills/dstack-beads-plan-feature/SKILL.md").read_text()

    assert "dstack-beads-plan-feature" in prompt
    assert "dstack-beads-plan-feature" in alias
    assert "deprecated" in alias.casefold()
    assert not (ROOT / "skills/dstack-beads-plan-features").exists()

    compact = " ".join(skill.split())
    for phrase in (
        "relevant repository context",
        "consequential ambiguity",
        "alternatives",
        "Decisions and rationale",
        "Failure and compatibility expectations",
        "Documentation expectations",
        "Deferred questions",
        "bd create",
        "bd update",
        "--title",
        "--body-file",
        "--acceptance",
        "--priority",
        "bd show",
        "bd dep add",
        "bd dep remove",
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
    review = " ".join((ROOT / "skills/dstack-beads-review-feature-spec/SKILL.md").read_text().split())

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
    assert review.index("feature scaffold-design") < review.index("feature inspect")
    assert review.index("feature inspect") < review.index("explicit human authorization")
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
        assert implementation.is_file()
        assert f"]({implementation.relative_to(source).as_posix()})" in summary
        assert f"]({implementation.relative_to(source / 'features').as_posix()})" in feature_index


def test_core_principles_and_architecture_are_first_class_docs() -> None:
    principles = (ROOT / "docs/src/development/index.md").read_text()
    architecture = (ROOT / "docs/src/architecture/index.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    for phrase in (
        "KISS and YAGNI",
        "Never store Git commit hashes in Beads",
        "Documentation is not workflow state",
    ):
        assert phrase in principles
    assert "stateless dstackctl" in architecture
    assert "docs/src/development/index.md" in agents
    assert "post-merge bookkeeping commit" in agents


def test_active_instructions_preserve_explicit_delivery_recovery() -> None:
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "skills/dstack-beads-core/SKILL.md",
        ROOT / "skills/dstack-beads-close-feature/SKILL.md",
        ROOT / "skills/dstack-beads-project-alignment-land/SKILL.md",
    ]
    for path in paths:
        text = " ".join(path.read_text().split())
        assert "During normal delivery" in text
        assert "must not mutate" in text
        assert "bookkeeping commit" in text
        assert "Explicit user-authorized recovery" in text
        assert "separate native Git operation" in text


def test_feature_quality_contract_is_shared_across_docs_and_skills() -> None:
    principles = (ROOT / "docs/src/development/index.md").read_text()
    plan = (ROOT / "skills/dstack-beads-plan-feature/SKILL.md").read_text()
    review = (ROOT / "skills/dstack-beads-review-feature-spec/SKILL.md").read_text()
    implement = (ROOT / "skills/dstack-beads-implement-feature/SKILL.md").read_text()
    close = (ROOT / "skills/dstack-beads-close-feature/SKILL.md").read_text()

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
    for phrase in ("externally meaningful behavior", "failure handling", "Documentation impact"):
        assert phrase in " ".join(close.split())


def test_public_feature_lifecycle_has_no_start_methodology() -> None:
    assert not (ROOT / "prompts/start-feature.md").exists()
    assert not (ROOT / "skills/dstack-beads-start-feature").exists()

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
        ROOT / "skills/dstack-beads-review-feature-spec/SKILL.md",
        ROOT / "skills/dstack-beads-implement-feature/SKILL.md",
        ROOT / "skills/dstack-beads-close-feature/SKILL.md",
    ):
        assert "/start-feature" not in path.read_text()

    cleanup = (ROOT / "scripts/cleanup-legacy-pi-skills.py").read_text()
    assert '"start-feature"' in cleanup
    assert '"plan-feature"' in cleanup

    cli = (ROOT / "skills/dstack-beads-core/scripts/dstack_cli.py").read_text()
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
    implement = " ".join((ROOT / "skills/dstack-beads-implement-feature/SKILL.md").read_text().split())
    close = " ".join((ROOT / "skills/dstack-beads-close-feature/SKILL.md").read_text().split())

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
        ROOT / "skills/dstack-beads-review-feature-spec/SKILL.md",
        ROOT / "skills/dstack-beads-implement-feature/SKILL.md",
        ROOT / "skills/dstack-beads-close-feature/SKILL.md",
    ]
    for path in skill_paths:
        text = " ".join(path.read_text().split())
        assert "pass" in text.casefold() and "explicit" in text.casefold()
        assert "worktree" in text.casefold()


def test_skills_are_short_and_decision_oriented() -> None:
    for path in ROOT.glob("skills/*/SKILL.md"):
        lines = path.read_text().splitlines()
        assert len(lines) <= 100, f"{path} is {len(lines)} lines"
        assert "Read the `dstack-beads-core` skill and every core reference" not in path.read_text()


def test_no_git_sha_mapping_or_shadow_state_contract() -> None:
    text = "\n".join(path.read_text() for path in ROOT.glob("skills/**/*.md"))
    assert "external_ref=git" not in text
    assert "reviewer replacement" not in text.casefold()
    assert "dstack:delivery-ready" not in text
    assert "tasks.md" not in text or "Do not create `tasks.md`" in text
    assert not (ROOT / "skills/dstack-beads-core/scripts/git_evidence.py").exists()
    setup = (ROOT / "skills/dstack-beads-core/scripts/setup.py").read_text()
    assert "DSTACK_FAKE_BD_STATE" not in setup


def test_public_help_is_mechanical_and_side_effect_free() -> None:
    controller_path = ROOT / "skills/dstack-beads-core/scripts/dstackctl.py"
    sys.path.insert(0, str(controller_path.parent))
    spec = importlib.util.spec_from_file_location("dstackctl_help", controller_path)
    assert spec and spec.loader
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    parser = controller.build_parser()

    parsers: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []

    def collect(current: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        parsers.append((path, current))
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    collect(child, (*path, name))

    collect(parser, ())
    before = subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        text=True,
    )
    for _, current in parsers:
        assert current.description and "mechanics" in current.description.casefold()
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction) or action.dest == "help":
                continue
            assert action.help and action.help != argparse.SUPPRESS
    result = subprocess.run(
        [sys.executable, "-S", str(controller_path), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "mechanics" in result.stdout.casefold()
    after = subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        text=True,
    )
    assert after == before


def test_uv_run_has_default_development_dependencies() -> None:
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = set(project["dependency-groups"]["dev"])
    assert any(item.startswith("pytest") for item in dependencies)
    assert any(item.startswith("PyYAML") for item in dependencies)


def test_mise_installs_supported_beads() -> None:
    import tomllib

    config = tomllib.loads((ROOT / "mise.toml").read_text())
    assert config["tools"]["aqua:gastownhall/beads"] == "1.2.2"


def test_ci_runs_fast_and_real_suites_as_separate_jobs() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    jobs = workflow["jobs"]
    assert set(jobs) == {"fast", "real-beads"}
    for job in jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
    assert "uv run pytest -q -rs" in jobs["fast"]["steps"][-1]["run"]

    acceptance = jobs["real-beads"]
    assert acceptance["strategy"]["matrix"]["suite"] == [
        "test_bd_contract.py",
        "test_feature_smoke.py",
    ]
    assert "env" not in acceptance
    assert any(step.get("uses", "").startswith("jdx/mise-action@") for step in acceptance["steps"])
    assert "tests/acceptance/${{ matrix.suite }}" in acceptance["steps"][-1]["run"]


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
    commands = (ROOT / "skills/dstack-beads-core/scripts/dstack_commands.py").read_text()
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
