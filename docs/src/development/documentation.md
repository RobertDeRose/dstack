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
dstack docs export-design --bead <feature-root>
dstack check docs --slug <slug>
dstack docs commit --bead <feature-root>
```

The feature check rejects unsafe paths, symlinks, invalid includes, duplicate navigation, and direct SUMMARY links to
the design. It does not enforce global book layout, orphan pages, ADR format, unrelated links, or an mdBook build.
Repository lint and pre-commit workflows own those broader checks. The final documentation commit is owned by the close
step. Close may propose reusable Beads memory, but it writes memory only after user approval and never treats memory as
publication or completion evidence.

## Repeatable publication

Use `dstack docs export-design --bead <root> --scaffold` inside the registered feature worktree. Missing directories,
index sections, and the single SUMMARY entry are created mechanically; existing index prose is not replaced. Fill the
empty Overview and User Impact sections before validation. The exported design remains verbatim native plan content.

`dstack check docs --slug <slug>` remains a Beads-independent structural check and rejects an empty design. The docs
commit and final audit additionally compare it with the current native plan, rejecting a stale or hand-edited export.
Changes to approved intent still require explicit human agreement; a byte comparison is not an approval mechanism.

Publication ownership is checked in both new and reused commits. Application changes cannot be hidden in a close-owned
commit, and implementation tasks cannot own the feature publication directory. When validated publication is already
inherited unchanged from the base, close does not create an empty commit. A new feature publication or its newly added
SUMMARY entry requires a canonical close-owned commit; `audit --require-docs` verifies that distinction from Git.
