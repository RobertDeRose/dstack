from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import core as dstacklib


def client(tmp_path: Path) -> dstacklib.BeadsClient:
    value = dstacklib.BeadsClient.__new__(dstacklib.BeadsClient)
    value.root = tmp_path
    value._read_cache = {}
    return value


def test_json_envelope_and_create_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        return dstacklib.CommandResult(
            0,
            json.dumps({"schema_version": 1, "data": {"id": "task-1"}}),
            "",
        )

    monkeypatch.setattr(dstacklib, "run", fake_run)
    result = client(tmp_path).create(
        "Task",
        parent="epic-1",
        labels=["dstack:work:implementation"],
        dependencies=["approval-1"],
        acceptance="observable result",
    )
    assert result == {"id": "task-1"}
    assert calls == [
        (
            "bd",
            "create",
            "Task",
            "--type",
            "task",
            "--priority",
            "2",
            "--json",
            "--parent",
            "epic-1",
            "--no-inherit-labels",
            "--labels",
            "dstack:work:implementation",
            "--deps",
            "approval-1",
            "--acceptance",
            "observable result",
        )
    ]


def test_show_cache_and_write_invalidation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    issue = {"id": "task-1", "status": "open"}

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        if command[:2] == ["bd", "show"]:
            return dstacklib.CommandResult(0, json.dumps([issue]), "")
        if command[:2] == ["bd", "update"]:
            return dstacklib.CommandResult(0, json.dumps([issue]), "")
        raise AssertionError(command)

    monkeypatch.setattr(dstacklib, "run", fake_run)
    beads = client(tmp_path)
    beads.show("task-1")
    beads.show("task-1")
    beads.update("task-1", "--claim")
    beads.show("task-1")
    assert calls.count(("bd", "show", "task-1", "--json")) == 2


def test_not_found_is_optional_but_other_errors_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(command, *, cwd, check=True, **kwargs):
        return dstacklib.CommandResult(1, "", "issue not found")

    monkeypatch.setattr(dstacklib, "run", missing)
    assert client(tmp_path).show_optional("missing") is None

    def broken(command, *, cwd, check=True, **kwargs):
        return dstacklib.CommandResult(1, "", "database unavailable")

    monkeypatch.setattr(dstacklib, "run", broken)
    with pytest.raises(dstacklib.DstackError, match="database unavailable"):
        client(tmp_path).show_optional("broken")


def test_invalid_json_has_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dstacklib,
        "run",
        lambda *args, **kwargs: dstacklib.CommandResult(0, "not-json", ""),
    )
    with pytest.raises(dstacklib.DstackError, match="bd list .*returned invalid JSON"):
        client(tmp_path).list()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "unknown object shape"),
        ({"items": {}}, "must be an array"),
        ({"items": [], "data": []}, "unknown object shape"),
        ([{"title": "missing id"}], "has no issue ID"),
        (["not an issue"], "is not an object"),
    ],
)
def test_issue_payload_parser_rejects_malformed_native_shapes(payload: object, message: str) -> None:
    with pytest.raises(dstacklib.DstackError, match=message):
        dstacklib.as_items(payload, context="test payload")


def test_issue_payload_parser_accepts_a_valid_empty_result() -> None:
    assert dstacklib.as_items([], context="test payload") == []


def test_json_envelope_null_normalizes_to_empty_collection() -> None:
    payload = dstacklib.parse_json(
        json.dumps({"schema_version": 1, "data": None}),
        context="bd gate list",
    )
    assert payload == []


def test_gate_list_accepts_empty_null_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        return dstacklib.CommandResult(
            0,
            json.dumps({"schema_version": 1, "data": None}),
            "",
        )

    monkeypatch.setattr(dstacklib, "run", fake_run)
    assert client(tmp_path).gates(all_statuses=True) == []
    assert calls == [("bd", "gate", "list", "--limit", "0", "--json", "--all")]


def test_comment_file_is_closed_before_native_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False)
    path = Path(handle.name)
    monkeypatch.setattr(dstacklib, "write_temp_text", lambda text: handle)
    beads = client(tmp_path)

    def run_comment(command: list[str]) -> dstacklib.CommandResult:
        assert command == ["bd", "comments", "add", "task-1", "-f", str(path)]
        assert handle.closed
        return dstacklib.CommandResult(0, "", "")

    beads._run = run_comment  # type: ignore[method-assign]
    beads.add_comment("task-1", "evidence")
    assert not path.exists()


