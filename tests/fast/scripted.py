"""Ordered call/response snapshots for fast controller tests.

This helper deliberately contains no Beads lifecycle, readiness, dependency,
or ownership logic.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ExpectedCall:
    name: str
    args: tuple[Any, ...] = ()
    kwargs: tuple[tuple[str, Any], ...] = ()
    result: Any = None


class ScriptedClient:
    def __init__(self, root: Path, *calls: ExpectedCall):
        self.root = root
        self._expected = list(calls)
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._read_cache: dict[tuple[Any, ...], Any] = {}

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((name, args, kwargs))
        if not self._expected:
            raise AssertionError(f"unexpected Beads call: {name}{args!r}{kwargs!r}")
        expected = self._expected.pop(0)
        actual = (name, args, tuple(sorted(kwargs.items())))
        declared = (expected.name, expected.args, expected.kwargs)
        if declared != actual:
            raise AssertionError(
                f"expected {expected.name}{expected.args!r}{dict(expected.kwargs)!r}, got {name}{args!r}{kwargs!r}"
            )
        return deepcopy(expected.result)

    def assert_exhausted(self) -> None:
        if self._expected:
            raise AssertionError(f"unconsumed Beads calls: {self._expected!r}")

    def __getattr__(self, name: str) -> Callable[..., Any]:
        return lambda *args, **kwargs: self._call(name, *args, **kwargs)


def call(name: str, *args: Any, result: Any = None, **kwargs: Any) -> ExpectedCall:
    return ExpectedCall(name, args, tuple(sorted(kwargs.items())), result)
