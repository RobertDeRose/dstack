# Documentation

Documentation is part of the product and changes with the behavior it describes.

## Audiences

- **End users:** installation, configuration, usage, operations, and troubleshooting.
- **Developers:** architecture, interfaces, data flow, invariants, tests, and extension points.

Durable architecture and design rationale belongs in accepted decisions and targeted Beads memory rather than a
mandatory per-task future-agent classification.

## Current truth

The mdBook under `docs/` is the canonical repository documentation. Architecture describes the running system;
operations explain how to use it; reference pages state exact contracts; development pages explain how to change and
validate it. Current documentation and accepted decisions outrank stale memory.

Use Beads for live plans, tasks, decisions, blockers, claims, and readiness only inside an explicitly activated dStack
workflow. Do not copy those facts into Markdown.

## Feature documentation

Close writes stable reader-facing feature documentation under `docs/src/features/<slug>/` only after implementation
review passes. `index.md` contains a title, meaningful Overview and User Impact sections, and an Implemented Design
section with exactly one native mdBook include targeting `design.md`. The design file is exported verbatim from the
unique plan Bead:

```bash
dstack docs export-design --feature <feature-root>
dstack check docs --feature <slug>
```

The feature check rejects unsafe paths, symlinks, invalid includes, duplicate navigation, and direct SUMMARY links to
the design. It does not enforce global book layout, orphan pages, ADR format, unrelated links, or an mdBook build.
Repository lint and pre-commit workflows own those broader checks.
