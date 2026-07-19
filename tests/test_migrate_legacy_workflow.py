"""End-to-end tests for migration from the legacy Markdown workflow."""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from tests.support import commit_repository, initialize_git, merged_environment, run_command


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
            if args[:1] == ["--dolt-auto-commit=batch"]:
                batch_count = state / "batch-count"
                batch_count.write_text(str(int(batch_count.read_text()) + 1 if batch_count.exists() else 1))
                args = args[1:]
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
                failure_marker = state / "dep-failed-once"
                source = issues.get(args[2], {})
                target = issues.get(args[3], {})
                if (
                    os.environ.get("FAKE_BD_FAIL_DEP_ONCE") == "1"
                    and source.get("type") == "epic"
                    and target.get("type") == "epic"
                    and not failure_marker.exists()
                ):
                    failure_marker.write_text("failed")
                    print("injected dependency failure", file=sys.stderr)
                    raise SystemExit(1)
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
    run_migrator(legacy_project, "baseline", "--write")
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
    imported_identities = {slug: feature["beads"] for slug, feature in features.items()}
    commands_path = state_dir / "commands.jsonl"
    before_retry = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    retry = run_migrator(legacy_project, "import-beads", "--apply", env=env)
    after_retry = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    mutation_verbs = {"create", "update", "close", "dep", "note"}
    assert [command for command in after_retry if command and command[0] in mutation_verbs] == [
        command for command in before_retry if command and command[0] in mutation_verbs
    ]
    assert "already completed; skipping mutations" in retry.stdout
    assert {slug: feature["beads"] for slug, feature in features_by_slug(legacy_project).items()} == imported_identities

    commands = after_retry
    alpha_root = alpha["beads"]["root_id"]
    assert not any(command[:2] == ["close", alpha_root] for command in commands)
    metadata_updates = [
        command
        for command in commands
        if len(command) >= 2 and command[0] == "update" and command[1] == alpha_root and "--set-metadata" in command
    ]
    assert metadata_updates
    assert any(
        f"implementation_id={alpha['beads']['lifecycle']['implementation']}" in command for command in metadata_updates
    )

    result = run_migrator(legacy_project, "finalize", expected=2)
    assert "still referenced" in result.stderr

    existing_archive = legacy_project / "migration/legacy-tasks/existing.md"
    existing_archive.parent.mkdir(parents=True, exist_ok=True)
    existing_archive.write_text("# Existing archive\n", encoding="utf-8")
    (legacy_project / "docs/src/features/alpha/index.md").write_text(
        "# Alpha\n\n## Delivery Summary\n\nStandalone migrated record.\n",
        encoding="utf-8",
    )
    run_migrator(legacy_project, "finalize", "--apply")
    assert not (legacy_project / "docs/src/features/alpha/tasks.md").exists()
    assert (legacy_project / "migration/legacy-tasks/alpha.md").is_file()
    assert (legacy_project / "migration/legacy-tasks/beta.md").is_file()
    assert existing_archive.read_text(encoding="utf-8") == "# Existing archive\n"
    finalized = (legacy_project / "migration/workflow-migration.json").read_bytes()
    run_migrator(legacy_project, "finalize", "--apply")
    assert (legacy_project / "migration/workflow-migration.json").read_bytes() == finalized
    run_migrator(legacy_project, "verify")


@pytest.mark.integration
def test_checkbox_status_fallback_and_explicit_precedence(tmp_path: Path) -> None:
    feature = tmp_path / "docs/src/features/alpha"
    feature.mkdir(parents=True)
    (tmp_path / "docs/src/planned-features.md").write_text(
        "# Planned Features\n\n### `alpha`\n\n- Status: In Progress\n",
        encoding="utf-8",
    )
    (feature / "design.md").write_text("# Alpha\n", encoding="utf-8")
    (feature / "tasks.md").write_text(
        textwrap.dedent(
            """
            # Tasks

            - [ ] `T010` Open
            - [-] `T020` Active
            - [x] `T030` Closed
            - [x] `T040` Explicit override

              Status: blocked
            """
        ).lstrip(),
        encoding="utf-8",
    )

    run_migrator(tmp_path, "scan", "--write")
    tasks = {task["label"]: task for task in features_by_slug(tmp_path)["alpha"]["tasks"]}
    assert tasks["T010"]["status"] == "open"
    assert tasks["T020"]["status"] == "in_progress"
    assert tasks["T030"]["status"] == "closed"
    assert tasks["T040"]["status"] == "blocked"


