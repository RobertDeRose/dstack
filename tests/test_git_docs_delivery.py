from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import DSTACKCTL, ctl, run_command
from test_feature_controller import initialize


def test_commit_helper_rejects_runtime_beads_and_adds_one_footer(installed_repo: Path) -> None:
    created = initialize(installed_repo)
    worktree = Path(created["worktree"])
    runtime = worktree / ".beads/interactions.jsonl"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("x\n")
    subprocess.run(["git", "add", "-f", ".beads/interactions.jsonl"], cwd=worktree, check=True)
    failed = run_command(
        ["python3", "-S", str(DSTACKCTL), "--root", str(worktree), "git", "commit", "--bead", "bd-1", "--subject", "test: bad"],
        cwd=worktree,
        check=False,
    )
    assert failed.returncode == 1
    assert "runtime state" in failed.stderr


def test_docs_guard_allows_durable_docs_but_rejects_transient_and_status_only(installed_repo: Path) -> None:
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True).strip()
    docs = installed_repo / "docs/planned-features.md"
    docs.parent.mkdir(parents=True)
    docs.write_text("# Features\n\n- Status: planned\n- Summary: durable intent\n")
    subprocess.run(["git", "add", "docs/planned-features.md"], cwd=installed_repo, check=True)
    subprocess.run(["git", "commit", "-m", "docs: add plan"], cwd=installed_repo, check=True, capture_output=True)
    assert ctl(installed_repo, "docs", "check", "--base", base, "--head", "HEAD")["status"] == "ok"

    prior = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True).strip()
    docs.write_text("# Features\n\n- Status: in-progress\n- Summary: durable intent\n")
    subprocess.run(["git", "add", "docs/planned-features.md"], cwd=installed_repo, check=True)
    subprocess.run(["git", "commit", "-m", "docs: bad status"], cwd=installed_repo, check=True, capture_output=True)
    failed = run_command(
        ["python3", "-S", str(DSTACKCTL), "--root", str(installed_repo), "docs", "check", "--base", prior, "--head", "HEAD"],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 4
    assert "violations" in failed.stdout


def test_docs_guard_allows_domain_vocabulary_but_rejects_workflow_records(
    installed_repo: Path,
) -> None:
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True
    ).strip()
    docs = installed_repo / "docs/domain.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(
        "# Request lifecycle\n\n"
        "A request can be blocked by policy, and review may complete later.\n"
    )
    subprocess.run(["git", "add", str(docs.relative_to(installed_repo))], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: describe domain lifecycle"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    assert ctl(installed_repo, "docs", "check", "--base", base, "--head", "HEAD")["status"] == "ok"

    prior = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True
    ).strip()
    docs.write_text(
        "# Request lifecycle\n\n"
        "A request can be blocked by policy, and review may complete later.\n"
        "- Worktree: /tmp/request\n"
    )
    subprocess.run(["git", "add", str(docs.relative_to(installed_repo))], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: add workflow record"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "docs",
            "check",
            "--base",
            prior,
            "--head",
            "HEAD",
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 4
    assert "Worktree" in failed.stdout


def prepare_deliverable(repo: Path):
    created = initialize(repo, "Delivery Feature")
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("approved\n")
    ctl(repo, "feature", "claim-spec", root_id)
    ctl(repo, "feature", "approve-spec", root_id)
    task = ctl(repo, "feature", "add-task", root_id, "--title", "Implement", "--acceptance", "done")["task"]
    ctl(repo, "feature", "claim-next", root_id)
    (worktree / "delivery.txt").write_text("done\n")
    subprocess.run(["git", "add", "delivery.txt"], cwd=worktree, check=True)
    ctl(worktree, "git", "commit", "--bead", task["id"], "--subject", "feat: delivery")
    ctl(repo, "feature", "finish-task", root_id, "--task", task["id"])
    ctl(repo, "feature", "finish-workstream", root_id)
    ctl(repo, "feature", "claim-closeout", root_id)
    ctl(repo, "feature", "finish-closeout", root_id)
    return created


def test_fast_forward_delivery_closes_beads_without_post_merge_git_change(installed_repo: Path) -> None:
    created = prepare_deliverable(installed_repo)
    before = subprocess.check_output(["git", "status", "--short", "--untracked-files=no"], cwd=installed_repo, text=True)
    result = ctl(installed_repo, "delivery", "merge", created["root"]["id"])
    assert result["status"] == "ok"
    assert subprocess.check_output(["git", "status", "--short", "--untracked-files=no"], cwd=installed_repo, text=True) == before
    assert ctl(installed_repo, "feature", "inspect", created["root"]["id"])["root"]["status"] == "closed"


def test_pr_preflight_rejects_stale_remote_base(installed_repo: Path, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=installed_repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", "dev"], cwd=installed_repo, check=True, capture_output=True)
    created = prepare_deliverable(installed_repo)
    # Advance local target without pushing it.
    (installed_repo / "local-only.txt").write_text("local\n")
    subprocess.run(["git", "add", "local-only.txt"], cwd=installed_repo, check=True)
    subprocess.run(["git", "commit", "-m", "chore: local target advance"], cwd=installed_repo, check=True, capture_output=True)
    failed = run_command(
        ["python3", "-S", str(DSTACKCTL), "--root", str(installed_repo), "delivery", "pr-preflight", created["root"]["id"]],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "local target and origin target differ" in failed.stderr


def test_docs_guard_allows_implemented_status_as_part_of_real_feature_delta(installed_repo: Path) -> None:
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True).strip()
    docs = installed_repo / "docs/planned-features.md"
    source = installed_repo / "src/feature.py"
    docs.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    docs.write_text("# Features\n\n- Status: implemented\n- Summary: shipped behavior\n")
    source.write_text("ENABLED = True\n")
    subprocess.run(["git", "add", "docs/planned-features.md", "src/feature.py"], cwd=installed_repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add behavior"], cwd=installed_repo, check=True, capture_output=True)
    assert ctl(installed_repo, "docs", "check", "--base", base, "--head", "HEAD")["status"] == "ok"


def test_docs_guard_rejects_completed_as_legacy_workflow_vocabulary(
    installed_repo: Path,
) -> None:
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True
    ).strip()
    docs = installed_repo / "docs/planned-features.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text("# Features\n\n- Status: completed\n")
    subprocess.run(["git", "add", str(docs.relative_to(installed_repo))], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: legacy completion vocabulary"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "docs",
            "check",
            "--base",
            base,
            "--head",
            "HEAD",
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 4
    assert "completed" in failed.stdout


def test_evidence_audit_allows_multiple_reachable_commits_for_one_bead(
    installed_repo: Path,
) -> None:
    created = initialize(installed_repo, "Multi Commit Feature")
    root_id = created["root"]["id"]
    worktree = Path(created["worktree"])
    design = worktree / created["design_path"]
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("approved\n")
    ctl(installed_repo, "feature", "claim-spec", root_id)
    ctl(installed_repo, "feature", "approve-spec", root_id)
    task = ctl(
        installed_repo,
        "feature",
        "add-task",
        root_id,
        "--title",
        "Implement in two bounded commits",
        "--acceptance",
        "done",
    )["task"]
    ctl(installed_repo, "feature", "claim-next", root_id)
    for number in (1, 2):
        path = worktree / f"part-{number}.txt"
        path.write_text(f"part {number}\n")
        subprocess.run(["git", "add", path.name], cwd=worktree, check=True)
        ctl(
            worktree,
            "git",
            "commit",
            "--bead",
            task["id"],
            "--subject",
            f"feat: add part {number}",
        )
    ctl(installed_repo, "feature", "finish-task", root_id, "--task", task["id"])
    audit = ctl(installed_repo, "evidence", "audit-feature", root_id)
    assert audit["status"] == "ok"
    assert len(audit["multiple_commits"][task["id"]]) == 2


def test_docs_guard_allows_command_documentation_but_rejects_next_command_state(
    installed_repo: Path,
) -> None:
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True
    ).strip()
    docs = installed_repo / "docs/workflow.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text("# Workflow\n\nUse `/implement-feature` to execute ready work.\n")
    subprocess.run(["git", "add", str(docs.relative_to(installed_repo))], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: explain command"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    assert ctl(installed_repo, "docs", "check", "--base", base, "--head", "HEAD")["status"] == "ok"

    prior = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=installed_repo, text=True
    ).strip()
    docs.write_text(
        "# Workflow\n\nUse `/implement-feature` to execute ready work.\n\n"
        "- Next command: /implement-feature current-feature\n"
    )
    subprocess.run(["git", "add", str(docs.relative_to(installed_repo))], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: add transient next command"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "docs",
            "check",
            "--base",
            prior,
            "--head",
            "HEAD",
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 4
    assert "Next command" in failed.stdout


def test_pr_preflight_rejects_docs_only_title_for_code_feature(
    installed_repo: Path,
    tmp_path: Path,
) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "dev"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    created = prepare_deliverable(installed_repo)
    body = tmp_path / "body.md"
    body.write_text("- add the complete feature\n\nValidation: tests\n")
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "delivery",
            "pr-preflight",
            created["root"]["id"],
            "--title",
            "docs: finalize delivery record",
            "--body-file",
            str(body),
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "docs-only" in failed.stderr

    accepted = ctl(
        installed_repo,
        "delivery",
        "pr-preflight",
        created["root"]["id"],
        "--title",
        "feat: add delivery feature",
        "--body-file",
        str(body),
    )
    assert accepted["pr_copy"]["title"] == "feat: add delivery feature"
    assert "delivery.txt" in accepted["pr_copy"]["non_documentation_paths"]


def test_delivery_allows_tracked_beads_repository_configuration(installed_repo: Path) -> None:
    config_files = {
        ".beads/.gitignore": "embeddeddolt/\ninteractions.jsonl\n",
        ".beads/README.md": "# Beads\n",
        ".beads/config.yaml": "# project configuration\n",
        ".beads/metadata.json": "{}\n",
    }
    for name, content in config_files.items():
        path = installed_repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "add", *config_files], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: track Beads repository configuration"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    created = prepare_deliverable(installed_repo)
    inspected = ctl(installed_repo, "delivery", "inspect", created["root"]["id"])
    assert inspected["tracked_runtime_beads"] == []
    assert ctl(installed_repo, "delivery", "merge", created["root"]["id"])["status"] == "ok"


def test_delivery_rejects_true_tracked_beads_runtime(installed_repo: Path) -> None:
    runtime = installed_repo / ".beads/sync-state.json"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("{}\n")
    subprocess.run(["git", "add", "-f", str(runtime.relative_to(installed_repo))], cwd=installed_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "test: track runtime state"],
        cwd=installed_repo,
        check=True,
        capture_output=True,
    )
    created = prepare_deliverable(installed_repo)
    failed = run_command(
        [
            "python3",
            "-S",
            str(DSTACKCTL),
            "--root",
            str(installed_repo),
            "delivery",
            "merge",
            created["root"]["id"],
        ],
        cwd=installed_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert ".beads/sync-state.json" in failed.stderr
