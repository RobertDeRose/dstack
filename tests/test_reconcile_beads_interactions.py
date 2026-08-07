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
print(json.dumps([{"id": issue_id, "dependencies": dependencies}]))
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


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("unrelated", "outside selected standalone issue"),
        ("malformed", "is not valid JSON"),
        ("duplicate", "repeats interaction id"),
        ("non-append", "is not an append-only change"),
        ("extra-path", "worktree must contain only an unstaged"),
        ("staged", "worktree must contain only an unstaged"),
        ("committed-early", "must remain uncommitted until standalone finalization"),
        ("commit-revert", "must remain uncommitted until standalone finalization"),
        ("mode-only", "must remain uncommitted until standalone finalization"),
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