@pytest.mark.integration
def test_delivered_navigation_and_review_required_drafts(legacy_project: Path) -> None:
    alpha = legacy_project / "docs/src/features/alpha"
    numbered_alpha = legacy_project / "docs/src/features/001-alpha"
    alpha.rename(numbered_alpha)
    (numbered_alpha / "index.md").write_text(
        "# Alpha\n\n## Delivery summary\n\nLegacy delivery evidence.\n",
        encoding="utf-8",
    )
    initialize_git(legacy_project, "legacy delivered feature")
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    summary_path = legacy_project / "docs/src/SUMMARY.md"
    index_path = legacy_project / "docs/src/features/index.md"
    assert "[Alpha](features/alpha/index.md)" in summary_path.read_text(encoding="utf-8")
    assert "[Alpha](alpha/index.md)" in index_path.read_text(encoding="utf-8")
    prepared = (summary_path.read_bytes(), index_path.read_bytes())
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    assert (summary_path.read_bytes(), index_path.read_bytes()) == prepared

    run_migrator(legacy_project, "draft-delivered-records", "--apply")
    manifest_path = legacy_project / "migration/workflow-migration.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = manifest["delivered_record_candidates"]
    assert candidates
    assert all(not candidate["reviewed"] for candidate in candidates)
    blocked = run_migrator(legacy_project, "verify", "--skip-docs-check", expected=1)
    assert "Delivered-record candidates require semantic review" in blocked.stderr
    finalize = run_migrator(legacy_project, "finalize", "--apply", expected=2)
    assert "require semantic review before finalization" in finalize.stderr
    for candidate in candidates:
        run_migrator(
            legacy_project,
            "review-delivered-record",
            candidate["slug"],
            "--reason",
            "Maintainer reconciled the candidate with legacy and Git evidence",
        )
    reviewed = json.loads(manifest_path.read_text(encoding="utf-8"))["delivered_record_candidates"]
    assert all(candidate["reviewed"] for candidate in reviewed)
    candidate_path = legacy_project / reviewed[0]["path"]
    candidate_path.write_text(candidate_path.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")
    tampered = run_migrator(legacy_project, "verify", "--skip-docs-check", expected=1)
    assert "changed after approval" in tampered.stderr
    rejected_review = run_migrator(
        legacy_project,
        "review-delivered-record",
        reviewed[0]["slug"],
        "--reason",
        "Attempt review after tampering",
        expected=2,
    )
    assert "changed after drafting" in rejected_review.stderr
    run_migrator(legacy_project, "draft-delivered-records", "--apply")
    redrafted = json.loads(manifest_path.read_text(encoding="utf-8"))["delivered_record_candidates"]
    assert all(candidate["reviewed"] for candidate in redrafted)
    candidate_text = (legacy_project / redrafted[0]["path"]).read_text(encoding="utf-8")
    assert "Git commits:" in candidate_text
    assert "Changed paths: docs/src/features/001-alpha" in candidate_text
    (legacy_project / "docs/src/features/alpha/design.md").write_text(
        "# Alpha design\n\nAdditional delivered evidence.\n",
        encoding="utf-8",
    )
    commit_repository(legacy_project, "add delivered evidence")
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "draft-delivered-records", "--apply")
    changed = json.loads(manifest_path.read_text(encoding="utf-8"))["delivered_record_candidates"]
    assert any(not candidate["reviewed"] for candidate in changed)


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
    assert "### Passport MQTT roles (`passport-mqtt-roles`)" in roadmap

    run_migrator(tmp_path, "scan", "--write")
    feature_state = features_by_slug(tmp_path)["passport-mqtt-roles"]
    assert feature_state["title"] == "Passport MQTT roles"


