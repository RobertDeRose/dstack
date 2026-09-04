from __future__ import annotations

from io import StringIO

import pytest

from dstack import output as subject


class FakeStream(StringIO):
    def __init__(self, *, tty: bool):
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


@pytest.mark.parametrize("tty", [True, False])
def test_emit_defaults_to_compact_json_in_every_terminal(monkeypatch: pytest.MonkeyPatch, tty: bool) -> None:
    stream = FakeStream(tty=tty)
    monkeypatch.delenv("DSTACK_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(subject.sys, "stdout", stream)

    subject.emit({"status": "ok", "items": [1]})

    assert stream.getvalue() == '{"items":[1],"status":"ok"}\n'


def test_explicit_pretty_output_uses_standard_json_without_terminal_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = FakeStream(tty=True)
    monkeypatch.setenv("DSTACK_OUTPUT_FORMAT", "pretty")
    monkeypatch.setattr(subject.sys, "stdout", stream)

    subject.emit({"status": "ok", "items": [1]})

    assert stream.getvalue() == '{\n  "items": [\n    1\n  ],\n  "status": "ok"\n}\n'
    assert "\x1b[" not in stream.getvalue()


def test_compact_override_remains_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream(tty=True)
    monkeypatch.setenv("DSTACK_OUTPUT_FORMAT", "compact")
    monkeypatch.setattr(subject.sys, "stdout", stream)

    subject.emit({"status": "ok"})

    assert stream.getvalue() == '{"status":"ok"}\n'


def test_fail_defaults_to_compact_json_on_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream(tty=True)
    monkeypatch.delenv("DSTACK_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(subject.sys, "stderr", stream)

    assert subject.fail("bad") == 2
    assert stream.getvalue() == '{"error":"bad","status":"error"}\n'
