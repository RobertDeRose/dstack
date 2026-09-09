# Documentation

Documentation is part of the product and changes with the behavior it describes.

## Audiences

- **Users:** installation, configuration, usage, operations, and troubleshooting.
- **Developers:** architecture, interfaces, data flow, invariants, tests, and extension points.

Accepted feature designs are published under [References > Implemented Features](../reference/implemented-features.md).
Live plans, decisions, blockers, claims, and readiness remain in Beads instead of being copied into Markdown.

## Current truth

The mdBook under `docs/` is the canonical repository documentation. Getting Started covers onboarding and normal use;
Interrupted Skill Recovery covers restart procedures; Architecture explains responsibilities and data flow; References
state exact contracts and preserve implemented feature designs; and Development and Contributions explains how to
change and validate dStack.

Current documentation and accepted Beads decisions remain the source for current product guidance.

## Feature documentation

Close writes reader-facing feature documentation under `docs/src/features/<slug>/` only after semantic review passes.
`index.md` contains a title, meaningful Overview and User Impact sections, and an Implemented Design section with
exactly
one mdBook include targeting `design.md`. The design file is exported verbatim from the feature's plan issue:

```bash
dstack docs export-design --bead <feature>
dstack check docs --slug <slug>
dstack docs commit --bead <feature>
```

The structural documentation check rejects unsafe paths, symlinks, invalid includes, duplicate navigation, and direct
`SUMMARY.md` links to the design. It does not enforce global book layout, orphan pages, unrelated links, or an
mdBook build. Repository lint and pre-commit workflows own those broader checks.

## Repeatable publication

Use `dstack docs export-design --bead <feature> --scaffold` inside the registered feature worktree. Missing directories,
index sections, and the single `SUMMARY.md` entry are created mechanically; existing index prose is not replaced. Fill
Overview and User Impact before validation. The exported design remains exactly the accepted plan design.

`dstack check docs --slug <slug>` is a Beads-independent structural check. `dstack docs commit` and
`dstack check feature --bead <feature> --require-docs` additionally compare the exported design with the current plan
and
reject stale or hand-edited content. A byte comparison is validation, not approval; changed intent still requires the
user's agreement.

Application changes cannot be hidden in a close-owned documentation commit, and implementation tasks cannot own the
feature-documentation directory. When valid documentation is already inherited unchanged from the base, close does not
create an empty commit. New or changed feature documentation requires canonical close ownership.
