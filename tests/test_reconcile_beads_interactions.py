# ruff: noqa: EM102, S603

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("skills/dstack-core/scripts/reconcile-beads-interactions.py")
INTERACTIONS = Path(".beads/interactions.jsonl")


def run(*args: str | Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(arg) for arg in args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise AssertionError(f"command failed: {args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def interaction(interaction_id: str, issue_id: str) -> str:
    return json.dumps(
        {
            "id": interaction_id,
            "kind": "field_change",
            "created_at": "2026-07-29T12:00:00Z",
            "actor": "Test Agent",
            "issue_id": issue_id,
        },
        separators=(",", ":"),
    )


@pytest.fixture
def interaction_worktrees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_bd = bin_dir / "bd"
    fake_bd.write_text(
        """#!/usr/bin/env python3
import json
import sys

issue_id = sys.argv[2]
dependencies = []
if issue_id == "project-discovered":
    dependencies = [{"id": "project-a.1", "dependency_type": "discovered-from"}]
if issue_id in ("project-blocked", "project-related"):
    dependencies = [{"id": "project-a.1", "dependency_type": "blocks" if issue_id == "project-blocked" else "related"}]
print(json.dumps([{"id": issue_id, "title": f"Issue {issue_id}", "dependencies": dependencies}]))
""",
        encoding="utf-8",
    )
    fake_bd.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    base = tmp_path / "project"
    feature = tmp_path / "project.feature"
    run("git", "init", "-b", "main", base)
    run("git", "-C", base, "config", "user.name", "Test User")
    run("git", "-C", base, "config", "user.email", "test@example.com")
    path = base / INTERACTIONS
    path.parent.mkdir()
    path.write_text(interaction("int-base", "project-old") + "\n", encoding="utf-8")
    run("git", "-C", base, "add", INTERACTIONS)
    run("git", "-C", base, "commit", "-m", "initial")
    run("git", "-C", base, "branch", "feat/example")
    run("git", "-C", base, "worktree", "add", feature, "feat/example")

    feature_path = feature / INTERACTIONS
    feature_path.write_text(
        feature_path.read_text(encoding="utf-8") + interaction("int-spec", "project-a.1") + "\n",
        encoding="utf-8",
    )
    run("git", "-C", feature, "add", INTERACTIONS)
    run("git", "-C", feature, "commit", "-m", "record spec state")

    path.write_text(
        path.read_text(encoding="utf-8")
        + interaction("int-close", "project-a.7")
        + "\n"
        + interaction("int-discovered", "project-discovered")
        + "\n",
        encoding="utf-8",
    )
    return base, feature


@pytest.fixture
def standalone_worktree(tmp_path: Path) -> tuple[Path, str]:
    worktree = tmp_path / "standalone"
    run("git", "init", "-b", "main", worktree)
    run("git", "-C", worktree, "config", "user.name", "Test User")
    run("git", "-C", worktree, "config", "user.email", "test@example.com")
    run("git", "-C", worktree, "config", "core.fileMode", "true")
    path = worktree / INTERACTIONS
    path.parent.mkdir()
    path.write_text(interaction("int-base", "project-old") + "\n", encoding="utf-8")
    run("git", "-C", worktree, "add", INTERACTIONS)
    run("git", "-C", worktree, "commit", "-m", "initial")
    baseline = run("git", "-C", worktree, "rev-parse", "HEAD").stdout.strip()
    return worktree, baseline


def verify_standalone(
    repository_root: Path,
    worktree: Path,
    baseline: str,
    *,
    staged: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command: list[str | Path] = [
        sys.executable,
        repository_root / SCRIPT,
        "verify-standalone",
        "--worktree",
        worktree,
        "--issue-id",
        "project-task",
        "--baseline-commit",
        baseline,
    ]
    if staged:
        command.append("--staged")
    return run(*command, check=check)


def verify_feature(
    repository_root: Path,
    worktree: Path,
    baseline: str,
    issue_id: str,
    *,
    staged: bool = False,
    expected_content_sha256: str | None = None,
    expected_mode: str | None = None,
    allow_clean: bool = False,
    lineage_only: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command: list[str | Path] = [
        sys.executable,
        repository_root / SCRIPT,
        "verify-feature",
        "--worktree",
        worktree,
        "--root-id",
        "project-a",
        "--issue-id",
        issue_id,
        "--baseline-commit",
        baseline,
    ]
    if expected_content_sha256 is not None:
        command.extend(("--expected-content-sha256", expected_content_sha256))
    if expected_mode is not None:
        command.extend(("--expected-mode", expected_mode))
    if allow_clean:
        command.append("--allow-clean")
    if lineage_only:
        command.append("--lineage-only")
    if staged:
        command.append("--staged")
    return run(*command, check=check)


def test_accepts_clean_standalone_interaction_state(
    repository_root: Path,
    standalone_worktree: tuple[Path, str],
) -> None:
    worktree, baseline = standalone_worktree

    result = verify_standalone(repository_root, worktree, baseline)

    assert json.loads(result.stdout) == {
        "dirty": False,
        "issue_id": "project-task",
        "tracked": True,
        "verified": 0,
    }


def test_accepts_clean_worktree_without_tracked_interactions(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    worktree = tmp_path / "untracked"
    run("git", "init", "-b", "main", worktree)
    run("git", "-C", worktree, "config", "user.name", "Test User")
    run("git", "-C", worktree, "config", "user.email", "test@example.com")
    (worktree / ".gitignore").write_text(".beads/\n", encoding="utf-8")
    path = worktree / INTERACTIONS
    path.parent.mkdir()
    path.write_text(interaction("int-local", "project-task") + "\n", encoding="utf-8")
    run("git", "-C", worktree, "add", ".gitignore")
    run("git", "-C", worktree, "commit", "-m", "initial")
    baseline = run("git", "-C", worktree, "rev-parse", "HEAD").stdout.strip()

    result = verify_standalone(repository_root, worktree, baseline)

    assert json.loads(result.stdout) == {
        "dirty": False,
        "issue_id": "project-task",
        "tracked": False,
        "verified": 0,
    }


def test_accepts_only_selected_standalone_interactions(
    repository_root: Path,
    standalone_worktree: tuple[Path, str],
) -> None:
    worktree, baseline = standalone_worktree
    implementation = worktree / "implementation.txt"
    implementation.write_text("implemented\n", encoding="utf-8")
    run("git", "-C", worktree, "add", implementation.name)
    run("git", "-C", worktree, "commit", "-m", "implementation")
    path = worktree / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-task", "project-task") + "\n",
        encoding="utf-8",
    )

    result = verify_standalone(repository_root, worktree, baseline)

    assert json.loads(result.stdout) == {
        "dirty": True,
        "issue_id": "project-task",
        "tracked": True,
        "verified": 1,
    }


def test_finalizes_standalone_interactions_in_a_separate_clean_commit(
    repository_root: Path,
    standalone_worktree: tuple[Path, str],
) -> None:
    worktree, baseline = standalone_worktree
    implementation = worktree / "implementation.txt"
    implementation.write_text("implemented\n", encoding="utf-8")
    run("git", "-C", worktree, "add", implementation.name)
    run("git", "-C", worktree, "commit", "-m", "implementation")
    path = worktree / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-task", "project-task") + "\n",
        encoding="utf-8",
    )

    verify_standalone(repository_root, worktree, baseline)
    run("git", "-C", worktree, "add", INTERACTIONS)
    verify_standalone(repository_root, worktree, baseline, staged=True)
    run(
        "git",
        "-C",
        worktree,
        "commit",
        "-m",
        "chore: Record standalone task evidence\n\nBeads: project-task",
    )

    assert run("git", "-C", worktree, "show", "--format=", "--name-only", "HEAD^").stdout.splitlines() == [
        implementation.name
    ]
    assert run("git", "-C", worktree, "show", "--format=", "--name-only", "HEAD").stdout.splitlines() == [
        INTERACTIONS.as_posix()
    ]
    assert run("git", "-C", worktree, "status", "--porcelain=v1").stdout == ""


def test_staged_verification_rejects_rows_added_after_worktree_verification(
    repository_root: Path,
    standalone_worktree: tuple[Path, str],
) -> None:
    worktree, baseline = standalone_worktree
    path = worktree / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-task", "project-task") + "\n",
        encoding="utf-8",
    )
    verify_standalone(repository_root, worktree, baseline)
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-race", "project-other") + "\n",
        encoding="utf-8",
    )
    run("git", "-C", worktree, "add", INTERACTIONS)

    result = verify_standalone(repository_root, worktree, baseline, staged=True, check=False)

    assert result.returncode != 0
    assert "outside selected standalone issue" in result.stderr
    assert run("git", "-C", worktree, "status", "--porcelain=v1").stdout.startswith("M  ")


def test_rejects_mode_change_combined_with_selected_interaction_append(
    repository_root: Path,
    standalone_worktree: tuple[Path, str],
) -> None:
    worktree, baseline = standalone_worktree
    path = worktree / INTERACTIONS
    path.chmod(0o755)
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-task", "project-task") + "\n",
        encoding="utf-8",
    )

    worktree_result = verify_standalone(repository_root, worktree, baseline, check=False)
    run("git", "-C", worktree, "add", INTERACTIONS)
    index_result = verify_standalone(repository_root, worktree, baseline, staged=True, check=False)

    assert worktree_result.returncode != 0
    assert index_result.returncode != 0
    assert "mode or type differs" in worktree_result.stderr
    assert "mode or type differs" in index_result.stderr
    assert run("git", "-C", worktree, "rev-parse", "HEAD").stdout.strip() == baseline


