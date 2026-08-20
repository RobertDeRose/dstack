from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_and_resources() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    assert package["name"] == "dstack"
    assert package["version"] == "0.4.3"
    assert package["pi"]["skills"] == ["./skills"]
    assert package["pi"]["prompts"] == ["./prompts"]


def test_all_skill_and_prompt_frontmatter_parses() -> None:
    for path in [*ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("prompts/*.md")]:
        text = path.read_text()
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert isinstance(yaml.safe_load(frontmatter), dict)


def test_core_principles_and_architecture_are_first_class_docs() -> None:
    principles = (ROOT / "docs/core-principles.md").read_text()
    architecture = (ROOT / "docs/architecture.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    for phrase in (
        "KISS and YAGNI",
        "Never store Git commit hashes in Beads",
        "Documentation is not workflow state",
    ):
        assert phrase in principles
    assert "stateless dstackctl" in architecture
    assert "docs/core-principles.md" in agents
    assert "post-merge bookkeeping commit" in agents


def test_feature_quality_contract_is_shared_across_docs_and_skills() -> None:
    principles = (ROOT / "docs/core-principles.md").read_text()
    start = (ROOT / "skills/dstack-beads-start-feature/SKILL.md").read_text()
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
    for phrase in ("scaffold-design", "observable outcomes", "Documentation impact"):
        assert phrase in " ".join(start.split())
    for phrase in ("happy path", "failure recovery", "Documentation impact"):
        assert phrase in " ".join(review.split())
    for phrase in ("externally meaningful behavior", "failure handling", "Documentation impact"):
        assert phrase in " ".join(implement.split())
    for phrase in ("externally meaningful behavior", "failure handling", "Documentation impact"):
        assert phrase in " ".join(close.split())


def test_feature_lifecycle_skills_pass_explicit_feature_context() -> None:
    skill_paths = [
        ROOT / "skills/dstack-beads-start-feature/SKILL.md",
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