@pytest.mark.integration
def test_baseline_hk_inventory_excludes_builtin_test_fixtures(tmp_path: Path) -> None:
    (tmp_path / "hk.pkl").write_text("// evaluated by the fixture\n", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    fixture_path = tmp_path / "pkl-result.json"
    fixture_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "pre-commit": {
                        "steps": {
                            "detect_private_key": {
                                "check": "scan",
                                "types": ["text"],
                                "tests": [{"input": "-----BEGIN " + "PRIVATE" + " KEY-----"}],
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    fake_pkl = binary_dir / "pkl"
    fake_pkl.write_text(f"#!/bin/sh\ncat '{fixture_path}'\n", encoding="utf-8")
    fake_pkl.chmod(0o755)
    environment = {**os.environ, "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}"}

    run_migrator(tmp_path, "baseline", "--write", env=environment)
    baseline_path = tmp_path / "migration/baseline.json"
    first = json.loads(baseline_path.read_text(encoding="utf-8"))["hk"]["hooks"]["pre-commit"]["detect_private_key"]
    assert first["definition"] == '{"check":"scan","types":["text"]}'
    assert "PRIVATE" + " KEY" not in baseline_path.read_text(encoding="utf-8")

    fixture_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "pre-commit": {
                        "steps": {
                            "detect_private_key": {
                                "check": "scan",
                                "types": ["text"],
                                "tests": [{"input": "changed machine-owned fixture"}],
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    run_migrator(tmp_path, "baseline", "--write", env=environment)
    second = json.loads(baseline_path.read_text(encoding="utf-8"))["hk"]["hooks"]["pre-commit"]["detect_private_key"]
    assert second == first


@pytest.mark.integration
def test_baseline_records_and_reruns_named_validation_partitions(tmp_path: Path) -> None:
    (tmp_path / "packages/client").mkdir(parents=True)
    docs_partition = json.dumps(
        {
            "name": "root-docs",
            "kind": "documentation",
            "argv": [sys.executable, "-c", "print('docs-ok')"],
            "working_directory": ".",
            "provenance": "operator-override",
        }
    )
    client_partition = json.dumps(
        {
            "name": "client-tests",
            "kind": "tests",
            "argv": [sys.executable, "-c", "import os; print(os.getcwd()); print('x' * 25000)"],
            "working_directory": "packages/client",
            "provenance": "mise.toml:monorepo.config_roots",
        }
    )

    run_migrator(
        tmp_path,
        "baseline",
        "--validation-partition",
        docs_partition,
        "--validation-partition",
        client_partition,
        "--write",
    )
    baseline_path = tmp_path / "migration/baseline.json"
    report_path = tmp_path / "migration/baseline.md"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    partitions = baseline["validation_partitions"]
    assert [item["name"] for item in partitions] == ["root-docs", "client-tests"]
    assert partitions[1]["argv"] == [
        sys.executable,
        "-c",
        "import os; print(os.getcwd()); print('x' * 25000)",
    ]
    assert partitions[1]["working_directory"] == "packages/client"
    assert partitions[1]["status"] == "passed"
    assert partitions[1]["output_truncated"] is True
    assert len(partitions[1]["stdout"]) <= 20_000
    assert baseline["documentation"]["status"] == "passed"
    assert baseline["tests"]["status"] == "passed"
    report = report_path.read_text(encoding="utf-8")
    assert "`client-tests` (tests): status=`passed`" in report
    assert "cwd=`packages/client`" in report
    assert "Return code: `0`; output truncated: `true`" in report
    assert "- stdout:" in report

    first = baseline_path.read_bytes(), report_path.read_bytes()
    run_migrator(
        tmp_path,
        "baseline",
        "--validation-partition",
        docs_partition,
        "--validation-partition",
        client_partition,
        "--write",
    )
    assert (baseline_path.read_bytes(), report_path.read_bytes()) == first

    marker = tmp_path / "shell-was-used"
    non_shell_partition = json.dumps(
        {
            "name": "non-shell",
            "kind": "tests",
            "argv": [f"printf safe; touch {marker}"],
            "working_directory": ".",
            "provenance": "operator-override",
        }
    )
    run_migrator(
        tmp_path,
        "baseline",
        "--validation-partition",
        non_shell_partition,
        "--write",
        expected=1,
    )
    assert not marker.exists()
    failed = json.loads(baseline_path.read_text(encoding="utf-8"))["validation_partitions"][0]
    assert failed["status"] == "failed"
    assert failed["recovery"]

    validation_marker = tmp_path / "validation-ran-too-early"
    first_partition = json.dumps(
        {
            "name": "must-not-run",
            "kind": "tests",
            "argv": [sys.executable, "-c", f"from pathlib import Path; Path({str(validation_marker)!r}).touch()"],
        }
    )
    run_migrator(
        tmp_path,
        "baseline",
        "--validation-partition",
        first_partition,
        "--validation-partition",
        '{"name":"broken"}',
        expected=2,
    )
    assert not validation_marker.exists()


@pytest.mark.integration
def test_baseline_inventory_discovers_monorepo_docs_go_and_elixir(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/book.toml").write_text('[book]\ntitle = "Legacy docs"\n', encoding="utf-8")
    (tmp_path / "packages/client").mkdir(parents=True)
    (tmp_path / "packages/server/test/app").mkdir(parents=True)
    (tmp_path / "mise.toml").write_text(
        "experimental_monorepo_root = true\n\n"
        '[monorepo]\nconfig_roots = [".", "packages/client", "packages/server"]\n\n'
        '[tasks."docs:build"]\nrun = "cd docs && mdbook build"\n',
        encoding="utf-8",
    )
    (tmp_path / "packages/client/mise.toml").write_text(
        '[tasks.test]\nrun = "go test ./..."\n',
        encoding="utf-8",
    )
    (tmp_path / "packages/client/go.mod").write_text("module example.test/client\n", encoding="utf-8")
    (tmp_path / "packages/client/client_test.go").write_text("package client\n", encoding="utf-8")
    (tmp_path / "packages/server/mix.exs").write_text("defmodule Legacy.MixProject do\nend\n", encoding="utf-8")
    (tmp_path / "packages/server/test/app/example_test.exs").write_text(
        "defmodule LegacyTest do\n  use ExUnit.Case\nend\n",
        encoding="utf-8",
    )

    run_migrator(tmp_path, "baseline", "--write")
    inventory = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))["capability_inventory"]

    assert inventory["layout"] == {
        "kind": "monorepo",
        "config_roots": [".", "packages/client", "packages/server"],
        "source": "mise.toml",
    }
    assert inventory["documentation"]["evidence"] == ["docs/book.toml"]
    assert inventory["documentation"]["commands"][0]["argv"] == ["mise", "run", "docs:build"]
    tests = {partition["name"]: partition for partition in inventory["tests"]["commands"]}
    assert tests["client-mise-test"]["argv"] == ["mise", "run", "//packages/client:test"]
    assert tests["client-mise-test"]["working_directory"] == "."
    assert tests["server-elixir-test"]["argv"] == ["mix", "test"]
    assert tests["server-elixir-test"]["working_directory"] == "packages/server"
    assert inventory["tests"]["evidence"] == [
        "packages/client/client_test.go",
        "packages/server/test/app/example_test.exs",
    ]
    baseline = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))
    assert baseline["documentation"]["status"] == "unresolved"
    assert baseline["tests"]["status"] == "unresolved"
    report = (tmp_path / "migration/baseline.md").read_text(encoding="utf-8")
    assert "Layout: `monorepo`" in report
    assert "`client-mise-test`" in report
    assert "`server-elixir-test`" in report


@pytest.mark.integration
def test_baseline_inventory_covers_single_package_ecosystems_and_ci_evidence(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "legacy"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "src/lib.rs").write_text("#[test]\nfn works() {}\n", encoding="utf-8")
    (tmp_path / "src/orphan_test.go").write_text("package orphan\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "legacy"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "tests/test_app.py").write_text("def test_app():\n    assert True\n", encoding="utf-8")
    outside_test = tmp_path.parent / f"{tmp_path.name}-outside_test.py"
    outside_test.write_text("def test_external():\n    assert False\n", encoding="utf-8")
    (tmp_path / "tests/external_test.py").symlink_to(outside_test)
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "src/app.test.tsx").write_text("export {}\n", encoding="utf-8")
    (tmp_path / ".github/workflows/validate.yml").write_text(
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - run: |-\n"
        "          cargo test\n"
        "          uv run pytest\n"
        "        working-directory: client\n"
        "      - run: npm test\n",
        encoding="utf-8",
    )

    run_migrator(tmp_path, "baseline", "--write")
    first = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))["capability_inventory"]
    commands = {item["name"]: item for item in first["tests"]["commands"]}
    assert set(commands) == {"root-javascript-test", "root-python-test", "root-rust-test"}
    assert commands["root-python-test"]["argv"] == ["uv", "run", "pytest"]
    assert first["packages"][0]["manifests"] == ["Cargo.toml", "package.json", "pyproject.toml"]
    assert "src/orphan_test.go" in first["tests"]["evidence"]
    assert "tests/external_test.py" not in first["tests"]["evidence"]
    assert ".: Go test files exist but go.mod is missing" in first["ambiguities"]
    assert first["ci"]["commands"] == [
        {
            "source": ".github/workflows/validate.yml:4",
            "command": "cargo test\nuv run pytest",
            "working_directory": "client",
            "provenance": "ci-evidence-only",
        },
        {
            "source": ".github/workflows/validate.yml:8",
            "command": "npm test",
            "working_directory": ".",
            "provenance": "ci-evidence-only",
        },
    ]
    report_path = tmp_path / "migration/baseline.md"
    report = report_path.read_text(encoding="utf-8")
    assert "Manifests: `Cargo.toml`, `package.json`, `pyproject.toml`" in report
    assert "argv=`cargo test`" in report
    assert "`.github/workflows/validate.yml:4`" in report
    run_migrator(tmp_path, "baseline", "--write")
    second = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))["capability_inventory"]
    assert first == second
    assert report_path.read_text(encoding="utf-8") == report


