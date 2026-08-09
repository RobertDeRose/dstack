# ruff: noqa: EM102, S603

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "skills/dstack-core/scripts/verify-delivery-state.py"
FINALIZE_SCRIPT = Path(__file__).parents[1] / "skills/dstack-core/scripts/finalize-feature-delivery.py"


def run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise AssertionError(f"command failed: {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def prepare_delivery_repository(tmp_path: Path, *, stale_claim: bool = False) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    run(["git", "init", "-b", "main"], cwd=repository)
    run(["git", "config", "user.name", "Test User"], cwd=repository)
    run(["git", "config", "user.email", "test@example.com"], cwd=repository)

    record = repository / "docs/src/features/example/index.md"
    reader_page = repository / "docs/src/operations/example.md"
    record.parent.mkdir(parents=True)
    reader_page.parent.mkdir(parents=True)
    record.write_text(
        "# Example\n\n## Delivery Summary\n\n- Status: delivered\n- Merge commit: pending\n",
        encoding="utf-8",
    )
    reader_page.write_text(
        "# Example operations\n\nThe feature is available.\n",
        encoding="utf-8",
    )
    run(["git", "add", "."], cwd=repository)
    run(["git", "commit", "-m", "deliver example"], cwd=repository)
    merge_sha = run(["git", "rev-parse", "HEAD"], cwd=repository).stdout.strip()

    record.write_text(
        f"# Example\n\n## Delivery Summary\n\n- Status: delivered\n- Merge commit: `{merge_sha}` (fast-forward)\n",
        encoding="utf-8",
    )
    if stale_claim:
        reader_page.write_text(
            "# Example operations\n\nThe merge is pending.\n",
            encoding="utf-8",
        )
    run(["git", "add", "."], cwd=repository)
    run(["git", "commit", "-m", "record final delivery state"], cwd=repository)
    return repository, merge_sha


def verify(repository: Path, merge_sha: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            str(SCRIPT),
            "--base-worktree",
            str(repository),
            "--base-branch",
            "main",
            "--record",
            "docs/src/features/example/index.md",
            "--merge-sha",
            merge_sha,
            "--path",
            "docs/src/operations/example.md",
        ],
        cwd=repository,
        check=False,
    )


def test_delivery_state_verifier_accepts_reconciled_delivery(tmp_path: Path) -> None:
    repository, merge_sha = prepare_delivery_repository(tmp_path)

    result = verify(repository, merge_sha)

    assert result.returncode == 0, result.stderr
    assert "Delivery state verified" in result.stdout


def test_delivery_state_verifier_rejects_stale_pending_claim(tmp_path: Path) -> None:
    repository, merge_sha = prepare_delivery_repository(tmp_path, stale_claim=True)

    result = verify(repository, merge_sha)

    assert result.returncode == 1
    assert "stale delivery claim" in result.stderr


def install_fake_bd(tmp_path: Path, *, log: Path, status: str = "open") -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bd").write_text(
        f"""#!/usr/bin/env python3
import json
import pathlib
import sys

pathlib.Path({str(log)!r}).write_text(" ".join(sys.argv[1:]) + "\\n", encoding="utf-8")
if sys.argv[1] == "show":
    print(json.dumps([{{"id": sys.argv[2], "status": {status!r}}}]))
else:
    print(json.dumps([]))
""",
        encoding="utf-8",
    )
    (bin_dir / "bd").chmod(0o755)
    return bin_dir


def finalize(
    repository: Path,
    merge_sha: str,
    finalizer_sha: str,
    *,
    path: str = "docs/src/operations/example.md",
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            str(FINALIZE_SCRIPT),
            "--base-worktree",
            str(repository),
            "--base-branch",
            "main",
            "--record",
            "docs/src/features/example/index.md",
            "--merge-sha",
            merge_sha,
            "--finalizer-sha",
            finalizer_sha,
            "--path",
            path,
            "--delivery-id",
            "delivery-1",
            "--root-id",
            "root-1",
        ],
        cwd=repository,
        check=check,
    )


def test_feature_delivery_finalizer_closes_only_after_verified_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, merge_sha = prepare_delivery_repository(tmp_path)
    finalizer_sha = run(["git", "rev-parse", "HEAD"], cwd=repository).stdout.strip()
    log = tmp_path / "bd.log"
    bin_dir = install_fake_bd(tmp_path, log=log)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = finalize(repository, merge_sha, finalizer_sha)

    assert result.returncode == 0, result.stderr
    assert "delivery-1" in log.read_text(encoding="utf-8")
    assert "root-1" in log.read_text(encoding="utf-8")


def test_feature_delivery_finalizer_rejects_merge_as_finalizer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository, merge_sha = prepare_delivery_repository(tmp_path)
    log = tmp_path / "bd.log"
    bin_dir = install_fake_bd(tmp_path, log=log)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = finalize(repository, merge_sha, merge_sha)

    assert result.returncode == 1
    assert "after the confirmed merge" in result.stderr
    assert not log.exists()


def test_feature_delivery_finalizer_does_not_close_on_dirty_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, merge_sha = prepare_delivery_repository(tmp_path)
    finalizer_sha = run(["git", "rev-parse", "HEAD"], cwd=repository).stdout.strip()
    (repository / "unrelated.txt").write_text("do not absorb\n", encoding="utf-8")
    log = tmp_path / "bd.log"
    bin_dir = install_fake_bd(tmp_path, log=log)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = finalize(repository, merge_sha, finalizer_sha)

    assert result.returncode == 1
    assert "clean worktree" in result.stderr
    assert not log.exists()