def test_ready_claim_delegates_to_native_ready_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        return dstacklib.CommandResult(0, json.dumps([{"id": "task-1"}]), "")

    monkeypatch.setattr(dstacklib, "run", fake_run)
    assert client(tmp_path).ready_children("implementation-1", label="dstack:work:implementation", claim=True) == [
        {"id": "task-1"}
    ]
    assert calls == [
        (
            "bd",
            "ready",
            "--parent",
            "implementation-1",
            "--exclude-type",
            "epic,molecule,gate",
            "--limit",
            "1",
            "--json",
            "--label",
            "dstack:work:implementation",
            "--claim",
        )
    ]


def test_pour_builds_declared_variables_without_persisting_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        return dstacklib.CommandResult(0, json.dumps({"root_id": "feature-1"}), "")

    monkeypatch.setattr(dstacklib, "run", fake_run)
    result = client(tmp_path).pour("dstack-feature", {"feature_title": "Feature", "feature_slug": "feature"})
    assert result == {"root_id": "feature-1"}
    assert calls == [
        (
            "bd",
            "mol",
            "pour",
            "dstack-feature",
            "--var",
            "feature_title=Feature",
            "--var",
            "feature_slug=feature",
            "--json",
        )
    ]


def test_gate_resolution_treats_human_output_as_mutation_then_reads_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    states = iter(
        [
            dstacklib.CommandResult(0, json.dumps([{"id": "gate-1", "status": "open"}]), ""),
            dstacklib.CommandResult(0, "resolved gate-1\n", ""),
            dstacklib.CommandResult(0, json.dumps([{"id": "gate-1", "status": "closed"}]), ""),
        ]
    )

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        return next(states)

    monkeypatch.setattr(dstacklib, "run", fake_run)
    assert client(tmp_path).resolve_gate("gate-1", "approved")["status"] == "closed"
    assert calls == [
        ("bd", "show", "gate-1", "--json"),
        ("bd", "gate", "resolve", "gate-1", "--reason", "approved"),
        ("bd", "show", "gate-1", "--json"),
    ]


def test_dependency_and_supersession_use_native_mutations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    show_states = iter(
        [
            {"id": "old-1", "status": "open"},
            {
                "id": "old-1",
                "status": "closed",
                "dependencies": [{"depends_on_id": "new-1", "type": "supersedes"}],
            },
        ]
    )

    def fake_run(command, *, cwd, check=True, **kwargs):
        calls.append(tuple(command))
        if command[:2] == ["bd", "show"]:
            return dstacklib.CommandResult(0, json.dumps([next(show_states)]), "")
        return dstacklib.CommandResult(0, "", "")

    monkeypatch.setattr(dstacklib, "run", fake_run)
    beads = client(tmp_path)
    beads.add_dependency("task-1", "blocker-1")
    beads.supersede("old-1", "new-1")
    assert calls == [
        ("bd", "dep", "add", "task-1", "blocker-1", "--type", "blocks"),
        ("bd", "show", "old-1", "--json"),
        ("bd", "supersede", "old-1", "--with", "new-1"),
        ("bd", "show", "old-1", "--json"),
    ]


@pytest.mark.parametrize(
    "version",
    [
        "1.2.1",
        "1.2.3",
        "1.2.2-dev",
        "1.2.2+local",
        "1.2.2",
        "1.2.2 (deadbeef)",
    ],
)
def test_version_check_rejects_untested_beads_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    monkeypatch.setattr(
        dstacklib,
        "run",
        lambda *args, **kwargs: dstacklib.CommandResult(0, f"bd version {version}", ""),
    )

    with pytest.raises(dstacklib.DstackError, match="requires Beads 1.2.2 exactly"):
        client(tmp_path).check_version()


def test_version_check_accepts_supported_beads_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dstacklib,
        "run",
        lambda *args, **kwargs: dstacklib.CommandResult(0, "bd version 1.2.2 (6c124203e)", ""),
    )

    assert client(tmp_path).check_version() == "bd version 1.2.2 (6c124203e)"