@pytest.mark.integration
@pytest.mark.parametrize(
    ("ecosystem", "manifest", "test_path", "test_text", "expected"),
    [
        ("go", "go.mod", "app_test.go", "package app\n", "root-go-test"),
        ("elixir", "mix.exs", "test/app_test.exs", "defmodule AppTest do\nend\n", "root-elixir-test"),
        ("rust", "Cargo.toml", "tests/app.rs", "#[test]\nfn works() {}\n", "root-rust-test"),
        ("python", "pyproject.toml", "tests/test_app.py", "def test_app():\n    assert True\n", "root-python-test"),
        ("javascript", "package.json", "src/app.test.ts", "export {}\n", "root-javascript-test"),
    ],
)
def test_baseline_inventory_discovers_isolated_single_package_ecosystem(
    tmp_path: Path,
    ecosystem: str,
    manifest: str,
    test_path: str,
    test_text: str,
    expected: str,
) -> None:
    manifest_text = json.dumps({"scripts": {"test": "vitest run"}}) if ecosystem == "javascript" else "# manifest\n"
    (tmp_path / manifest).write_text(manifest_text, encoding="utf-8")
    target = tmp_path / test_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(test_text, encoding="utf-8")

    run_migrator(tmp_path, "baseline", "--write")
    inventory = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))["capability_inventory"]

    assert inventory["layout"]["kind"] == "single-package"
    assert [command["name"] for command in inventory["tests"]["commands"]] == [expected]
    assert inventory["tests"]["evidence"] == [test_path]


