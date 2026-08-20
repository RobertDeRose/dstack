# Testing dStack

## Fast suite

The default suite exercises controller decisions in-process with immutable
Beads protocol snapshots. It uses disposable Git repositories where Git is the
authority and never invokes a real `bd` binary.

```bash
uv run pytest -q -rs
```

This suite must complete quickly, with zero skipped tests. The scripted client
is a protocol stub only: it matches ordered calls and returns declared
snapshots; it does not calculate readiness, dependencies, ownership, gates, or
lifecycle transitions.

## Real-Beads acceptance

Acceptance uses exactly two real-boundary scenarios in `tests/acceptance`:

```bash
uv run pytest -q tests/acceptance/test_bd_contract.py

uv run pytest -q tests/acceptance/test_feature_smoke.py
```

An unavailable or invalid `bd` is an acceptance failure, never a skip. The
contract scenario initializes Beads directly and verifies the supported JSON
envelope, both formula structures and pours, native gates/readiness/claims,
child fan-in, supersession, and worktree primitives. The smoke scenario alone
runs full dStack setup, then one minimal shipped feature through approval, one
Git-backed task, closeout, and fast-forward delivery.

GitHub Actions runs the fast suite and each real-Beads scenario as separate
jobs. The acceptance matrix installs the locked Beads version through mise, and
the acceptance preflight fails immediately unless `bd` is on `PATH`.

## Test ownership

- Beads owns lifecycle behavior; acceptance tests verify the supported binary.
- dStack owns selector, validation, refusal, Git evidence, documentation, and
  delivery policy; fast tests verify those decisions without reimplementing
  Beads.
- Git owns repository state; fast tests use real temporary Git repositories for
  Git behavior.

No coverage threshold or fixed test count is used. Every test asserts an
observable result, invariant, refusal, or failure boundary.
