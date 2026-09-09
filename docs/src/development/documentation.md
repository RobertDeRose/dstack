# Documentation

dStack's own documentation follows the same feature-publication pattern that dStack provides to other repositories.
The mdBook under `docs/` is the current product documentation; accepted feature designs are preserved under
[References > Implemented Features](../reference/implemented-features.md).

## Feature documentation

A feature plan stores its accepted design in Beads using the standard sections:

- Goals
- User-facing behavior
- Implemented design
- Compatibility and constraints
- Validation
- Non-goals

During close, that accepted design is exported verbatim to `docs/src/features/<slug>/design.md`. The reader-facing
`index.md` adds the context that should be written for humans:

```markdown
# <Feature>

## Overview

<What the feature is and where it fits.>

## User Impact

<What changed for users, operators, or contributors.>

## Implemented Design

{{#include design.md}}
```

The design is not rewritten during documentation closeout. The Overview and User Impact explain the implemented feature;
the included design preserves the reviewed implementation contract.

Use the dStack documentation commands from the feature worktree:

```bash
dstack docs export-design --bead <feature> --scaffold
dstack check docs --slug <slug>
dstack docs commit --bead <feature>
```

In this repository, the finished feature page is placed under **References > Implemented Features** in `SUMMARY.md`.
The generic scaffold does not impose that navigation choice on repositories that use dStack.

## Editing the book

General product, architecture, development, and reference documentation is edited directly under `docs/src/`. Keep each
page focused on its audience instead of copying feature designs or workflow state into multiple sections.

Build the book with:

```bash
mise run docs:build
```

For local editing with automatic reload:

```bash
mise run docs:serve
```

The documentation build is also part of the repository's hk validation.