@pytest.mark.integration
def test_baseline_inventory_rejects_unsafe_or_missing_mise_roots(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-package"
    outside.mkdir(exist_ok=True)
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    (tmp_path / "mise.toml").write_text(
        '[monorepo]\nconfig_roots = [".", "../outside-package", "/tmp/absolute", "linked", "missing"]\n',
        encoding="utf-8",
    )

    run_migrator(tmp_path, "baseline", "--write")
    inventory = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))["capability_inventory"]

    assert inventory["layout"]["config_roots"] == ["."]
    assert inventory["ambiguities"] == [
        "mise config root does not exist: missing",
        "mise config root resolves through a symlink: linked",
        "unsafe mise config root: '../outside-package'",
        "unsafe mise config root: '/tmp/absolute'",
    ]
    assert not any(str(outside) in evidence for evidence in inventory["tests"]["evidence"])


@pytest.mark.integration
def test_baseline_inventory_keeps_explicit_one_package_monorepo_and_markdown(tmp_path: Path) -> None:
    (tmp_path / "packages/api").mkdir(parents=True)
    (tmp_path / "packages/api/CONTRIBUTING.md").write_text("# API contribution\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changes\n", encoding="utf-8")
    (tmp_path / "mise.toml").write_text(
        '[monorepo]\nconfig_roots = ["packages/api"]\n',
        encoding="utf-8",
    )

    run_migrator(tmp_path, "baseline", "--write")
    baseline = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))
    inventory = baseline["capability_inventory"]

    assert inventory["layout"]["kind"] == "monorepo"
    assert inventory["layout"]["config_roots"] == ["packages/api"]
    assert inventory["documentation"]["evidence"] == ["CHANGELOG.md", "packages/api/CONTRIBUTING.md"]
    assert baseline["documentation"]["status"] == "unresolved"


