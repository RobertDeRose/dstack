from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import SETUP_SCRIPT, run_command, run_json


def install(repo: Path, *extra: str):
    return run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(repo), "--init", *extra],
        cwd=repo,
    )


def test_setup_installs_sources_without_live_proto_pollution(target_repo: Path) -> None:
    result = install(target_repo)
    assert result["status"] == "ok"
    assert result["preflight"] == "isolated-formula-pour"
    assert (target_repo / ".beads/formulas/dstack-feature.formula.toml").is_file()
    state = json.loads(Path(__import__("os").environ["DSTACK_FAKE_BD_STATE"]).read_text())
    assert not state["issues"]


def test_setup_is_idempotent_and_doctor_is_setup_only(target_repo: Path) -> None:
    install(target_repo)
    second = install(target_repo)
    assert set(second["formulas"].values()) == {"unchanged"}
    doctor = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "doctor", "--root", str(target_repo)],
        cwd=target_repo,
    )
    assert doctor["status"] == "ok"


def test_setup_refuses_formula_drift_without_force(target_repo: Path) -> None:
    install(target_repo)
    path = target_repo / ".beads/formulas/dstack-feature.formula.toml"
    path.write_text(path.read_text() + "\n# drift\n")
    failed = run_command(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"],
        cwd=target_repo,
        check=False,
    )
    assert failed.returncode == 1
    assert "--force" in failed.stderr
    assert install(target_repo, "--force")["formulas"]["dstack-feature"] == "updated"


def test_legacy_repair_untracks_interaction_log_without_deleting_it(target_repo: Path) -> None:
    install(target_repo)
    runtime = target_repo / ".beads/interactions.jsonl"
    runtime.write_text('{"event":"test"}\n')
    subprocess.run(["git", "add", str(runtime.relative_to(target_repo))], cwd=target_repo, check=True)
    subprocess.run(["git", "commit", "-m", "track legacy log"], cwd=target_repo, check=True, capture_output=True)
    preview = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "repair-legacy", "--root", str(target_repo)],
        cwd=target_repo,
        check=False,
    )
    assert preview.returncode == 2
    repaired = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "repair-legacy", "--root", str(target_repo), "--force"],
        cwd=target_repo,
    )
    assert repaired["interaction_log_untracked"] is True
    assert runtime.is_file()
    assert ".beads/interactions.jsonl" in (target_repo / ".gitignore").read_text()
    assert subprocess.run(["git", "ls-files", "--error-unmatch", ".beads/interactions.jsonl"], cwd=target_repo).returncode != 0


def test_legacy_repair_normalizes_root_and_child_metadata(target_repo: Path) -> None:
    install(target_repo)
    poured = run_json(
        [
            "bd",
            "mol",
            "pour",
            "dstack-feature",
            "--var",
            "feature_title=Legacy Current",
            "--var",
            "feature_slug=legacy-current",
            "--var",
            "base_branch=dev",
            "--var",
            "design_path=docs/src/features/legacy-current/design.md",
            "--json",
        ],
        cwd=target_repo,
    )
    root_id = poured["root_id"]
    run_json(
        [
            "bd",
            "update",
            root_id,
            "--title",
            "Feature: Legacy Current",
            "--add-label",
            "workflow:feature",
            "--add-label",
            "feature:legacy-current",
            "--set-metadata",
            "base_branch=dev",
            "--set-metadata",
            "design_path=docs/src/features/legacy-current/design.md",
            "--set-metadata",
            "feature_slug=legacy-current",
            "--json",
        ],
        cwd=target_repo,
    )
    children = run_json(
        ["bd", "list", "--parent", root_id, "--all", "--limit", "0", "--json"],
        cwd=target_repo,
    )
    first_child = children[0]
    run_json(
        [
            "bd",
            "update",
            first_child["id"],
            "--set-metadata",
            "base_branch={{base_branch}}",
            "--set-metadata",
            "design_path={{design_path}}",
            "--add-label",
            "feature:{{feature_slug}}",
            "--json",
        ],
        cwd=target_repo,
    )

    repaired = run_json(
        [
            "python3",
            "-S",
            str(SETUP_SCRIPT),
            "repair-legacy",
            "--root",
            str(target_repo),
            "--force",
        ],
        cwd=target_repo,
    )
    assert root_id in repaired["molecule_items_normalized"]
    root = run_json(["bd", "show", root_id, "--json"], cwd=target_repo)[0]
    assert root["metadata"]["dstack.base_branch"] == "dev"
    assert root["metadata"]["dstack.design_path"].endswith("design.md")
    assert "base_branch" not in root["metadata"]
    assert "feature_slug" not in root["metadata"]
    child = run_json(["bd", "show", first_child["id"], "--json"], cwd=target_repo)[0]
    assert "base_branch" not in child["metadata"]
    assert "design_path" not in child["metadata"]
    assert "feature:{{feature_slug}}" not in child["labels"]
