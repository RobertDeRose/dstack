# Testing and tooling

Run the fast suite and native acceptance suite with:

```bash
uv run pytest                 # xdist workers are enabled automatically
uv run pytest tests/acceptance
```

The default pytest configuration uses `pytest-xdist` with `-n auto`. Pass `-n 0` when a serial run is needed.

Run the complete repository contract with:

```bash
hk check -a
```

Fast tests cover stateless adapters and validators. Acceptance tests execute Beads 1.2.2 and verify the native formula,
readiness, claims, gates, dependencies, worktrees, and Git evidence used by the skills.

This repository chooses hk as its project-validation contract; dStack does not impose hk on target repositories or run
it as a CLI runtime dependency. Skills run each target repository's documented validation command. hk owns formatting,
linting, type checking, tests, and documentation validation here. Its Beads hooks integrate through native `bd hooks`
commands.

## Internal boundaries

The Python package keeps native authority and workflow policy separate:

- `core.py` contains generic process and filesystem primitives. It has no Beads environment or workflow policy.
- `beads.py` is the thin native Beads adapter. It injects the supported JSON-envelope environment, performs workspace
  and version preflight, and uses complete lifecycle reads where recovery requires them.
- `git_state.py` reads Git/worktree/evidence state and serializes repository mutations. Native interrupted operations
  remain Git state; this layer detects them without creating a recovery journal.
- `policy.py` owns mechanical plan, task, commit-message, and commit-path policy. Read-only validators consume these
  rules without depending on the mutating Git command layer.
- `docs.py` owns feature-publication structure and detects whether publication differs from the inherited base state.
- `workflow.py` derives feature identity, fixed steps, implementation children, and graph invariants from Beads data.
- `task_validation.py` composes read-only workflow, policy, and Git evidence into the shared implementation-task
  validator used by both `check task` and `audit`.
- `git_ops.py` owns state-changing Git commit/correction operations and verifies them against `policy.py` and `docs.py`.
- `commands.py` and `audit.py` orchestrate those lower-level operations; lower-level modules must not import command
  handlers.

Keep these boundaries narrow. Do not add repository/service abstractions or duplicate Git/Beads state to make recovery
easier. Restartability is reconstructed from the native stores.

Fast tests include architectural checks for these import and environment boundaries and shared task-evidence tests. The
acceptance suite remains responsible for real Beads/Git recovery behavior.