@pytest.mark.integration
def test_baseline_inventory_rejects_symlinked_capability_inputs(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "check-docs.py").write_text("raise SystemExit('must not run')\n", encoding="utf-8")
    (outside / "go.mod").write_text("module outside.invalid\n", encoding="utf-8")
    (outside / "workflows").mkdir()
    (outside / "workflows/workflow.yml").write_text("steps:\n  - run: outside-command\n", encoding="utf-8")
    (tmp_path / "scripts").symlink_to(outside, target_is_directory=True)
    (tmp_path / "go.mod").symlink_to(outside / "go.mod")
    (tmp_path / "app_test.go").write_text("package app\n", encoding="utf-8")
    (tmp_path / ".github").symlink_to(outside, target_is_directory=True)

    run_migrator(tmp_path, "baseline", "--write")
    inventory = json.loads((tmp_path / "migration/baseline.json").read_text(encoding="utf-8"))["capability_inventory"]

    assert "documentation checker must not resolve through a symlink: scripts/check-docs.py" in inventory["ambiguities"]
    assert ".: manifest must not resolve through a symlink: go.mod" in inventory["ambiguities"]
    assert "CI workflow directory must not resolve through a symlink" in inventory["ambiguities"]
    assert inventory["ci"]["files"] == []
    assert inventory["tests"]["evidence"] == ["app_test.go"]
    assert inventory["tests"]["commands"] == []


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
    assert "No documentation system, task, or checker was discovered" in report
    assert "No test evidence was found in the bounded repository topology scan" in report


