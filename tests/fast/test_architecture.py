from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dstack import beads
from dstack.core import CommandResult, command_env


LOWER_LEVEL_MODULES = (
    "beads.py",
    "docs.py",
    "formula.py",
    "git_ops.py",
    "git_state.py",
    "policy.py",
    "task_validation.py",
    "workflow.py",
)


def test_lower_layers_do_not_import_command_handlers() -> None:
    package = Path(__file__).parents[2] / "dstack"
    offenders: list[str] = []
    for name in LOWER_LEVEL_MODULES:
        path = package / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in {"commands", "dstack.commands"}:
                offenders.append(name)
            elif isinstance(node, ast.Import) and any(alias.name == "dstack.commands" for alias in node.names):
                offenders.append(name)
    assert offenders == []


def test_read_only_validation_does_not_import_git_mutation_layer() -> None:
    package = Path(__file__).parents[2] / "dstack"
    offenders: list[str] = []
    for name in ("feature_check.py", "task_validation.py"):
        path = package / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in {"git_ops", "dstack.git_ops"}:
                offenders.append(name)
            elif isinstance(node, ast.Import) and any(alias.name == "dstack.git_ops" for alias in node.names):
                offenders.append(name)
    assert offenders == []


def test_generic_command_environment_has_no_beads_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BD_JSON_ENVELOPE", raising=False)
    assert "BD_JSON_ENVELOPE" not in command_env()


def test_beads_adapter_adds_json_envelope_only_at_native_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_run(command: list[str], **kwargs: object) -> CommandResult:
        captured.update(kwargs["env"])  # type: ignore[arg-type]
        return CommandResult(0, "", "")

    monkeypatch.setattr(beads, "run", fake_run)
    beads.run_beads(["bd", "--version"], cwd=tmp_path)
    assert captured == {"BD_JSON_ENVELOPE": "1"}


def test_beads_list_reads_complete_lifecycle_state(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = beads.BeadsClient(git_repo)
    observed: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CommandResult:
        observed.append(command)
        return CommandResult(0, '{"schema_version":1,"data":[]}', "")

    monkeypatch.setattr(client, "_run", fake_run)
    assert client.list_issues(parent="implementation", labels=["dstack:work:implementation"]) == []
    assert observed == [
        [
            "bd",
            "list",
            "--limit",
            "0",
            "--json",
            "--all",
            "--parent",
            "implementation",
            "--label",
            "dstack:work:implementation",
        ]
    ]
