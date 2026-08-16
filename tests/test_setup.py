from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import SETUP_SCRIPT, run_json


def fake_state() -> dict:
    return json.loads(Path(os.environ["DSTACK_FAKE_BD_STATE"]).read_text())


def test_setup_installs_and_validates_formula_sources_without_persisted_protos(
    target_repo: Path,
) -> None:
    result = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"],
        cwd=target_repo,
    )
    assert result["status"] == "ok"
    assert result["beads_version"] == "bd version 1.2.2"
    assert result["preflight"] == "isolated-formula-pour"
    assert result["formulas"] == {
        "dstack-feature": "installed",
        "dstack-project-alignment": "installed",
    }
    assert result["legacy_persisted_protos_removed"] == []
    for name in result["validated"]:
        assert (target_repo / ".beads" / "formulas" / f"{name}.formula.toml").is_file()

    state = fake_state()
    assert state["protos"] == {}
    assert not any(item.get("is_template") for item in state["issues"].values())

    doctor = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "doctor", "--root", str(target_repo)],
        cwd=target_repo,
    )
    assert doctor["status"] == "ok"
    assert doctor["persisted_protos"] == "absent"
    assert set(doctor["formulas"]) == {"dstack-feature", "dstack-project-alignment"}


def test_setup_is_idempotent(target_repo: Path) -> None:
    command = ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"]
    run_json(command, cwd=target_repo)
    second = run_json(command, cwd=target_repo)
    assert set(second["formulas"].values()) == {"unchanged"}
    assert second["legacy_persisted_protos_removed"] == []


def test_setup_refuses_formula_conflict_without_force(target_repo: Path) -> None:
    command = ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"]
    run_json(command, cwd=target_repo)
    installed = target_repo / ".beads" / "formulas" / "dstack-feature.formula.toml"
    installed.write_text(installed.read_text() + "\n# local change\n")

    failed = run_json(command, cwd=target_repo, check=False)
    assert failed.returncode == 1
    error = json.loads(failed.stderr)
    assert "formula differs" in error["error"]

    forced = run_json([*command, "--force"], cwd=target_repo)
    assert forced["formulas"]["dstack-feature"] == "updated"


def test_force_setup_recovers_from_previously_copied_invalid_formula(
    target_repo: Path,
) -> None:
    formulas = target_repo / ".beads" / "formulas"
    formulas.mkdir(parents=True)
    (formulas / "dstack-feature.formula.toml").write_text(
        """
formula = "dstack-feature"
type = "workflow"
phase = "liquid"
pour = true

[[steps]]
id = "implementation"
title = "Implementation"
type = "epic"

[[steps]]
id = "closeout"
title = "Closeout"
type = "task"
needs = ["implementation"]
""".lstrip()
    )

    result = run_json(
        [
            "python3",
            "-S",
            str(SETUP_SCRIPT),
            "install",
            "--root",
            str(target_repo),
            "--force",
        ],
        cwd=target_repo,
    )

    assert result["status"] == "ok"
    assert result["formulas"]["dstack-feature"] == "updated"


def test_force_setup_recovers_from_formula_gate_on_epic(target_repo: Path) -> None:
    formulas = target_repo / ".beads" / "formulas"
    formulas.mkdir(parents=True)
    (formulas / "dstack-feature.formula.toml").write_text(
        """
formula = "dstack-feature"
type = "workflow"
phase = "liquid"
pour = true

[[steps]]
id = "implementation"
title = "Implementation"
type = "epic"

[steps.gate]
type = "human"
id = "approve-implementation"
""".lstrip()
    )

    result = run_json(
        [
            "python3",
            "-S",
            str(SETUP_SCRIPT),
            "install",
            "--root",
            str(target_repo),
            "--force",
        ],
        cwd=target_repo,
    )

    assert result["status"] == "ok"
    assert result["formulas"]["dstack-feature"] == "updated"


