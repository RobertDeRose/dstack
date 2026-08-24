# Testing dStack

## Setup diagnostics

Setup first emits a stateless plan with an authority-state digest. Apply requires that reviewed digest, recomputes the
plan after a clean-worktree preflight, and refuses changed preconditions. Formula writes use atomic replacement;
failures compensate setup-owned resources where possible and report observed recovery for boundaries that require
inspection.

Doctor reports independent, actionable checks for pinned Beads and mdBook versions, formula bytes and validity,
documentation, interaction-log policy, feature reconciliations, Git worktrees, tracked runtime paths, origin/GitHub
prerequisites, and pending compatibility migration.

## Documentation

The tested mdBook release is pinned through mise. Validate required pages, chapter navigation, local links, orphan
Markdown, and the build with:

```bash
python3 skills/dstack-beads-core/scripts/dstackctl.py docs validate
```

The build uses temporary output and external URLs are not fetched.

## Fast suite

The default suite exercises controller decisions in-process with immutable Beads protocol snapshots. It uses disposable
Git repositories where Git is the authority and never invokes a real `bd` binary.

```bash
uv run pytest -q -rs
```

This suite must complete quickly, with zero skipped tests. The scripted client is a protocol stub only: it matches
ordered calls and returns declared snapshots; it does not calculate readiness, dependencies, ownership, gates, or
lifecycle transitions.

## Real-Beads acceptance

Acceptance uses exactly two real-boundary scenarios in `tests/acceptance`:

```bash
uv run pytest -q tests/acceptance/test_bd_contract.py

uv run pytest -q tests/acceptance/test_feature_smoke.py
```

An unavailable or invalid `bd` is an acceptance failure, never a skip. The contract scenario initializes Beads directly
and verifies the supported JSON envelope, both formula structures and pours, native gates/readiness/claims, child
fan-in, supersession, and worktree primitives. The smoke scenario alone runs full dStack setup, then one minimal shipped
feature through approval, one Git-backed task, closeout, and fast-forward delivery.

GitHub Actions validates the mdBook, then runs the fast suite and each real-Beads scenario as separate jobs on pull
requests, pushes to `main`, a weekly schedule, and manual dispatch. The acceptance matrix installs the exact supported
Beads 1.2.2 release through mise. A different version requires an explicit compatibility change backed by the same
real-boundary scenarios. Acceptance preflight fails immediately unless `bd` is on `PATH`.

## Test ownership

- Beads owns lifecycle behavior; acceptance tests verify the supported binary.
- dStack owns selector, validation, refusal, Git evidence, documentation, and delivery policy; fast tests verify those
  decisions without reimplementing Beads.
- Git owns repository state; fast tests use real temporary Git repositories for Git behavior.

No coverage threshold or fixed test count is used. Every test asserts an observable result, invariant, refusal, or
failure boundary.

## Controller command timeouts

Every external Git, Beads, GitHub CLI, Python, and mdBook invocation has a bounded timeout. A timeout reports the
command, working directory, limit, and whether the operation may have mutated state; it never claims that a timed-out
mutation was safely rolled back. Set `DSTACK_COMMAND_TIMEOUT_SECONDS` to a positive number only when a repository's
known validation boundary needs a larger uniform limit.