def test_finalizes_feature_work_units_at_clean_boundaries(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    path = feature / INTERACTIONS
    audit_commits: list[str] = []

    for sequence, issue_id in enumerate(("project-a.1", "project-a.2", "project-a.99"), start=1):
        baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
        additions = interaction(f"int-work-{sequence}", issue_id) + "\n"
        if sequence == 1:
            additions += interaction("int-discovered-work", "project-discovered") + "\n"
        path.write_text(path.read_text(encoding="utf-8") + additions, encoding="utf-8")
        if sequence < 3:
            implementation = feature / f"implementation-{sequence}.txt"
            implementation.write_text(f"implemented {issue_id}\n", encoding="utf-8")
            run("git", "-C", feature, "add", implementation.name)
            run("git", "-C", feature, "commit", "-m", f"implement {issue_id}")

        worktree_result = verify_feature(repository_root, feature, baseline, issue_id)
        snapshot = json.loads(worktree_result.stdout)
        assert snapshot == {
            "dirty": True,
            "issue_id": issue_id,
            "root_id": "project-a",
            "snapshot_mode": "100644",
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "tracked": True,
            "verified": 2 if sequence == 1 else 1,
        }
        run("git", "-C", feature, "add", INTERACTIONS)
        verify_feature(
            repository_root,
            feature,
            baseline,
            issue_id,
            staged=True,
            expected_content_sha256=snapshot["snapshot_sha256"],
            expected_mode=snapshot["snapshot_mode"],
        )
        run(
            "git",
            "-C",
            feature,
            "commit",
            "-m",
            f"chore: Record feature work evidence\n\nBeads: {issue_id}",
        )
        audit_commits.append(run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip())
        assert run("git", "-C", feature, "status", "--porcelain=v1").stdout == ""

    for commit in audit_commits:
        assert run("git", "-C", feature, "show", "--format=", "--name-only", commit).stdout.splitlines() == [
            INTERACTIONS.as_posix()
        ]


def test_feature_verification_rejects_a_clean_tracked_interval(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()

    result = verify_feature(repository_root, feature, baseline, "project-a.1", check=False)

    assert result.returncode != 0
    assert "no appended interaction references selected feature work unit" in result.stderr
    allowed = verify_feature(repository_root, feature, baseline, "project-a", allow_clean=True)
    assert json.loads(allowed.stdout) == {
        "dirty": False,
        "issue_id": "project-a",
        "root_id": "project-a",
        "tracked": True,
        "verified": 0,
    }
    assert run("git", "-C", feature, "status", "--porcelain=v1").stdout == ""


def test_lineage_only_feature_verification_accepts_child_interactions_without_a_root_interaction(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
    path = feature / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-child", "project-a.2") + "\n",
        encoding="utf-8",
    )

    strict = verify_feature(repository_root, feature, baseline, "project-a", check=False)
    result = verify_feature(repository_root, feature, baseline, "project-a", lineage_only=True)

    assert strict.returncode != 0
    assert "no appended interaction references selected feature work unit" in strict.stderr
    assert json.loads(result.stdout)["verified"] == 1


def test_lineage_only_feature_verification_rejects_foreign_interactions(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
    path = feature / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8")
        + interaction("int-child", "project-a.2")
        + "\n"
        + interaction("int-foreign", "project-b.1")
        + "\n",
        encoding="utf-8",
    )

    result = verify_feature(
        repository_root,
        feature,
        baseline,
        "project-a",
        lineage_only=True,
        check=False,
    )

    assert result.returncode != 0
    assert "outside selected feature lineage" in result.stderr


def test_feature_verification_rejects_an_interaction_commit_after_worktree_verification(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
    path = feature / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-current", "project-a.1") + "\n",
        encoding="utf-8",
    )
    verify_feature(repository_root, feature, baseline, "project-a.1")
    run("git", "-C", feature, "add", INTERACTIONS)
    run("git", "-C", feature, "commit", "-m", "premature feature interaction commit")

    result = verify_feature(repository_root, feature, baseline, "project-a.1", check=False)

    assert result.returncode != 0
    assert "must remain uncommitted until work-unit finalization" in result.stderr
    assert run("git", "-C", feature, "status", "--porcelain=v1").stdout == ""


def test_feature_verification_rejects_a_same_lineage_snapshot_race(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
    path = feature / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-current", "project-a.1") + "\n",
        encoding="utf-8",
    )
    worktree_result = verify_feature(repository_root, feature, baseline, "project-a.1")
    snapshot = json.loads(worktree_result.stdout)
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-sibling", "project-a.2") + "\n",
        encoding="utf-8",
    )
    run("git", "-C", feature, "add", INTERACTIONS)

    result = verify_feature(
        repository_root,
        feature,
        baseline,
        "project-a.1",
        staged=True,
        expected_content_sha256=snapshot["snapshot_sha256"],
        expected_mode=snapshot["snapshot_mode"],
        check=False,
    )

    assert result.returncode != 0
    assert "content changed after work-unit verification" in result.stderr
    assert run("git", "-C", feature, "status", "--porcelain=v1").stdout.startswith("M  ")


def test_feature_staged_snapshot_rejects_index_mutation_after_revalidation(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
    path = feature / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-current", "project-a.1") + "\n",
        encoding="utf-8",
    )
    worktree_result = verify_feature(repository_root, feature, baseline, "project-a.1")
    snapshot = json.loads(worktree_result.stdout)
    run("git", "-C", feature, "add", INTERACTIONS)
    verify_feature(
        repository_root,
        feature,
        baseline,
        "project-a.1",
        staged=True,
        expected_content_sha256=snapshot["snapshot_sha256"],
        expected_mode=snapshot["snapshot_mode"],
    )
    path.write_text(
        path.read_text(encoding="utf-8") + interaction("int-index-race", "project-a.2") + "\n",
        encoding="utf-8",
    )
    run("git", "-C", feature, "add", INTERACTIONS)

    result = verify_feature(
        repository_root,
        feature,
        baseline,
        "project-a.1",
        staged=True,
        expected_content_sha256=snapshot["snapshot_sha256"],
        expected_mode=snapshot["snapshot_mode"],
        check=False,
    )

    assert result.returncode != 0
    assert "content changed after work-unit verification" in result.stderr


def test_feature_verification_rejects_interactions_outside_the_selected_lineage(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    _base, feature = interaction_worktrees
    baseline = run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip()
    path = feature / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8")
        + interaction("int-current", "project-a.1")
        + "\n"
        + interaction("int-foreign", "project-b.1")
        + "\n",
        encoding="utf-8",
    )

    result = verify_feature(repository_root, feature, baseline, "project-a.1", check=False)

    assert result.returncode != 0
    assert "outside selected feature lineage" in result.stderr
    assert run("git", "-C", feature, "rev-parse", "HEAD").stdout.strip() == baseline


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("unrelated", "outside selected standalone issue"),
        ("malformed", "is not valid JSON"),
        ("duplicate", "repeats interaction id"),
        ("non-append", "is not an append-only change"),
        ("extra-path", "worktree must contain only an unstaged"),
        ("staged", "worktree must contain only an unstaged"),
        ("committed-early", "must remain uncommitted until work-unit finalization"),
        ("commit-revert", "must remain uncommitted until work-unit finalization"),
        ("mode-only", "must remain uncommitted until work-unit finalization"),
    ],
)
def test_rejects_unsafe_standalone_interactions_without_mutation(
    repository_root: Path,
    standalone_worktree: tuple[Path, str],
    case: str,
    expected_error: str,
) -> None:
    worktree, baseline = standalone_worktree
    path = worktree / INTERACTIONS
    if case == "unrelated":
        path.write_text(
            path.read_text(encoding="utf-8") + interaction("int-other", "project-other") + "\n",
            encoding="utf-8",
        )
    elif case == "malformed":
        path.write_text(path.read_text(encoding="utf-8") + "{not-json}\n", encoding="utf-8")
    elif case == "duplicate":
        path.write_text(
            path.read_text(encoding="utf-8") + interaction("int-base", "project-task") + "\n",
            encoding="utf-8",
        )
    elif case == "non-append":
        path.write_text(interaction("int-task", "project-task") + "\n", encoding="utf-8")
    elif case == "mode-only":
        path.chmod(0o755)
        run("git", "-C", worktree, "add", INTERACTIONS)
        run("git", "-C", worktree, "commit", "-m", "premature mode change")
    else:
        path.write_text(
            path.read_text(encoding="utf-8") + interaction("int-task", "project-task") + "\n",
            encoding="utf-8",
        )
        if case == "extra-path":
            (worktree / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
        elif case == "staged":
            run("git", "-C", worktree, "add", INTERACTIONS)
        elif case == "commit-revert":
            run("git", "-C", worktree, "add", INTERACTIONS)
            run("git", "-C", worktree, "commit", "-m", "premature interaction commit")
            run("git", "-C", worktree, "checkout", baseline, "--", INTERACTIONS)
            run("git", "-C", worktree, "commit", "-m", "restore interaction baseline")
        else:
            run("git", "-C", worktree, "add", INTERACTIONS)
            run("git", "-C", worktree, "commit", "-m", "premature interaction commit")
    before = {
        "head": run("git", "-C", worktree, "rev-parse", "HEAD").stdout,
        "status": run("git", "-C", worktree, "status", "--porcelain=v1").stdout,
        "interactions": path.read_bytes(),
    }

    result = verify_standalone(repository_root, worktree, baseline, check=False)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert run("git", "-C", worktree, "rev-parse", "HEAD").stdout == before["head"]
    assert run("git", "-C", worktree, "status", "--porcelain=v1").stdout == before["status"]
    assert path.read_bytes() == before["interactions"]


def test_inspect_reports_selected_and_foreign_appends_without_mutation(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    base, _feature = interaction_worktrees
    path = base / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8")
        + interaction("int-foreign-a", "project-b.1")
        + "\n"
        + interaction("int-foreign-b", "project-b.2")
        + "\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    result = run(
        sys.executable,
        repository_root / SCRIPT,
        "inspect",
        "--worktree",
        base,
        "--root-id",
        "project-a",
    )

    report = json.loads(result.stdout)

    assert [row["interaction_id"] for row in report["selected"]] == ["int-close", "int-discovered"]
    assert [row["interaction_id"] for row in report["foreign"]] == ["int-foreign-a", "int-foreign-b"]
    assert all(row["title"].startswith("Issue ") for row in report["foreign"])
    assert {row["actor"] for row in report["foreign"]} == {"Test Agent"}
    assert {row["created_at"] for row in report["foreign"]} == {"2026-07-29T12:00:00Z"}
    assert path.read_bytes() == before
    assert run("git", "-C", base, "status", "--porcelain=v1").stdout == " M .beads/interactions.jsonl\n"


def test_inspect_does_not_promote_blocks_or_related_edges_to_ownership(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    base, _feature = interaction_worktrees
    path = base / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8")
        + interaction("int-blocked", "project-blocked")
        + "\n"
        + interaction("int-related", "project-related")
        + "\n",
        encoding="utf-8",
    )

    result = run(
        sys.executable,
        repository_root / SCRIPT,
        "inspect",
        "--worktree",
        base,
        "--root-id",
        "project-a",
    )
    report = json.loads(result.stdout)

    assert [row["issue_id"] for row in report["foreign"]] == ["project-blocked", "project-related"]


def test_prepare_reports_all_foreign_appends_without_mutation(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    base, feature = interaction_worktrees
    path = base / INTERACTIONS
    path.write_text(
        path.read_text(encoding="utf-8")
        + interaction("int-foreign-a", "project-b.1")
        + "\n"
        + interaction("int-foreign-b", "project-b.2")
        + "\n",
        encoding="utf-8",
    )
    before_base = path.read_bytes()
    before_feature = (feature / INTERACTIONS).read_bytes()

    result = run(
        sys.executable,
        repository_root / SCRIPT,
        "prepare",
        "--base-worktree",
        base,
        "--feature-worktree",
        feature,
        "--root-id",
        "project-a",
        check=False,
    )

    assert result.returncode != 0
    assert "int-foreign-a" in result.stderr
    assert "int-foreign-b" in result.stderr
    assert path.read_bytes() == before_base
    assert (feature / INTERACTIONS).read_bytes() == before_feature


def test_preflight_requires_a_clean_worktree_before_closeout(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    base, _feature = interaction_worktrees

    result = run(
        sys.executable,
        repository_root / SCRIPT,
        "preflight",
        "--worktree",
        base,
        "--root-id",
        "project-a",
        check=False,
    )

    assert result.returncode != 0
    assert "preflight requires a clean worktree" in result.stderr
    assert run("git", "-C", base, "status", "--porcelain=v1").stdout == " M .beads/interactions.jsonl\n"


def test_reconciles_only_committed_feature_interactions(
    repository_root: Path,
    interaction_worktrees: tuple[Path, Path],
) -> None:
    base, feature = interaction_worktrees
    script = repository_root / SCRIPT
    common = (
        "--base-worktree",
        base,
        "--feature-worktree",
        feature,
        "--root-id",
        "project-a",
    )

    feature_path = feature / INTERACTIONS
    for interaction_id, issue_id in (
        ("int-child-audit", "project-a.2"),
        ("int-coordinator-audit", "project-a.99"),
    ):
        feature_path.write_text(
            feature_path.read_text(encoding="utf-8") + interaction(interaction_id, issue_id) + "\n",
            encoding="utf-8",
        )
        run("git", "-C", feature, "add", INTERACTIONS)
        run("git", "-C", feature, "commit", "-m", f"record {issue_id} interaction boundary")

    run(sys.executable, script, "prepare", *common)
    assert "int-spec" in (feature / INTERACTIONS).read_text(encoding="utf-8")
    assert "int-close" in (feature / INTERACTIONS).read_text(encoding="utf-8")
    assert "int-discovered" in (feature / INTERACTIONS).read_text(encoding="utf-8")
    assert run(sys.executable, script, "finalize", *common, check=False).returncode != 0

    run("git", "-C", feature, "add", INTERACTIONS)
    run("git", "-C", feature, "commit", "-m", "record close state")
    run(sys.executable, script, "finalize", *common)
    assert run("git", "-C", base, "status", "--porcelain").stdout == ""

    run("git", "-C", base, "merge", "--ff-only", "feat/example")
    base_path = base / INTERACTIONS
    merged_interactions = base_path.read_text(encoding="utf-8")
    assert "int-child-audit" in merged_interactions
    assert "int-coordinator-audit" in merged_interactions
    base_path.write_text(
        base_path.read_text(encoding="utf-8") + interaction("int-delivery", "project-a") + "\n",
        encoding="utf-8",
    )
    run(
        sys.executable,
        script,
        "verify-post-merge",
        "--base-worktree",
        base,
        "--root-id",
        "project-a",
    )

    base_path.write_text(
        base_path.read_text(encoding="utf-8") + interaction("int-foreign", "project-b.1") + "\n",
        encoding="utf-8",
    )
    result = run(
        sys.executable,
        script,
        "verify-post-merge",
        "--base-worktree",
        base,
        "--root-id",
        "project-a",
        check=False,
    )
    assert result.returncode != 0
    assert "outside selected feature lineage" in result.stderr