def test_force_setup_removes_legacy_persisted_proto_graphs(target_repo: Path) -> None:
    install = [
        "python3",
        "-S",
        str(SETUP_SCRIPT),
        "install",
        "--root",
        str(target_repo),
        "--init",
    ]
    run_json(install, cwd=target_repo)

    for formula_name in ("dstack-feature", "dstack-project-alignment"):
        run_json(
            ["bd", "cook", formula_name, "--persist", "--force", "--json"],
            cwd=target_repo,
        )

    ready = run_json(["bd", "ready", "--json"], cwd=target_repo)
    assert any(item.get("is_template") for item in ready)
    gates = run_json(["bd", "gate", "list", "--json"], cwd=target_repo)
    assert any(item["id"].startswith("dstack-feature.gate-") for item in gates)

    doctor_failed = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "doctor", "--root", str(target_repo)],
        cwd=target_repo,
        check=False,
    )
    assert doctor_failed.returncode == 1
    assert "legacy persisted dstack protos remain" in json.loads(doctor_failed.stderr)["error"]

    install_failed = run_json(install, cwd=target_repo, check=False)
    assert install_failed.returncode == 1
    assert "rerun with --force" in json.loads(install_failed.stderr)["error"]

    repaired = run_json([*install, "--force"], cwd=target_repo)
    assert repaired["legacy_persisted_protos_removed"] == [
        "dstack-feature",
        "dstack-project-alignment",
    ]

    state = fake_state()
    assert state["protos"] == {}
    assert not any(
        item_id == "dstack-feature"
        or item_id.startswith("dstack-feature.")
        or item_id == "dstack-project-alignment"
        or item_id.startswith("dstack-project-alignment.")
        for item_id in state["issues"]
    )
    assert not any(item.get("is_template") for item in state["issues"].values())


def test_doctor_rejects_cookable_task_workstream_workaround(target_repo: Path) -> None:
    run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"],
        cwd=target_repo,
    )
    installed = target_repo / ".beads" / "formulas" / "dstack-feature.formula.toml"
    text = installed.read_text()
    marker = 'id = "implementation"\ntitle = "Implementation workstream: {{feature_title}}"\ntype = "epic"'
    assert marker in text
    installed.write_text(text.replace(marker, marker.replace('type = "epic"', 'type = "task"')))

    failed = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "doctor", "--root", str(target_repo)],
        cwd=target_repo,
        check=False,
    )
    assert failed.returncode == 1
    error = json.loads(failed.stderr)
    assert "installed formula differs from dstack package" in error["error"]


def test_doctor_rejects_formula_source_drift(target_repo: Path) -> None:
    run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "install", "--root", str(target_repo), "--init"],
        cwd=target_repo,
    )
    installed = target_repo / ".beads" / "formulas" / "dstack-feature.formula.toml"
    installed.write_text(installed.read_text() + "\n# local drift\n")

    failed = run_json(
        ["python3", "-S", str(SETUP_SCRIPT), "doctor", "--root", str(target_repo)],
        cwd=target_repo,
        check=False,
    )
    assert failed.returncode == 1
    error = json.loads(failed.stderr)
    assert "installed formula differs from dstack package" in error["error"]


def test_formula_contract_rejects_task_workstream_workaround() -> None:
    import runpy
    import tomllib

    namespace = runpy.run_path(str(SETUP_SCRIPT))
    validate = namespace["validate_dstack_formula_contract"]
    setup_error = namespace["SetupError"]
    formula_path = SETUP_SCRIPT.parents[3] / "formulas" / "dstack-feature.formula.toml"
    formula = tomllib.loads(formula_path.read_text())
    next(step for step in formula["steps"] if step["id"] == "implementation")["type"] = "task"

    with __import__("pytest").raises(
        setup_error,
        match="implementation must remain type=epic",
    ):
        validate("dstack-feature", formula)


def test_force_setup_refuses_same_named_non_template_issue(target_repo: Path) -> None:
    state = fake_state()
    state["issues"]["dstack-feature"] = {
        "id": "dstack-feature",
        "title": "Ordinary project issue",
        "type": "epic",
        "issue_type": "epic",
        "status": "open",
        "parent_id": None,
        "labels": [],
        "metadata": {},
        "dependencies": [],
        "gate_ids": [],
        "is_template": False,
    }
    Path(os.environ["DSTACK_FAKE_BD_STATE"]).write_text(json.dumps(state))

    failed = run_json(
        [
            "python3",
            "-S",
            str(SETUP_SCRIPT),
            "install",
            "--root",
            str(target_repo),
            "--init",
            "--force",
        ],
        cwd=target_repo,
        check=False,
    )

    assert failed.returncode == 1
    assert "not a dstack template" in json.loads(failed.stderr)["error"]
    assert "dstack-feature" in fake_state()["issues"]