@pytest.mark.integration
def test_selective_import_does_not_mark_global_completion(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    env, _ = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")

    beta = run_migrator(legacy_project, "import-beads", "--feature", "beta", "--apply", env=env)
    manifest_path = legacy_project / "migration/workflow-migration.json"
    partial = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert partial["beads_import_completed_at"] is None
    assert partial["beads_import_progress"]["total"] == 2
    assert partial["beads_import_progress"]["completed"] == 0
    assert partial["beads_import_progress"]["remaining"] == 2
    assert features_by_slug(legacy_project)["beta"]["beads"]["import_phase"] == "relationships"
    assert "remaining: 2" in beta.stdout

    failing_env = {**env, "FAKE_BD_FAIL_DEP_ONCE": "1"}
    run_migrator(
        legacy_project,
        "import-beads",
        "--feature",
        "alpha",
        "--apply",
        env=failing_env,
        expected=2,
    )
    interrupted = features_by_slug(legacy_project)
    assert interrupted["alpha"]["beads"]["import_phase"] == "relationships"
    assert interrupted["beta"]["beads"]["import_phase"] == "relationships"

    alpha = run_migrator(legacy_project, "import-beads", "--feature", "alpha", "--apply", env=env)
    complete = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert complete["beads_import_completed_at"]
    assert complete["beads_import_progress"]["completed"] == 2
    assert complete["beads_import_progress"]["remaining"] == 0
    assert "remaining: 0" in alpha.stdout


@pytest.mark.integration
def test_large_import_uses_bounded_batches_and_proportional_retry(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    roadmap = legacy_project / "docs/src/planned-features.md"
    roadmap_additions: list[str] = []
    for index in range(12):
        slug = f"bulk-{index:02d}"
        feature = legacy_project / "docs/src/features" / slug
        feature.mkdir(parents=True)
        (feature / "design.md").write_text(f"# {slug}\n", encoding="utf-8")
        tasks = ["# Tasks", ""]
        for task_index in range(12):
            tasks.extend((f"- [x] `T{task_index + 10:03d}` Bulk task {task_index}", ""))
        (feature / "tasks.md").write_text("\n".join(tasks), encoding="utf-8")
        dependency = "None" if index == 0 else f"`bulk-{index - 1:02d}`"
        roadmap_additions.extend((f"### `{slug}`", "", "- Status: Implemented", f"- Dependencies: {dependency}", ""))
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\n" + "\n".join(roadmap_additions), encoding="utf-8")

    env, state_dir = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    started = time.monotonic()
    imported = run_migrator(legacy_project, "import-beads", "--apply", env=env)
    elapsed = time.monotonic() - started

    issues = json.loads((state_dir / "issues.json").read_text(encoding="utf-8"))
    commands_path = state_dir / "commands.jsonl"
    before_retry = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    assert len(issues) >= 300
    assert int((state_dir / "batch-count").read_text(encoding="utf-8")) >= len(issues)
    batch_commits = [command for command in before_retry if command[:2] == ["dolt", "commit"]]
    assert len(batch_commits) <= 2 * 14 + 1
    assert elapsed < 240
    assert "completed: 14" in imported.stdout
    assert "remaining: 0" in imported.stdout

    manifest_path = legacy_project / "migration/workflow-migration.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = {feature["slug"]: feature for feature in manifest["features"]}
    features["bulk-06"]["beads"]["import_phase"] = "relationships"
    manifest["beads_import_completed_at"] = None
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    issues_path = state_dir / "issues.json"
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
    source = features["bulk-06"]["beads"]["root_id"]
    target = features["bulk-05"]["beads"]["root_id"]
    issues[source]["dependencies"].pop(target)
    issues_path.write_text(json.dumps(issues), encoding="utf-8")

    resumed = run_migrator(legacy_project, "import-beads", "--feature", "bulk-06", "--apply", env=env)
    after_retry = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    retry_mutations = [
        command
        for command in after_retry[len(before_retry) :]
        if command and command[0] in {"create", "update", "close", "dep", "note"}
    ]
    assert retry_mutations == [["dep", "add", source, target, "--type", "blocks"]]
    assert "remaining: 1" in resumed.stdout
    assert resumed.stdout.rstrip().endswith("Import pass complete for 1 selected feature(s).")
    progress = json.loads(manifest_path.read_text(encoding="utf-8"))["beads_import_progress"]
    assert progress["completed"] == 14
    assert progress["remaining"] == 0


@pytest.mark.integration
def test_legacy_interrupted_state_retries_relationships(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    env, state_dir = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    run_migrator(legacy_project, "import-beads", "--apply", env=env)

    manifest_path = legacy_project / "migration/workflow-migration.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = {feature["slug"]: feature for feature in manifest["features"]}
    for feature in features.values():
        feature["beads"].pop("import_phase")
    manifest.pop("beads_import_completed_at")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    issues_path = state_dir / "issues.json"
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
    beta_root = features["beta"]["beads"]["root_id"]
    alpha_root = features["alpha"]["beads"]["root_id"]
    issues[beta_root]["dependencies"].pop(alpha_root)
    issues_path.write_text(json.dumps(issues), encoding="utf-8")

    run_migrator(legacy_project, "scan", "--write")
    rescanned = features_by_slug(legacy_project)
    assert rescanned["alpha"]["beads"]["import_phase"] == "relationships"
    assert rescanned["beta"]["beads"]["import_phase"] == "relationships"
    run_migrator(legacy_project, "import-beads", "--apply", env=env)
    repaired = json.loads(issues_path.read_text(encoding="utf-8"))
    assert repaired[beta_root]["dependencies"][alpha_root] == "blocks"
    assert all(feature["beads"]["import_phase"] == "completed" for feature in features_by_slug(legacy_project).values())


@pytest.mark.integration
def test_import_recovers_existing_beads_ids_and_does_not_duplicate_issues(
    legacy_project: Path,
    fake_bd_environment: tuple[dict[str, str], Path],
) -> None:
    env, state_dir = fake_bd_environment
    run_migrator(legacy_project, "scan", "--write")
    run_migrator(legacy_project, "prepare", "--apply", "--allow-dirty")
    first_apply = run_migrator(legacy_project, "import-beads", "--apply", env=env)
    assert "APPLY STARTED" in first_apply.stdout
    assert "remaining: 0" in first_apply.stdout

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
    assert "existing:" in result.stdout
    assert "pending:" in result.stdout
    assert "remaining: 0" in result.stdout

    final_commands = [json.loads(line) for line in commands_path.read_text(encoding="utf-8").splitlines()]
    final_creates = [command for command in final_commands if command and command[0] == "create"]
    final_issue_count = len(json.loads((state_dir / "issues.json").read_text(encoding="utf-8")))
    assert len(final_creates) == len(initial_creates)
    assert final_issue_count == initial_issue_count

    recovered = features_by_slug(legacy_project)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    completed_at = manifest["beads_import_completed_at"]
    progress = manifest["beads_import_progress"]
    run_migrator(legacy_project, "scan", "--write")
    rescanned = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert rescanned["beads_import_completed_at"] == completed_at
    assert rescanned["beads_import_progress"] == progress
    assert recovered["alpha"]["beads"]["root_id"]
    assert recovered["alpha"]["beads"]["lifecycle"]["implementation"]
    assert recovered["alpha"]["beads"]["implementation_tasks"]["T010"]
    assert recovered["alpha"]["beads"]["migration_reconciliation_id"]
