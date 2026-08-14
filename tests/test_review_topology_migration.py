"""Behavior tests for finite review-topology migration."""

# ruff: noqa: S603 - tests invoke the fixed local migration helper.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import Any, cast

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "skills/dstack-core/scripts/migrate-review-topology.py"
NEW_KINDS = ("specification-clarity", "execution-readiness", "implementation-integrity", "delivery-integrity")
OLD_KINDS = ("architecture", "simplicity", "documentation", "execution", "delivery", "drift")


def issue(
    issue_id: str, *, status: str = "open", metadata: dict[str, object] | None = None, labels: list[str] | None = None
) -> dict[str, object]:
    return {
        "id": issue_id,
        "title": issue_id,
        "status": status,
        "metadata": metadata or {},
        "labels": labels or [],
        "notes": f"evidence for {issue_id}",
        "dependencies": [],
    }


def old_snapshot(phase: str = "unstarted") -> dict[str, object]:
    root_id = "test-root"
    children = [
        issue("design", metadata={"workflow_phase": "design"}),
        issue("spec", metadata={"workflow_phase": "spec-ready"}),
        issue("implementation", metadata={"workflow_phase": "implementation"}),
        issue("docs", metadata={"workflow_phase": "closeout", "closeout_kind": "documentation"}),
        issue("validate", metadata={"workflow_phase": "closeout", "closeout_kind": "validation"}),
        issue("delivery", metadata={"workflow_phase": "delivery"}),
    ]
    statuses = {
        "unstarted": {},
        "spec-review": {"design": "closed"},
        "implementation": {"design": "closed", "spec": "closed"},
        "close-out": {"design": "closed", "spec": "closed", "implementation": "closed"},
        "delivered": {"delivery": "closed"},
    }[phase]
    for item in children:
        item["status"] = statuses.get(str(item["id"]), item["status"])
    for kind in OLD_KINDS:
        children.append(issue(f"old-{kind}", status="closed", metadata={"review_kind": kind}))
    by_id = {str(item["id"]): item for item in children}
    by_id["spec"]["dependencies"] = [
        {"id": f"old-{kind}", "dependency_type": "blocks"}
        for kind in ("architecture", "simplicity", "documentation", "execution")
    ]
    by_id["delivery"]["dependencies"] = [
        {"id": f"old-{kind}", "dependency_type": "blocks"} for kind in ("delivery", "drift")
    ]
    return {"root": issue(root_id, metadata={"feature_name": "Test feature"}), "children": children}


