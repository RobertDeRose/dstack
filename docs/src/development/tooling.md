# Testing dStack

## Installed CLI boundary

`dstack` is built as a normal Python package and installed with `uv tool install`. Controller modules live in the
top-level `dstack/` package. `dstack install_skills` installs the Pi prompts, decision skills, and compact managed
system-prompt additive; no executable controller code lives inside a skill.

Controller entry points verify the supported Beads binary, initialize Beads when necessary, and use packaged formula
source for native pours. No setup/migration fixture exists because upgrades do not normalize historical Beads.

## Documentation

The tested mdBook release is pinned for repository development through mise. Validate required pages, chapter
navigation, local links, orphan Markdown, and the build with:

```bash
dstack ctl docs validate
```

The build uses temporary output and external URLs are not fetched.

## Fast suite

The default suite exercises controller decisions in-process with immutable Beads protocol snapshots. It uses disposable
Git repositories where Git is the authority and never invokes a real `bd` binary.

```bash
uv run pytest -q -rs
```

The scripted client is a protocol stub only: it matches ordered calls and returns declared snapshots; it does not
calculate readiness, dependencies, ownership, gates, or lifecycle transitions.

## Real-Beads acceptance

Acceptance verifies the supported native boundary:

```bash
uv run pytest -q tests/acceptance/test_bd_contract.py
uv run pytest -q tests/acceptance/test_feature_smoke.py
```

An unavailable or invalid `bd` is an acceptance failure, never a skip. The contract scenario verifies Beads JSON,
formulas/pours, gates/readiness/claims, child fan-in, supersession, worktree primitives, and formula-contract auditing.
The smoke scenario runs one shipped feature through approval, one Git-backed task, closeout, and delivery.

## Packaging checks

Before release, build the package and verify installation resources:

```bash
uv build
uv tool install --force --python 3.14 .
dstack install_skills --agent-dir /tmp/dstack-pi-agent
```

The installed resource set must contain prompts and decision skills but no `dstack-beads-core` skill. The managed
`APPEND_SYSTEM.md` block must be idempotent and preserve unrelated existing content.

## Test ownership

- Beads owns lifecycle behavior; acceptance tests verify the supported binary.
- dStack owns selector, validation, refusal, Git evidence, documentation, packaging, and delivery policy; fast tests
  verify those decisions without reimplementing Beads.
- Git owns repository state; fast tests use real temporary Git repositories for Git behavior.

No coverage threshold or fixed test count is used. Every test asserts an observable result, invariant, refusal, or
failure boundary.
