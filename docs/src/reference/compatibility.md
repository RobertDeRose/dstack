# Compatibility

dStack's tested runtime boundary is:

- Python 3.14
- Beads 1.2.2

This repository uses mdBook 0.5.4 for its own documentation, but dStack does not require target repositories to use
mdBook or hk.

## Repository policy

The installed dStack formula and `.beads/PRIME.md` are reviewed repository policy. `dstack check formula` requires them
to match the installed package and requires the formula to match committed `HEAD` before new feature work begins.

The close step keeps the stable internal Beads identity `audit` / `dstack:step:audit` so existing molecules remain
readable while user-facing documentation consistently calls it close.

Formula version 4 replaced dynamic `waits-for` fan-in with persistent ordinary blockers from the close step to each
implementation task. Features created with older formula versions keep their existing graph; review or close repairs a
missing direct blocker when encountered instead of rewriting the entire molecule.

## Git evidence

Canonical implementation and documentation commits use exactly one `Task:` trailer. Legacy `Beads:` footers are not
ownership evidence. Implementation commit bodies come from ordered `Implementation:` task notes rather than planned
description or design prose.

A task correction may rewrite its unambiguous unpublished canonical commit and replay descendants. Published or
ambiguous evidence is not rewritten automatically.

## Recovery-sensitive Beads behavior

Restart and recovery depend on complete all-status Beads reads. dStack deliberately uses unbounded lifecycle list reads
(`--limit 0`) where omission could hide older or in-progress work.

The Beads v2-default JSON envelope currently reports `schema_version: 1`. dStack enables that envelope only for Beads
subprocesses and rejects unsupported schema versions.

## Agent contract

`.beads/PRIME.md` contains the common opt-in, authority, invocation, ownership, and recovery rules. Each installed skill
contains only its stage-specific workflow behavior and CLI commands.
