"""Regression tests for pre-implementation feature reviews."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "skills/dstack-core/scripts"


def load_script(name: str) -> ModuleType:
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py").replace("-", "_"), path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def issue(
    issue_id: str,
    title: str,
    *,
    parent: str | None = None,
    metadata: dict[str, str] | None = None,
    dependencies: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "id": issue_id,
        "title": title,
        "status": "open",
        "issue_type": "task",
        "parent": parent,
        "owner": "maintainer",
        "description": f"Implement {title}.",
        "acceptance_criteria": f"{title} passes.",
        "labels": ["workflow:feature-lifecycle"],
        "metadata": metadata or {},
        "dependencies": dependencies or [],
    }


def lifecycle_metadata() -> dict[str, str]:
    return {
        "design_id": "demo-design",
        "review_specification_clarity_id": "demo-clarity",
        "review_execution_readiness_id": "demo-readiness",
        "spec_reconcile_id": "demo-spec-reconcile",
        "implementation_id": "demo-impl",
        "docs_reconcile_id": "demo-docs",
        "validation_id": "demo-validation",
        "review_implementation_integrity_id": "demo-implementation-review",
        "review_delivery_integrity_id": "demo-delivery-review",
        "delivery_id": "demo-delivery",
    }


def lifecycle_issues(metadata: dict[str, str]) -> list[dict[str, object]]:
    return [issue(issue_id, key, parent="demo-root") for key, issue_id in metadata.items()]


def test_projection_derives_complete_graph_without_reading_beads_files(tmp_path: Path) -> None:
    module = load_script("build-beads-review-projection.py")
    metadata = lifecycle_metadata()
    root = issue("demo-root", "Demo", metadata=metadata)
    lifecycle = lifecycle_issues(metadata)
    task = issue(
        "demo-task",
        "Change contract",
        parent="demo-impl",
        metadata={"validation_commands": "pytest -q tests/test_contract.py", "commit_boundary": "contract change"},
        dependencies=[{"issue_id": "demo-task", "depends_on_id": "demo-impl", "type": "parent-child"}],
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(command: list[str], *, cwd: Path) -> object:
        assert cwd == tmp_path
        commands.append(tuple(command))
        if command[1:3] == ["show", "demo-root"]:
            return [root]
        if command[1:4] == ["list", "--parent", "demo-root"]:
            return lifecycle
        if command[1:4] == ["list", "--parent", "demo-impl"]:
            return [task]
        raise AssertionError(command)

    projection = module.build_projection(
        repository_root=tmp_path,
        root_id="demo-root",
        source_boundary={
            "reviewed_commit": "a" * 40,
            "reviewed_diff_base": "b" * 40,
            "reviewed_diff_digest": "sha256:" + "c" * 64,
            "allowed_paths": ["docs/src/features/demo/design.md"],
        },
        runner=fake_run,
    )

    assert not (tmp_path / ".beads").exists()
    assert projection["schema"] == "dstack.beads-review-projection.v1"
    assert projection["root"]["id"] == "demo-root"
    assert projection["implementation_coordinator"]["id"] == "demo-impl"
    assert projection["implementation_tasks"][0]["validation_commands"] == ["pytest -q tests/test_contract.py"]
    assert projection["implementation_tasks"][0]["commit_boundary"] == "contract change"
    assert projection["edges"] == [{"from": "demo-task", "to": "demo-impl", "type": "parent-child"}]
    assert module.verify_projection(projection, repository_root=tmp_path, runner=fake_run) == projection
    task["title"] = "Changed after projection"
    with pytest.raises(ValueError, match="stale"):
        module.verify_projection(projection, repository_root=tmp_path, runner=fake_run)
    assert all(command[0] == "bd" for command in commands)


def test_projection_rejects_incomplete_or_stale_graph(tmp_path: Path) -> None:
    module = load_script("build-beads-review-projection.py")
    root = issue("demo-root", "Demo", metadata={"implementation_id": "missing"})

    def fake_run(command: list[str], *, cwd: Path) -> object:
        if command[1] == "show":
            return [root]
        return []

    with pytest.raises(ValueError, match="incomplete lifecycle metadata"):
        module.build_projection(
            repository_root=tmp_path,
            root_id="demo-root",
            source_boundary={
                "reviewed_commit": "a" * 40,
                "reviewed_diff_base": "b" * 40,
                "reviewed_diff_digest": "sha256:" + "c" * 64,
                "allowed_paths": [],
            },
            runner=fake_run,
        )


def test_projection_rejects_missing_task_readiness_fields(tmp_path: Path) -> None:
    module = load_script("build-beads-review-projection.py")
    metadata = lifecycle_metadata()
    root = issue("demo-root", "Demo", metadata=metadata)
    lifecycle = lifecycle_issues(metadata)
    task = issue("demo-task", "Task", parent="demo-impl")
    task["acceptance_criteria"] = ""

    def fake_run(command: list[str], *, cwd: Path) -> object:
        if command[1:3] == ["show", "demo-root"]:
            return [root]
        if command[1:4] == ["list", "--parent", "demo-root"]:
            return lifecycle
        if command[1:4] == ["list", "--parent", "demo-impl"]:
            return [task]
        raise AssertionError(command)

    with pytest.raises(ValueError, match="incomplete readiness fields"):
        module.build_projection(
            repository_root=tmp_path,
            root_id="demo-root",
            source_boundary={
                "reviewed_commit": "a" * 40,
                "reviewed_diff_base": "b" * 40,
                "reviewed_diff_digest": "sha256:" + "c" * 64,
                "allowed_paths": [],
            },
            runner=fake_run,
        )


def valid_review_state() -> dict[str, object]:
    return {
        "schema": "dstack.review-state.v3",
        "reviewer_id": "task",
        "review_issue_id": "demo-review",
        "review_boundary_id": "demo-boundary",
        "reviewed_commit": "a" * 40,
        "reviewed_diff_base": "b" * 40,
        "reviewed_diff_digest": "sha256:" + "c" * 64,
        "state": "initial_active",
        "pass": "initial",
        "pending_conditions": [],
        "declared_domains": ["correctness"],
        "declared_paths": ["tests/test_contract.py"],
        "declared_requirement_ids": ["AC-1"],
        "current_findings": [],
        "decision": None,
        "resolved_decision": None,
        "waiver": None,
        "partial_evidence": None,
        "redesign_replacement_count": 0,
        "infrastructure_replacement_count": {"initial": 0, "verification": 0},
        "provisional": False,
        "telemetry": {
            "assignment_path_count": 1,
            "assignment_domain_count": 1,
            "elapsed_ms": None,
            "context_used_percent": None,
            "terminal_status": None,
            "replacement_cause": None,
        },
    }


def test_structured_review_note_preserves_exact_json_bytes(tmp_path: Path) -> None:
    module = load_script("append-review-note.py")
    state = valid_review_state()
    state["declared_paths"] = ["quotes-'single'-\"double\"-café.md"]
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], *, cwd: Path) -> None:
        calls.append((command, cwd))

    evidence = module.append_record(
        repository_root=tmp_path,
        issue_id="demo-review",
        kind="review-state",
        raw_json=raw,
        runner=fake_run,
    )

    assert calls == [(["bd", "update", "demo-review", "--append-notes", f"Review state: {raw}"], tmp_path)]
    assert evidence["record_sha256"]
    assert evidence["bytes"] == len(raw.encode())


def valid_finding() -> dict[str, object]:
    return {
        "schema": "dstack.review-finding.v1",
        "finding_id": "F-001",
        "domain": "workflow",
        "severity": "medium",
        "material": False,
        "protected": False,
        "status": "open",
        "source_boundary": {
            "review_issue_id": "demo-review",
            "reviewer_session_id": "demo-session",
            "reviewed_commit": "a" * 40,
            "reviewed_diff_base": "b" * 40,
            "reviewed_diff_digest": "sha256:" + "c" * 64,
        },
        "summary": "Example finding.",
        "resolution": None,
        "verification": None,
        "waiver": None,
        "supersedes_finding_id": None,
    }


def test_structured_review_note_rejects_incomplete_records(tmp_path: Path) -> None:
    module = load_script("append-review-note.py")
    with pytest.raises(ValueError, match="Invalid review state"):
        module.append_record(
            repository_root=tmp_path,
            issue_id="demo-review",
            kind="review-state",
            raw_json='{"schema":"dstack.review-state.v3"}',
        )
    with pytest.raises(ValueError, match="fields are incomplete"):
        module.append_record(
            repository_root=tmp_path,
            issue_id="demo-review",
            kind="finding",
            raw_json='{"schema":"dstack.review-finding.v1"}',
        )


def test_structured_review_note_rejects_invalid_waivers() -> None:
    module = load_script("append-review-note.py")
    finding = valid_finding()
    finding.update(status="resolved", resolution="fixed", verification="passed", waiver={"rationale": "bad"})
    with pytest.raises(ValueError, match="Only accepted"):
        module.validate_finding(finding)

    finding.update(status="accepted", resolution="accepted", verification="checked")
    with pytest.raises(ValueError, match="waiver is incomplete"):
        module.validate_finding(finding)

    finding["waiver"] = {
        "user": "maintainer",
        "rationale": "Non-material preference.",
        "scope": ["F-001"],
        "verification": "Reviewed against the source boundary.",
    }
    module.validate_finding(finding)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("resolution", {"bad": True}, "resolution and verification"),
        ("verification", ["bad"], "resolution and verification"),
        ("reviewed_commit", "not-a-sha", "reviewed_commit is invalid"),
        ("reviewed_diff_digest", "sha256:bad", "reviewed_diff_digest is invalid"),
        ("supersedes_finding_id", 7, "supersedes_finding_id is invalid"),
    ],
)
def test_structured_review_note_rejects_malformed_evidence(field: str, value: object, message: str) -> None:
    module = load_script("append-review-note.py")
    finding = valid_finding()
    finding.update(status="resolved", resolution="fixed", verification="passed")
    if field in {"reviewed_commit", "reviewed_diff_digest"}:
        boundary = cast(dict[str, object], finding["source_boundary"])
        boundary[field] = value
    else:
        finding[field] = value
    with pytest.raises(ValueError, match=message):
        module.validate_finding(finding)


def promotion_plan() -> dict[str, object]:
    return {
        "schema": "dstack.legacy-feature-promotion.v1",
        "feature_name": "Demo",
        "feature_slug": "demo",
        "design_path": "docs/src/features/demo/design.md",
        "implemented_path": "docs/src/features/demo/index.md",
        "base_branch": "main",
        "implementation_repository": "demo",
        "implementation_path": ".",
        "implementation_tasks": [
            {
                "task_key": "contract",
                "title": "Change contract",
                "description": "Change the contract.",
                "acceptance_criteria": "Contract tests pass.",
                "owner": "maintainer",
                "validation_commands": ["pytest -q tests/test_contract.py"],
                "commit_boundary": "contract change",
                "needs": [],
            }
        ],
    }


def test_legacy_promotion_rejects_dependency_cycles_before_mutation() -> None:
    module = load_script("promote-legacy-feature.py")
    for dependencies in ((["contract"],), (["second"], ["contract"])):
        plan = promotion_plan()
        tasks = cast(list[dict[str, object]], plan["implementation_tasks"])
        tasks[0]["needs"] = dependencies[0]
        if len(dependencies) == 2:
            second = dict(tasks[0])
            second.update(task_key="second", title="Second task", needs=dependencies[1])
            tasks.append(second)
        with pytest.raises(ValueError, match="contain a cycle"):
            module.validate_plan(plan)


def test_legacy_promotion_rejects_conflicting_root_identity_before_mutation(tmp_path: Path) -> None:
    module = load_script("promote-legacy-feature.py")
    commands: list[list[str]] = []
    root = {
        "id": "demo-root",
        "title": "Original",
        "issue_type": "epic",
        "labels": ["workflow:feature"],
        "metadata": {"feature_slug": "original"},
    }

    def fake_run(command: list[str], *, cwd: Path) -> object:
        commands.append(command)
        if command[1:3] == ["show", "demo-root"]:
            return [root]
        message = "Promotion mutated Beads after an identity conflict"
        raise AssertionError(message)

    with pytest.raises(ValueError, match="feature_slug"):
        module.promote_existing_root(
            repository_root=tmp_path,
            root_id="demo-root",
            formula_path=REPOSITORY_ROOT / ".beads/formulas/dstack-feature.formula.toml",
            plan=promotion_plan(),
            runner=fake_run,
        )
    assert commands == [["bd", "show", "demo-root", "--json"]]


def test_legacy_promotion_preserves_root_and_is_idempotent(tmp_path: Path) -> None:
    module = load_script("promote-legacy-feature.py")
    root_metadata: dict[str, str] = {}
    root = {
        "id": "demo-root",
        "title": "Demo",
        "issue_type": "epic",
        "labels": ["workflow:feature"],
        "metadata": root_metadata,
    }
    children: dict[str, dict[str, object]] = {}
    commands: list[list[str]] = []

    def option(command: list[str], name: str, default: str = "") -> str:
        return command[command.index(name) + 1] if name in command else default

    def fake_run(command: list[str], *, cwd: Path) -> object:
        commands.append(command)
        if command[1:3] == ["show", "demo-root"]:
            return [root]
        if command[1] == "show":
            return [children[command[2]]]
        if command[1:4] == ["list", "--parent", command[3]]:
            return [item for item in children.values() if item["parent"] == command[3]]
        if command[1] == "create":
            issue_id = f"demo-{len(children) + 1}"
            created = {
                "id": issue_id,
                "title": command[2],
                "issue_type": option(command, "--type"),
                "parent": option(command, "--parent"),
                "labels": option(command, "--labels").split(","),
                "description": option(command, "--description"),
                "acceptance_criteria": option(command, "--acceptance"),
                "owner": option(command, "--assignee") or None,
                "metadata": json.loads(option(command, "--metadata")),
                "dependencies": [],
            }
            children[issue_id] = created
            return created
        if command[1:3] == ["dep", "add"]:
            dependencies = cast(list[object], children[command[3]]["dependencies"])
            dependencies.append(
                {"issue_id": command[3], "depends_on_id": command[4], "type": option(command, "--type")}
            )
            return {}
        if command[1:3] == ["update", "demo-root"]:
            for index, value in enumerate(command):
                if value == "--set-metadata":
                    key, item = command[index + 1].split("=", 1)
                    root_metadata[key] = item
            return [root]
        raise AssertionError(command)

    plan = promotion_plan()
    formula = REPOSITORY_ROOT / ".beads/formulas/dstack-feature.formula.toml"
    first = module.promote_existing_root(
        repository_root=tmp_path,
        root_id="demo-root",
        formula_path=formula,
        plan=plan,
        runner=fake_run,
    )
    creates = sum(command[1] == "create" for command in commands)
    second = module.promote_existing_root(
        repository_root=tmp_path,
        root_id="demo-root",
        formula_path=formula,
        plan=plan,
        runner=fake_run,
    )

    assert first == second
    assert first["root_id"] == "demo-root"
    assert root_metadata["implementation_id"] == first["lifecycle"]["implementation"]
    assert first["implementation_tasks"].keys() == {"contract"}
    assert sum(command[1] == "create" for command in commands) == creates
    assert all(command[1:3] != ["mol", "pour"] for command in commands)


def test_reviewer_and_promotion_contracts_cover_preimplementation_state() -> None:
    clarity = (REPOSITORY_ROOT / "skills/dstack-core/assets/pi-reviewers/dstack-clarity-reviewer.md").read_text(
        encoding="utf-8"
    )
    readiness = (REPOSITORY_ROOT / "skills/dstack-core/assets/pi-reviewers/dstack-readiness-reviewer.md").read_text(
        encoding="utf-8"
    )
    start = (REPOSITORY_ROOT / "skills/start-feature/SKILL.md").read_text(encoding="utf-8")

    assert "expected implementation gap" in clarity.casefold()
    assert "validated beads graph projection" in readiness.casefold()
    assert "build-beads-review-projection.py" in start
    assert "append-review-note.py" in start
    assert "promote-legacy-feature.py" in start
    for template in (
        REPOSITORY_ROOT / "docs/src/features/_template/design.md",
        REPOSITORY_ROOT / "skills/setup-project/template/docs/src/features/_template/design.md",
    ):
        assert "## Implementation Boundary" in template.read_text(encoding="utf-8")
    assert "preserve the existing feature slug and root id" in start.casefold()
    assert "canonical promotion path" in start.casefold()
