"""End-to-end tests for migration from the legacy Markdown workflow."""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from tests.support import merged_environment, run_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MIGRATOR = REPOSITORY_ROOT / "skills/migrate-workflow/scripts/migrate-legacy-workflow.py"
FORMULA = REPOSITORY_ROOT / "skills/setup-project/template/.beads/formulas/dstack-feature.formula.toml"


def create_legacy_project(root: Path) -> None:
    features = root / "docs/src/features"
    (features / "alpha").mkdir(parents=True)
    (features / "beta").mkdir(parents=True)
    (root / ".beads/formulas").mkdir(parents=True)
    shutil.copyfile(FORMULA, root / ".beads/formulas/dstack-feature.formula.toml")

    (root / "docs/src/planned-features.md").write_text(
        textwrap.dedent(
            """
            # Planned Features

            ## Feature Map

            ### `alpha`

            - Status: Implemented
            - Dependencies: None

            ### `beta`

            - Status: Partially implemented
            - Dependencies: `alpha`
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (root / "docs/src/SUMMARY.md").write_text(
        textwrap.dedent(
            """
            # Summary

            - [Planned Features](planned-features.md)
            - [Implemented Features](features/index.md)
              - [Alpha](features/alpha/index.md)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (features / "index.md").write_text(
        "# Implemented Features\n\n- [Alpha](alpha/index.md)\n",
        encoding="utf-8",
    )
    (root / "docs/src/architecture").mkdir(parents=True)
    (root / "docs/src/architecture/api.md").write_text(
        "# API\n\nThe external endpoint remains `/alpha/v1/items`.\n",
        encoding="utf-8",
    )
    (features / "alpha/design.md").write_text(
        "# Alpha Design\n\n- Status: Reviewed feature specification; ready for implementation.\n",
        encoding="utf-8",
    )
    (features / "alpha/tasks.md").write_text(
        textwrap.dedent(
            """
            # Tasks

            - [x] `T000` Reconcile context
              - Depends on: None
              - Parallel: No
              - Validation: Review design
              - Completion constraint: Design is ready

            - [x] `T010` Implement alpha
              - Depends on: T000
              - Parallel: No
              - Validation: pytest
              - Completion constraint: Tests pass

            - [x] `T999` Reconcile delivery
              - Depends on: T010
              - Parallel: No
              - Validation: Full validation
              - Completion constraint: Docs and code agree
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (features / "alpha/index.md").write_text(
        "# Alpha\n\n{{#include design.md}}\n\n{{#include tasks.md}}\n",
        encoding="utf-8",
    )

    (features / "beta/design.md").write_text(
        "# Beta Design\n\n- Status: In implementation.\n",
        encoding="utf-8",
    )
    (features / "beta/tasks.md").write_text(
        textwrap.dedent(
            """
            # Tasks

            - [x] `T000` Reconcile context
              - Depends on: None
              - Parallel: No
              - Validation: Review design
              - Completion constraint: Design is ready

            - [ ] `T010` Implement beta
              - Depends on: T000
              - Parallel: Yes
              - Validation: pytest
              - Completion constraint: Tests pass

            - [ ] `T999` Reconcile delivery
              - Depends on: T010
              - Parallel: No
              - Validation: Full validation
              - Completion constraint: Docs and code agree
            """
        ).lstrip(),
        encoding="utf-8",
    )


def run_migrator(
    root: Path,
    *arguments: str,
    env: Mapping[str, str] | None = None,
    expected: int = 0,
):
    return run_command(
        [sys.executable, str(MIGRATOR), *arguments, "--root", str(root)],
        cwd=root,
        env=env,
        expected=expected,
    )


def load_manifest(root: Path) -> dict[str, object]:
    return json.loads((root / "migration/workflow-migration.json").read_text(encoding="utf-8"))


@pytest.fixture
def legacy_project(tmp_path: Path) -> Path:
    create_legacy_project(tmp_path)
    return tmp_path


@pytest.fixture
def fake_bd_environment(legacy_project: Path) -> tuple[dict[str, str], Path]:
    bin_dir = legacy_project / "fake-bin"
    state_dir = legacy_project / "fake-bd-state"
    bin_dir.mkdir()
    script = bin_dir / "bd"
    script.write_text(
        textwrap.dedent(
            """
            #!/usr/bin/python3
            from __future__ import annotations

            import json
            import os
            from pathlib import Path
            import sys

            state = Path(os.environ["FAKE_BD_STATE"])
            state.mkdir(parents=True, exist_ok=True)
            args = sys.argv[1:]
            commands = state / "commands.jsonl"
            issues_path = state / "issues.json"
            issues = json.loads(issues_path.read_text()) if issues_path.exists() else {}

            def flag(name: str, default: str = "") -> str:
                try:
                    return args[args.index(name) + 1]
                except (ValueError, IndexError):
                    return default

            def save() -> None:
                issues_path.write_text(json.dumps(issues, indent=2, sort_keys=True) + "\\n")

            with commands.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(args) + "\\n")

            if args and args[0] == "create":
                counter = state / "counter"
                value = int(counter.read_text()) + 1 if counter.exists() else 1
                counter.write_text(str(value))
                issue_id = f"bd-test{value:05d}"
                metadata_raw = flag("--metadata", "{}")
                labels_raw = flag("--labels")
                issues[issue_id] = {
                    "id": issue_id,
                    "title": args[1],
                    "type": flag("--type", "task"),
                    "status": flag("--status", "open"),
                    "parent": flag("--parent"),
                    "dependencies": {},
                    "labels": [value for value in labels_raw.split(",") if value],
                    "metadata": json.loads(metadata_raw),
                }
                save()
                print(issue_id)
            elif args and args[0] == "list":
                values = list(issues.values())
                requested_type = flag("--type")
                requested_label = flag("--label")
                if requested_type:
                    values = [issue for issue in values if issue.get("type") == requested_type]
                if requested_label:
                    values = [issue for issue in values if requested_label in issue.get("labels", [])]
                print(json.dumps(values))
            elif args and args[0] == "show":
                issue = issues.get(args[1])
                print(json.dumps([issue] if issue else []))
            elif args and args[0] == "update":
                issue = issues.get(args[1])
                if issue is not None:
                    if "--status" in args:
                        issue["status"] = flag("--status")
                    index = 0
                    while index < len(args):
                        if args[index] == "--set-metadata" and index + 1 < len(args):
                            key, _, value = args[index + 1].partition("=")
                            try:
                                value = json.loads(value)
                            except json.JSONDecodeError:
                                pass
                            issue.setdefault("metadata", {})[key] = value
                            index += 2
                            continue
                        index += 1
                    save()
                print("ok")
            elif args and args[0] == "close":
                issue = issues.get(args[1])
                if issue is not None:
                    issue["status"] = "closed"
                    save()
                print("ok")
            elif args[:2] == ["dep", "add"]:
                issue = issues.get(args[2])
                if issue is not None:
                    issue.setdefault("dependencies", {})[args[3]] = flag("--type", "blocks")
                    save()
                print("ok")
            elif args[:2] == ["dep", "remove"]:
                issue = issues.get(args[2])
                if issue is not None:
                    issue.setdefault("dependencies", {}).pop(args[3], None)
                    save()
                print("ok")
            elif args[:2] == ["dep", "list"]:
                issue = issues.get(args[2], {})
                values = []
                for dependency_id, dependency_type in issue.get("dependencies", {}).items():
                    dependency = issues.get(dependency_id)
                    if dependency is None:
                        continue
                    value = dict(dependency)
                    value["dependency_type"] = dependency_type
                    values.append(value)
                print(json.dumps(values))
            else:
                print("ok")
            """
        ).lstrip(),
        encoding="utf-8",
    )
    script.chmod(0o755)
    env = merged_environment(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        FAKE_BD_STATE=str(state_dir),
    )
    return env, state_dir


def features_by_slug(root: Path) -> dict[str, dict[str, Any]]:
    manifest = load_manifest(root)
    features = manifest["features"]
    assert isinstance(features, list)
    typed_features = cast(list[dict[str, Any]], features)
    return {str(feature["slug"]): feature for feature in typed_features}


@pytest.mark.integration
def test_scan_is_conservative_and_override_survives_rescan(legacy_project: Path) -> None:
    run_migrator(legacy_project, "scan", "--write")
    manifest = load_manifest(legacy_project)
    features = features_by_slug(legacy_project)

    assert features["alpha"]["computed_classification"] == "needs_review"
    assert features["alpha"]["classification"] == "needs_review"
    assert features["beta"]["classification"] == "in_progress"
    assert features["beta"]["dependencies"] == ["alpha"]
    assert manifest["root"] == "."

    run_migrator(
        legacy_project,
        "classify",
        "alpha",
        "completed",
        "--reason",
        "Code, tests, docs, and delivery commit were manually verified.",
    )
    run_migrator(legacy_project, "scan", "--write")
    features = features_by_slug(legacy_project)

    assert features["alpha"]["computed_classification"] == "needs_review"
    assert features["alpha"]["classification_override"] == "completed"
    assert features["alpha"]["classification"] == "completed"
    assert features["alpha"]["migration_decisions"]


@pytest.mark.integration
def test_prepare_import_and_finalize_are_resumable_and_guarded(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")

    assert (legacy_project / "docs/src/features/alpha/design.md").is_file()
    assert (legacy_project / "docs/src/features/beta/design.md").is_file()
    roadmap = (legacy_project / "docs/src/planned-features.md").read_text(encoding="utf-8")
    assert "### Alpha (`alpha`)" in roadmap
    assert "### Beta (`beta`)" in roadmap
    api_doc = (legacy_project / "docs/src/architecture/api.md").read_text(encoding="utf-8")
    assert "/alpha/v1/items" in api_doc
    assert "/010-alpha/v1/items" not in api_doc

    summary = (legacy_project / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    for heading in ("# Introduction", "# Architecture", "# Operator's Manual", "# Development Guide", "# Reference"):
        assert heading in summary
    assert summary.count("<!-- BEGIN IMPLEMENTED FEATURES -->") == 1
    assert summary.count("<!-- END IMPLEMENTED FEATURES -->") == 1
    assert (legacy_project / "docs/src/introduction/index.md").is_file()
    assert (legacy_project / "docs/src/operations/index.md").is_file()
    assert (legacy_project / "docs/src/development/index.md").is_file()
    assert (legacy_project / "docs/src/reference/index.md").is_file()

    env, state_dir = fake_bd_environment
    run_migrator(legacy_project, "import-beads", "--apply", env=env)
    features = features_by_slug(legacy_project)
    alpha = features["alpha"]
    beta = features["beta"]

    assert alpha["classification"] == "needs_review"
    assert alpha["beads"]["migration_reconciliation_id"]
    assert beta["beads"]["root_id"]
    assert beta["beads"]["implementation_tasks"]["T010"]

    commands = [json.loads(line) for line in (state_dir / "commands.jsonl").read_text(encoding="utf-8").splitlines()]
    alpha_root = alpha["beads"]["root_id"]
    assert not any(command[:2] == ["close", alpha_root] for command in commands)
    metadata_updates = [
        command
        for command in commands
        if len(command) >= 2 and command[0] == "update" and command[1] == alpha_root and "--set-metadata" in command
    ]
    assert metadata_updates
    assert f"implementation_id={alpha['beads']['lifecycle']['implementation']}" in metadata_updates[-1]

    result = run_migrator(legacy_project, "finalize", expected=2)
    assert "still referenced" in result.stderr

    (legacy_project / "docs/src/features/alpha/index.md").write_text(
        "# Alpha\n\n## Delivery Summary\n\nStandalone migrated record.\n",
        encoding="utf-8",
    )
    run_migrator(legacy_project, "finalize", "--apply")
    assert not (legacy_project / "docs/src/features/alpha/tasks.md").exists()
    assert (legacy_project / "migration/legacy-tasks/alpha.md").is_file()
    assert (legacy_project / "migration/legacy-tasks/beta.md").is_file()
    run_migrator(legacy_project, "verify", "--skip-docs-check")


def create_heading_status_project(root: Path) -> None:
    feature = root / "docs/src/features/alpha"
    feature.mkdir(parents=True)
    (root / ".beads/formulas").mkdir(parents=True)
    shutil.copyfile(FORMULA, root / ".beads/formulas/dstack-feature.formula.toml")
    (root / "docs/src/planned-features.md").write_text(
        "# Planned Features\n\n## Feature Map\n\n### `alpha`\n\n- Status: Implemented\n- Dependencies: None\n",
        encoding="utf-8",
    )
    (root / "docs/src/SUMMARY.md").write_text(
        "# Summary\n\n- [Implemented Features](features/index.md)\n  - [Alpha](features/alpha/index.md)\n",
        encoding="utf-8",
    )
    (root / "docs/src/features/index.md").write_text(
        "# Implemented Features\n\n- [Alpha](alpha/index.md)\n",
        encoding="utf-8",
    )
    (feature / "design.md").write_text("# Alpha design\n", encoding="utf-8")
    (feature / "index.md").write_text("# Alpha delivered\n", encoding="utf-8")
    (feature / "tasks.md").write_text(
        textwrap.dedent(
            """
            # Alpha tasks

            ## T000: confirm feature spec

            Status: done

            - Reviewed the design and roadmap.

            ## T010: implement alpha

            Status: in progress
            Depends on: T000
            Validation: pytest

            - Work had started when migration began.

            ## T999: final verification

            Status: pending
            Depends on: T010
            """
        ).lstrip(),
        encoding="utf-8",
    )


def create_cyclic_project(root: Path) -> None:
    features = root / "docs/src/features"
    (root / ".beads/formulas").mkdir(parents=True)
    shutil.copyfile(FORMULA, root / ".beads/formulas/dstack-feature.formula.toml")
    for slug in ("alpha", "beta"):
        directory = features / slug
        directory.mkdir(parents=True)
        (directory / "design.md").write_text(f"# {slug.title()} design\n", encoding="utf-8")
        (directory / "tasks.md").write_text(
            "# Tasks\n\n- [ ] `T000` Reconcile context\n- [ ] `T999` Close out\n",
            encoding="utf-8",
        )
    (root / "docs/src/planned-features.md").write_text(
        textwrap.dedent(
            """
            # Planned Features

            ## Feature Map

            ### `alpha`

            - Status: Planned
            - Dependencies: `beta`

            ### `beta`

            - Status: Planned
            - Dependencies: `alpha`
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (root / "docs/src/SUMMARY.md").write_text(
        "# Summary\n\n- [Implemented Features](features/index.md)\n",
        encoding="utf-8",
    )
    (features / "index.md").write_text("# Implemented Features\n", encoding="utf-8")


@pytest.mark.integration
def test_scan_parses_heading_status_task_format(tmp_path: Path) -> None:
    create_heading_status_project(tmp_path)
    run_migrator(tmp_path, "scan", "--write")
    feature = features_by_slug(tmp_path)["alpha"]
    tasks = {str(task["label"]): task for task in feature["tasks"]}

    assert list(tasks) == ["T000", "T010", "T999"]
    assert tasks["T000"]["status"] == "closed"
    assert tasks["T010"]["status"] == "in_progress"
    assert tasks["T010"]["depends_on"] == ["T000"]
    assert tasks["T010"]["validation"] == "pytest"
    assert "Work had started" in tasks["T010"]["body"]
    assert tasks["T999"]["status"] == "open"


@pytest.mark.integration
def test_dependency_cycle_is_preflighted_before_beads_mutation(
    tmp_path: Path,
) -> None:
    create_cyclic_project(tmp_path)
    run_migrator(tmp_path, "scan", "--write")
    features = features_by_slug(tmp_path)
    assert any("Feature dependency cycle" in item for item in features["alpha"]["conflicts"])

    bin_dir = tmp_path / "fake-bin"
    state_dir = tmp_path / "fake-bd-state"
    bin_dir.mkdir()
    state_dir.mkdir()
    fake_bd = bin_dir / "bd"
    fake_bd.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import os, sys\n"
        "state = Path(os.environ['FAKE_BD_STATE'])\n"
        "(state / 'called').write_text('yes')\n"
        "print('bd-test')\n",
        encoding="utf-8",
    )
    fake_bd.chmod(0o755)
    env = merged_environment(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        FAKE_BD_STATE=str(state_dir),
    )

    result = run_migrator(tmp_path, "import-beads", "--apply", env=env, expected=2)
    assert "must be resolved before Beads import" in result.stderr
    assert not (state_dir / "called").exists()

    related = run_migrator(
        tmp_path,
        "dependency",
        "alpha",
        "beta",
        "related",
        "--reason",
        "Alpha is a follow-up, not a hard prerequisite.",
        expected=2,
    )
    assert "bd list" in related.stderr
    assert "use `remove`" in related.stderr
    features = features_by_slug(tmp_path)
    assert features["alpha"]["dependencies"] == ["beta"]
    assert features["alpha"]["related_dependencies"] == []

    run_migrator(
        tmp_path,
        "dependency",
        "alpha",
        "beta",
        "remove",
        "--reason",
        "Beta already depends on alpha, so the reverse inferred edge is redundant.",
    )
    run_migrator(tmp_path, "scan", "--write")
    features = features_by_slug(tmp_path)
    assert features["alpha"]["dependencies"] == []
    assert features["alpha"]["related_dependencies"] == []
    assert features["alpha"]["removed_dependencies"] == ["beta"]
    assert not any("cycle" in item.casefold() for feature in features.values() for item in feature["conflicts"])


@pytest.mark.integration
def test_rescan_detects_legacy_mixed_relationship_cycle_before_import(tmp_path: Path) -> None:
    create_cyclic_project(tmp_path)
    run_migrator(tmp_path, "scan", "--write")

    manifest_path = tmp_path / "migration/workflow-migration.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    alpha = next(feature for feature in manifest["features"] if feature["slug"] == "alpha")
    alpha["dependency_overrides"]["beta"] = {
        "relation": "related",
        "reason": "Legacy migration downgraded the reverse edge to related.",
        "decided_at": "2026-07-13T00:00:00+00:00",
    }
    alpha["dependencies"] = []
    alpha["related_dependencies"] = ["beta"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    run_migrator(tmp_path, "scan", "--write")
    features = features_by_slug(tmp_path)
    findings = [item for feature in features.values() for item in feature["conflicts"]]
    assert any("Feature Beads traversal cycle" in item for item in findings)
    assert any("-[related]->" in item and "-[blocks]->" in item for item in findings)

    bin_dir = tmp_path / "fake-bin"
    state_dir = tmp_path / "fake-bd-state"
    bin_dir.mkdir()
    state_dir.mkdir()
    fake_bd = bin_dir / "bd"
    fake_bd.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['FAKE_BD_STATE'], 'called').write_text('yes')\n",
        encoding="utf-8",
    )
    fake_bd.chmod(0o755)
    env = merged_environment(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        FAKE_BD_STATE=str(state_dir),
    )

    result = run_migrator(tmp_path, "import-beads", "--apply", env=env, expected=2)
    assert "recursive Beads traversal" in result.stderr
    assert not (state_dir / "called").exists()


@pytest.mark.integration
def test_dependency_command_reconciles_imported_beads_and_manifest(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    env, state_dir = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    run_migrator(legacy_project, "import-beads", "--apply", env=env)

    features = features_by_slug(legacy_project)
    alpha_root = features["alpha"]["beads"]["root_id"]
    beta_root = features["beta"]["beads"]["root_id"]
    issues_path = state_dir / "issues.json"
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
    assert issues[beta_root]["dependencies"][alpha_root] == "blocks"

    run_migrator(
        legacy_project,
        "dependency",
        "beta",
        "alpha",
        "remove",
        "--reason",
        "The imported roadmap edge was disproven during semantic reconciliation.",
        env=env,
    )

    updated = features_by_slug(legacy_project)["beta"]
    assert updated["dependencies"] == []
    assert updated["removed_dependencies"] == ["alpha"]
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
    assert alpha_root not in issues[beta_root]["dependencies"]
    commands = [json.loads(line) for line in (state_dir / "commands.jsonl").read_text(encoding="utf-8").splitlines()]
    assert ["dep", "remove", beta_root, alpha_root] in commands
    run_migrator(
        legacy_project,
        "verify",
        "--beads",
        "--skip-docs-check",
        env=env,
    )


@pytest.mark.integration
def test_verify_beads_detects_actual_mixed_relationship_cycle(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    env, _ = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    run_migrator(legacy_project, "import-beads", "--apply", env=env)

    features = features_by_slug(legacy_project)
    alpha_root = features["alpha"]["beads"]["root_id"]
    beta_root = features["beta"]["beads"]["root_id"]
    run_command(
        ["bd", "dep", "add", alpha_root, beta_root, "--type", "related"],
        cwd=legacy_project,
        env=env,
    )
    commands_path = legacy_project / "fake-bd-state/commands.jsonl"
    commands_path.write_text("", encoding="utf-8")

    result = run_migrator(
        legacy_project,
        "verify",
        "--beads",
        "--skip-docs-check",
        env=env,
        expected=1,
    )
    assert "Imported Beads graph contains a traversal cycle" in result.stderr
    assert "-[related]->" in result.stderr
    assert "-[blocks]->" in result.stderr
    verify_commands = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    assert not any(command and command[0] == "list" for command in verify_commands)
    assert any(command[:2] == ["dep", "list"] for command in verify_commands)


@pytest.mark.integration
def test_unparsed_task_file_blocks_import_before_beads_mutation(tmp_path: Path) -> None:
    feature = tmp_path / "docs/src/features/alpha"
    feature.mkdir(parents=True)
    (tmp_path / ".beads/formulas").mkdir(parents=True)
    shutil.copyfile(FORMULA, tmp_path / ".beads/formulas/dstack-feature.formula.toml")
    (tmp_path / "docs/src/planned-features.md").write_text(
        "# Planned Features\n\n## Feature Map\n\n### `alpha`\n\n"
        "- Status: Partially implemented\n- Dependencies: None\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/src/SUMMARY.md").write_text(
        "# Summary\n\n- [Implemented Features](features/index.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/src/features/index.md").write_text(
        "# Implemented Features\n",
        encoding="utf-8",
    )
    (feature / "design.md").write_text("# Alpha design\n", encoding="utf-8")
    (feature / "tasks.md").write_text(
        "# Work log\n\nThis file contains prose but no recognizable T-numbered tasks.\n",
        encoding="utf-8",
    )

    run_migrator(tmp_path, "scan", "--write")
    manifest = load_manifest(tmp_path)
    assert manifest["inventory"] == {
        "legacy_task_files": 1,
        "parsed_task_files": 0,
        "parsed_tasks": 0,
        "unparsed_task_files": 1,
    }
    feature_state = features_by_slug(tmp_path)["alpha"]
    assert any("no recognizable T### tasks" in item for item in feature_state["conflicts"])

    bin_dir = tmp_path / "fake-bin"
    state_dir = tmp_path / "fake-bd-state"
    bin_dir.mkdir()
    state_dir.mkdir()
    fake_bd = bin_dir / "bd"
    fake_bd.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['FAKE_BD_STATE'], 'called').write_text('yes')\n",
        encoding="utf-8",
    )
    fake_bd.chmod(0o755)
    env = merged_environment(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        FAKE_BD_STATE=str(state_dir),
    )

    result = run_migrator(tmp_path, "import-beads", "--apply", env=env, expected=2)
    assert "task parser coverage must be resolved" in result.stderr
    assert not (state_dir / "called").exists()


@pytest.mark.integration
def test_finding_resolution_survives_rescan(tmp_path: Path) -> None:
    create_heading_status_project(tmp_path)
    run_migrator(tmp_path, "scan", "--write")
    before = features_by_slug(tmp_path)["alpha"]
    assert before["conflicts"]

    run_migrator(
        tmp_path,
        "resolve-findings",
        "alpha",
        "--all",
        "--reason",
        "Current code, documentation, and Git history reconcile the legacy status evidence.",
    )
    run_migrator(tmp_path, "scan", "--write")
    after = features_by_slug(tmp_path)["alpha"]

    assert after["conflicts"] == []
    assert after["resolved_conflicts"]
    report = (tmp_path / "migration/workflow-migration.md").read_text(encoding="utf-8")
    assert "## Resolved Findings" in report
    assert "Current code, documentation, and Git history" in report


@pytest.mark.integration
def test_scan_accepts_legacy_numbered_roadmap_heading_without_feature_files(tmp_path: Path) -> None:
    docs = tmp_path / "docs/src"
    docs.mkdir(parents=True)
    (docs / "planned-features.md").write_text(
        "# Planned features\n\n"
        "## Feature map\n\n"
        "### F010 — Passport Apollo whitelist configuration "
        "(`passport-apollo-whitelist-configuration`)\n\n"
        "- Status: Planned\n"
        "- Dependencies: None\n",
        encoding="utf-8",
    )
    (docs / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")

    run_migrator(tmp_path, "scan", "--write")
    feature = features_by_slug(tmp_path)["passport-apollo-whitelist-configuration"]

    assert feature["title"] == "Passport Apollo whitelist configuration"
    assert feature["classification"] == "planned"
    assert feature["conflicts"] == []
    assert feature["has_design"] is False
    assert feature["has_tasks"] is False


@pytest.mark.integration
def test_prepare_normalizes_numbered_legacy_directories_and_dependencies(tmp_path: Path) -> None:
    features = tmp_path / "docs/src/features"
    for slug in ("alpha", "beta"):
        (features / f"0{'10' if slug == 'alpha' else '20'}-{slug}").mkdir(parents=True)
    (tmp_path / "docs/src/planned-features.md").write_text(
        "# Planned Features\n\n## Feature Map\n\n"
        "### F010 — Alpha (`alpha`)\n\n- Status: Planned\n- Dependencies: None\n\n"
        "### F020 — Beta (`beta`)\n\n- Status: Planned\n- Dependencies: `F010`\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/src/SUMMARY.md").write_text("# Summary\n", encoding="utf-8")

    run_migrator(tmp_path, "scan", "--write")
    manifest = load_manifest(tmp_path)
    features_state = cast(list[dict[str, Any]], manifest["features"])
    assert all("number" not in feature for feature in features_state)
    assert features_by_slug(tmp_path)["beta"]["dependencies"] == ["alpha"]
    run_migrator(tmp_path, "prepare", "--apply", "--allow-dirty")

    assert (features / "alpha").is_dir()
    assert (features / "beta").is_dir()
    assert not (features / "010-alpha").exists()
    assert "### Alpha (`alpha`)" in (tmp_path / "docs/src/planned-features.md").read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.parametrize("names", [("010-alpha", "alpha"), ("010-alpha", "020-alpha")])
def test_scan_rejects_duplicate_normalized_feature_slugs(tmp_path: Path, names: tuple[str, str]) -> None:
    features = tmp_path / "docs/src/features"
    for name in names:
        (features / name).mkdir(parents=True)

    result = run_migrator(tmp_path, "scan", "--write", expected=2)

    assert "normalize to duplicate slug 'alpha'" in result.stderr
    assert not (tmp_path / "migration/workflow-migration.json").exists()


@pytest.mark.integration
def test_prepare_uses_sentence_case_human_title_and_rescan_preserves_feature(tmp_path: Path) -> None:
    feature = tmp_path / "docs/src/features/passport-mqtt-roles"
    feature.mkdir(parents=True)
    (tmp_path / "docs/src/planned-features.md").write_text(
        "# Planned features\n\n"
        "## Feature map\n\n"
        "### `passport-mqtt-roles`\n\n"
        "- Status: Planned\n"
        "- Dependencies: None\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/src/SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (feature / "design.md").write_text("# Passport MQTT roles\n", encoding="utf-8")

    run_migrator(tmp_path, "scan", "--write")
    run_migrator(tmp_path, "prepare", "--apply", "--allow-dirty")
    roadmap = (tmp_path / "docs/src/planned-features.md").read_text(encoding="utf-8")
    assert "### Passport mqtt roles (`passport-mqtt-roles`)" in roadmap

    run_migrator(tmp_path, "scan", "--write")
    feature_state = features_by_slug(tmp_path)["passport-mqtt-roles"]
    assert feature_state["title"] == "Passport mqtt roles"


@pytest.mark.integration
def test_baseline_records_missing_docs_checker_and_absent_tests_without_running_pytest(tmp_path: Path) -> None:
    result = run_migrator(tmp_path, "baseline", "--write")
    assert "documentation: unavailable" in result.stdout
    assert "tests: no_tests" in result.stdout

    baseline = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))
    assert baseline["documentation"]["status"] == "unavailable"
    assert baseline["documentation"]["command"] is None
    assert baseline["tests"]["status"] == "no_tests"
    assert baseline["tests"]["command"] is None
    report = (tmp_path / "migration/baseline.md").read_text(encoding="utf-8")
    assert "scripts/check-docs.py did not exist" in report
    assert "No test_*.py or *_test.py files were found" in report


@pytest.mark.integration
def test_import_recovers_existing_beads_ids_and_does_not_duplicate_issues(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    env, state_dir = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    run_migrator(legacy_project, "import-beads", "--apply", env=env)

    commands_path = state_dir / "commands.jsonl"
    initial_commands = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    initial_creates = [command for command in initial_commands if command and command[0] == "create"]
    initial_issue_count = len(json.loads((state_dir / "issues.json").read_text(encoding="utf-8")))

    manifest_path = legacy_project / "migration/workflow-migration.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for feature in manifest["features"]:
        feature["beads"] = {}
    manifest.pop("beads_import_started", None)
    manifest.pop("beads_import_started_at", None)
    manifest.pop("beads_import_completed_at", None)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_migrator(legacy_project, "import-beads", "--apply", env=env)
    assert "Recovered" in result.stdout

    final_commands = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    final_creates = [command for command in final_commands if command and command[0] == "create"]
    final_issue_count = len(json.loads((state_dir / "issues.json").read_text(encoding="utf-8")))
    assert len(final_creates) == len(initial_creates)
    assert final_issue_count == initial_issue_count

    recovered = features_by_slug(legacy_project)
    assert recovered["alpha"]["beads"]["root_id"]
    assert recovered["alpha"]["beads"]["lifecycle"]["implementation"]
    assert recovered["alpha"]["beads"]["implementation_tasks"]["T010"]
    assert recovered["alpha"]["beads"]["migration_reconciliation_id"]
