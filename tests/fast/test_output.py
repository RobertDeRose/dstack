from __future__ import annotations

import re
from io import StringIO

import pytest

from dstack import output as subject


def strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


class FakeStream(StringIO):
    def __init__(self, *, tty: bool):
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def test_emit_pretty_prints_for_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream(tty=True)
    monkeypatch.delenv("DSTACK_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(subject.sys, "stdout", stream)

    subject.emit({"status": "ok", "items": [1]})

    assert "\x1b[" in stream.getvalue()
    assert strip_ansi(stream.getvalue()) == '{\n  "items": [\n    1\n  ],\n  "status": "ok"\n}\n'


def test_emit_compact_prints_when_not_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream(tty=False)
    monkeypatch.delenv("DSTACK_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(subject.sys, "stdout", stream)

    subject.emit({"status": "ok", "items": [1]})

    assert stream.getvalue() == '{"items":[1],"status":"ok"}\n'


@pytest.mark.parametrize(
    ("tty", "override", "pretty"),
    [(True, "compact", False), (False, "pretty", True)],
)
def test_output_format_override_wins_over_terminal_detection(
    monkeypatch: pytest.MonkeyPatch, tty: bool, override: str, pretty: bool
) -> None:
    stream = FakeStream(tty=tty)
    monkeypatch.setenv("DSTACK_OUTPUT_FORMAT", override)
    monkeypatch.setattr(subject.sys, "stdout", stream)

    subject.emit({"status": "ok"})

    if pretty:
        assert stream.getvalue() == '{\n  "status": "ok"\n}\n'
    else:
        assert stream.getvalue() == '{"status":"ok"}\n'


def test_fail_uses_stderr_terminal_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream(tty=True)
    monkeypatch.delenv("DSTACK_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(subject.sys, "stderr", stream)

    assert subject.fail("bad") == 2
    assert "\x1b[" in stream.getvalue()
    assert strip_ansi(stream.getvalue()) == '{\n  "error": "bad",\n  "status": "error"\n}\n'