def load_module() -> Any:
    import importlib.util

    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("review_topology", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("phase", ["unstarted", "spec-review", "implementation", "close-out"])
def test_migration_plan_maps_evidence_without_transferring_approval(phase: str) -> None:
    module = load_module()
    result = module.plan(old_snapshot(phase), phase)

    assert result["schema"] == "dstack.review-topology-plan.v1"
    assert result["applicable"] is True
    assert result["target_ids"] == {kind: f"test-root-{kind}" for kind in NEW_KINDS}
    assert set(result["evidence_map"]) == set(OLD_KINDS)
    assert all(item["status"] == "closed" for item in result["evidence_map"].values())
    assert result["plan_digest"].startswith("sha256:")


def test_delivered_feature_is_not_rewritten() -> None:
    module = load_module()
    result = module.plan(old_snapshot("delivered"), "delivered")
    assert result["applicable"] is False
    assert "retain historical topology" in result["reason"]
    assert module.validate_plan(result) == result
    assert module.apply(Path.cwd(), result, "bd", None, None)["status"] == "not_applicable"


class FakeBd:
    def __init__(self, module: Any, snapshot: dict[str, object]) -> None:
        self.module = module
        self.fail_update_parent = False
        self.fail_dependency_add = False
        self.fail_dependency_add_once = False
        root = cast(dict[str, Any], snapshot["root"])
        children = cast(list[dict[str, Any]], snapshot["children"])
        self.issues: dict[str, dict[str, Any]] = {item["id"]: item for item in [root, *children]}
        self.edges: set[tuple[str, str]] = set()
        self.deleted: list[str] = []

    def json(self, *arguments: str) -> Any:
        if arguments[0] == "show":
            item = self.issues.get(arguments[1])
            if item is None:
                message = "missing"
                raise self.module.MigrationError(message)
            return [item]
        if arguments[0] == "children":
            return [value for key, value in self.issues.items() if key != "test-root"]
        raise AssertionError(arguments)

    def run(self, *arguments: str, check: bool = True, input_text: str | None = None) -> Any:
        del input_text
        command = arguments[0]
        if command == "show":
            return self.module.CommandResult(0 if arguments[1] in self.issues else 1, "", "")
        if command == "create":
            if "--parent" in arguments or "--deps" in arguments:
                message = "invalid create shape"
                raise AssertionError(message)
            issue_id = arguments[arguments.index("--id") + 1]
            metadata = json.loads(arguments[arguments.index("--metadata") + 1])
            labels = arguments[arguments.index("--labels") + 1].split(",")
            self.issues[issue_id] = issue(issue_id, metadata=metadata, labels=labels)
            self.issues[issue_id]["notes"] = arguments[arguments.index("--notes") + 1]
            return self.module.CommandResult(0, "", "")
        if command == "dep":
            if (self.fail_dependency_add or self.fail_dependency_add_once) and arguments[1] == "add":
                self.fail_dependency_add_once = False
                message = "injected dependency failure"
                raise self.module.MigrationError(message)
            source, target_id = arguments[2], arguments[3]
            target = self.issues[source]
            dependencies = target.setdefault("dependencies", [])
            if arguments[1] == "add":
                self.edges.add((source, target_id))
                if not any(item.get("id") == target_id for item in dependencies):
                    dependencies.append({"id": target_id, "dependency_type": "blocks"})
            else:
                self.edges.discard((source, target_id))
                target["dependencies"] = [item for item in dependencies if item.get("id") != target_id]
            return self.module.CommandResult(0, "", "")
        if command == "update":
            if self.fail_update_parent and "--parent" in arguments:
                message = "injected parent failure"
                raise self.module.MigrationError(message)
            target = self.issues[arguments[1]]
            for index, value in enumerate(arguments):
                if value == "--status":
                    target["status"] = arguments[index + 1]
                elif value == "--add-label":
                    target.setdefault("labels", []).append(arguments[index + 1])
                elif value == "--remove-label":
                    target["labels"] = [item for item in target.get("labels", []) if item != arguments[index + 1]]
                elif value == "--set-metadata":
                    key, raw = arguments[index + 1].split("=", 1)
                    target.setdefault("metadata", {})[key] = raw
                elif value == "--parent":
                    target["parent"] = arguments[index + 1]
                elif value == "--unset-metadata":
                    target.setdefault("metadata", {}).pop(arguments[index + 1], None)
            return self.module.CommandResult(0, "", "")
        if command in {"close", "reopen"}:
            self.issues[arguments[1]]["status"] = "closed" if command == "close" else "open"
            return self.module.CommandResult(0, "", "")
        if command == "delete":
            self.deleted.append(arguments[1])
            self.issues.pop(arguments[1], None)
            return self.module.CommandResult(0, "", "")
        if check:
            raise AssertionError(arguments)
        return self.module.CommandResult(1, "", "")


def patch_apply(monkeypatch: pytest.MonkeyPatch, module: Any, fake: FakeBd, repository: Path) -> None:
    monkeypatch.setattr(module, "Bd", lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(module, "verify_primary_worktree", lambda _repository: None)
    monkeypatch.setattr(module, "interaction_preflight", lambda _repository, _root: "baseline")
    monkeypatch.setattr(module, "interaction_verify", lambda _repository, _root, _baseline: None)


def assert_no_new_targets(fake: FakeBd) -> None:
    assert not any(item.endswith(NEW_KINDS) for item in fake.issues)


def add_verified_targets(module: Any, fake: FakeBd, plan: dict[str, Any], *, status: str = "closed") -> None:
    ids = cast(dict[str, str], plan["target_ids"])
    fake.issues["test-root"]["metadata"] = {
        **cast(dict[str, object], fake.issues["test-root"]["metadata"]),
        **{module.TARGET_METADATA[kind]: ids[kind] for kind in NEW_KINDS},
        "review_topology_cutover": json.dumps(module.marker(plan), sort_keys=True, separators=(",", ":")),
    }
    for kind, issue_id in ids.items():
        target = fake.issues[issue_id] = issue(issue_id, status=status, metadata={"review_kind": kind})
        target["parent"] = "test-root"
        target["labels"] = [f"review:{kind}"]
        target["notes"] = module.mapping_note(plan, kind)
        target["dependencies"] = [
            {"id": prerequisite, "dependency_type": "blocks"}
            for prerequisite in module.target_prerequisites(plan, kind)
        ]
    fake.issues["spec"]["dependencies"] = [{"id": ids[kind], "dependency_type": "blocks"} for kind in NEW_KINDS[:2]]
    fake.issues["delivery"]["dependencies"] = [{"id": ids[kind], "dependency_type": "blocks"} for kind in NEW_KINDS[2:]]
    for kind in OLD_KINDS:
        fake.issues[f"old-{kind}"]["status"] = "closed"
        fake.issues[f"old-{kind}"]["labels"] = ["review:superseded"]


@pytest.mark.parametrize("failure", ["parent", "dependency"])
def test_apply_rolls_back_target_when_create_target_step_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    module = load_module()
    repository = tmp_path / f"repo-{failure}"
    repository.mkdir()
    fake = FakeBd(module, old_snapshot())
    fake.fail_update_parent = failure == "parent"
    fake.fail_dependency_add = failure == "dependency"
    patch_apply(monkeypatch, module, fake, repository)
    with pytest.raises(module.MigrationError, match="injected"):
        module.apply(repository, module.plan(old_snapshot(), "unstarted"), "bd", tmp_path / f"locks-{failure}", None)
    assert_no_new_targets(fake)


def test_apply_rolls_back_injected_failure_and_retries_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    repository = tmp_path / "repo"
    repository.mkdir()
    git = which("git")
    assert git is not None
    subprocess.run([git, "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
    snapshot = old_snapshot()
    fake = FakeBd(module, snapshot)
    plan = module.plan(snapshot, "unstarted")
    patch_apply(monkeypatch, module, fake, repository)
    with pytest.raises(module.MigrationError, match="injected migration failure"):
        module.apply(repository, plan, "bd", tmp_path / "locks", 2)
    assert_no_new_targets(fake)
    result = module.apply(repository, plan, "bd", tmp_path / "locks", None)
    repeated = module.apply(repository, plan, "bd", tmp_path / "locks", None)
    assert result["status"] == repeated["status"] == "verified"
    assert all(fake.issues[f"test-root-{kind}"]["status"] == "open" for kind in NEW_KINDS)
    assert json.loads(fake.issues["test-root"]["metadata"]["review_topology_cutover"])["approval_transferred"] is False


@pytest.mark.parametrize("phase", ["unstarted", "spec-review", "implementation"])
def test_guard_allows_progressed_migrated_review_statuses(phase: str) -> None:
    module = load_module()
    snapshot = old_snapshot(phase)
    plan = module.plan(snapshot, phase)
    fake = FakeBd(module, snapshot)
    add_verified_targets(module, fake, plan)
    assert module.verify_cutover(fake, plan)["status"] == "verified"


def test_verify_allows_closed_close_gates_after_approval() -> None:
    module = load_module()
    snapshot = old_snapshot("close-out")
    plan = module.plan(snapshot, "close-out")
    fake = FakeBd(module, snapshot)
    add_verified_targets(module, fake, plan)
    assert module.verify_cutover(fake, plan)["status"] == "verified"


def test_repair_reversed_prerequisite_edge_restores_it_when_add_fails() -> None:
    module = load_module()
    snapshot = old_snapshot("close-out")
    plan = module.plan(snapshot, "close-out")
    fake = FakeBd(module, snapshot)
    add_verified_targets(module, fake, plan)
    ids = cast(dict[str, str], plan["target_ids"])
    issue_id = ids["implementation-integrity"]
    prerequisite = module.target_prerequisites(plan, "implementation-integrity")[0]
    fake.issues[issue_id]["dependencies"] = []
    fake.issues[prerequisite].setdefault("dependencies", []).append({"id": issue_id, "dependency_type": "blocks"})
    fake.fail_dependency_add_once = True

    with pytest.raises(module.MigrationError, match="injected dependency failure"):
        module.repair_reversed_prerequisite_edges(fake, plan)

    assert any(item.get("id") == issue_id for item in fake.issues[prerequisite]["dependencies"])


def test_apply_repairs_legacy_reversed_prerequisite_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    repository = tmp_path / "repo-repair"
    repository.mkdir()
    snapshot = old_snapshot("close-out")
    fake = FakeBd(module, snapshot)
    plan = module.plan(snapshot, "close-out")
    patch_apply(monkeypatch, module, fake, repository)
    assert module.apply(repository, plan, "bd", tmp_path / "locks-repair", None)["status"] == "verified"
    ids = cast(dict[str, str], plan["target_ids"])
    prerequisites = {kind: module.target_prerequisites(plan, kind) for kind in NEW_KINDS}
    for kind, prerequisite_ids in prerequisites.items():
        for prerequisite_id in prerequisite_ids:
            target_dependencies = fake.issues[ids[kind]]["dependencies"]
            fake.issues[ids[kind]]["dependencies"] = [
                item for item in target_dependencies if item.get("id") != prerequisite_id
            ]
            fake.issues[prerequisite_id].setdefault("dependencies", []).append(
                {"id": ids[kind], "dependency_type": "blocks"}
            )
    fake.issues[ids["delivery-integrity"]]["status"] = "in_progress"
    assert module.apply(repository, plan, "bd", tmp_path / "locks-repair", None)["status"] == "verified"
    for kind, prerequisite_ids in prerequisites.items():
        target_dependencies = fake.issues[ids[kind]]["dependencies"]
        assert {item["id"] for item in target_dependencies} >= set(prerequisite_ids)
        for prerequisite_id in prerequisite_ids:
            assert not any(item.get("id") == ids[kind] for item in fake.issues[prerequisite_id]["dependencies"])


def test_unrelated_fixed_id_collision_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    repository = tmp_path / "repo"
    repository.mkdir()
    snapshot = old_snapshot()
    fake = FakeBd(module, snapshot)
    fake.issues["test-root-specification-clarity"] = issue(
        "test-root-specification-clarity", metadata={"review_kind": "unrelated"}
    )
    plan = module.plan(snapshot, "unstarted")
    patch_apply(monkeypatch, module, fake, repository)
    with pytest.raises(module.MigrationError, match=r"collides with unrelated work|snapshot changed"):
        module.apply(repository, plan, "bd", tmp_path / "locks", None)
    collision = fake.issues["test-root-specification-clarity"]
    metadata = cast(dict[str, Any], collision.get("metadata"))
    assert metadata["review_kind"] == "unrelated"


def test_duplicate_old_review_kind_is_rejected() -> None:
    module = load_module()
    snapshot = old_snapshot()
    cast(list[dict[str, object]], snapshot["children"]).append(
        issue("duplicate-architecture", metadata={"review_kind": "architecture"})
    )
    with pytest.raises(module.MigrationError, match="exactly one review per kind"):
        module.plan(snapshot, "unstarted")


def test_tampered_plan_and_wrong_phase_fail_before_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    snapshot = old_snapshot("implementation")
    with pytest.raises(module.MigrationError, match="disagrees with graph phase"):
        module.plan(snapshot, "close-out")
    plan = module.plan(snapshot, "implementation")
    plan["lifecycle"]["delivery"] = "unrelated"
    plan["plan_digest"] = module.digest({key: value for key, value in plan.items() if key != "plan_digest"})
    fake = FakeBd(module, snapshot)
    repository = tmp_path / "repo"
    repository.mkdir()
    patch_apply(monkeypatch, module, fake, repository)
    with pytest.raises(module.MigrationError, match="plan does not match"):
        module.apply(repository, plan, "bd", tmp_path / "locks", None)


def test_implementation_phase_interruption_restores_spec_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    repository = tmp_path / "repo-implementation"
    repository.mkdir()
    snapshot = old_snapshot("implementation")
    fake = FakeBd(module, snapshot)
    patch_apply(monkeypatch, module, fake, repository)
    with pytest.raises(module.MigrationError, match="injected migration failure"):
        module.apply(repository, module.plan(snapshot, "implementation"), "bd", tmp_path / "locks", 6)
    assert fake.issues["spec"]["status"] == "closed"


def test_cutover_target_matching_preserves_append_only_audit_notes() -> None:
    module = load_module()
    snapshot = old_snapshot("close-out")
    plan = module.plan(snapshot, "close-out")
    target = issue(
        cast(dict[str, str], plan["target_ids"])["delivery-integrity"],
        status="open",
        metadata={"review_kind": "delivery-integrity", "workflow_phase": "closeout-review"},
        labels=["phase:closeout", "review:delivery-integrity", "workflow:feature-lifecycle"],
    )
    target["parent"] = "test-root"
    target["notes"] = module.mapping_note(plan, "delivery-integrity") + '\nReview state: {"state":"initial_active"}'
    assert module.target_matches_plan(target, plan, "delivery-integrity")
    target["notes"] = "tampered\n" + str(target["notes"])
    assert not module.target_matches_plan(target, plan, "delivery-integrity")


def test_rollback_restores_preexisting_root_metadata_without_quoting() -> None:
    module = load_module()
    snapshot = old_snapshot()
    root = cast(dict[str, Any], snapshot["root"])
    root["metadata"] = {
        **cast(dict[str, Any], root["metadata"]),
        "review_implementation_integrity_id": "existing-review-id",
    }
    plan = module.plan(snapshot, "unstarted")
    fake = FakeBd(module, snapshot)

    module.rollback(fake, plan, [])

    assert fake.issues["test-root"]["metadata"]["review_implementation_integrity_id"] == "existing-review-id"


@pytest.mark.parametrize("marker", ['"corrupt"', "[]", "true"])
def test_present_non_object_cutover_marker_is_rejected(marker: str) -> None:
    module = load_module()
    root = issue("test-root", metadata={"review_topology_cutover": marker})
    with pytest.raises(module.MigrationError, match="must be an object"):
        module.marker_from_root(cast(dict[str, Any], root))


def test_markerless_new_topology_rejects_stale_controller(tmp_path: Path) -> None:
    fake_bd = tmp_path / "bd"
    root = issue("test-root")
    targets = [issue(f"test-root-{kind}", metadata={"review_kind": kind}) for kind in NEW_KINDS]
    fake_bd.write_text(
        "#!/bin/sh\n"
        f"root='{json.dumps([root])}'\n"
        f"children='{json.dumps(targets)}'\n"
        'case "$*" in *children*) printf "%s\\n" "$children" ;; *) printf "%s\\n" "$root" ;; esac\n',
        encoding="utf-8",
    )
    fake_bd.chmod(0o755)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository-root",
            str(tmp_path),
            "--bd",
            str(fake_bd),
            "guard",
            "--root-id",
            "test-root",
            "--controller-topology-version",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "predates the markerless" in result.stdout


def test_stale_controller_guard_fails_after_cutover(tmp_path: Path) -> None:
    fake_bd = tmp_path / "bd"
    marker = {
        "schema": "dstack.review-topology-cutover.v1",
        "topology_version": 2,  # stale-controller fixture
        "root_id": "test-root",
    }
    payload = [issue("test-root", metadata={"review_topology_cutover": marker})]
    fake_bd.write_text(f"#!/bin/sh\nprintf '%s\\n' '{json.dumps(payload)}'\n", encoding="utf-8")
    fake_bd.chmod(0o755)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository-root",
            str(tmp_path),
            "--bd",
            str(fake_bd),
            "guard",
            "--root-id",
            "test-root",
            "--controller-topology-version",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "controller predates" in result.stdout
