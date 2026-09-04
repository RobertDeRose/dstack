# Lean workflow and documentation lifecycle

## Overview

dStack now keeps workflow authority in native Beads while limiting its own role to deterministic repository mechanics.
The explicit lifecycle is `/plan-feature`, `/review-plan`, human approval, `/implement`, and `/close-feature`.
`/audit-project` starts a normal remediation feature when a broader project review finds confirmed drift.

Planning records intent, review reconciles that intent with targeted repository and memory evidence, and implementation
claims one native ready task at a time. Close performs the holistic delivery review before publishing feature
documentation. Native gates protect human approval and material ambiguity; implementation fan-in controls final close
readiness.

## User Impact

The workflow no longer activates merely because Beads is installed or a dStack skill is available. Users invoke public
prompt commands explicitly, while packaged skills remain unavailable for automatic model selection. Beads owns claims,
dependencies, readiness, gates, decisions, and durable memory; current repository documentation and accepted decisions
take precedence over stale memory.

Each repository-changing implementation task produces one canonical commit with a `Task:` trailer. Plain task titles
default to `feat(<slug>)`; explicit conventional prefixes select another supported type. Safe corrections are folded
into that unpublished commit. Feature documentation is deferred until close and published in one final `docs(<slug>)`
commit. Target repositories continue to own their validation command, and dStack separately validates only the minimal
feature-document structure it requires.

## Implemented Design

{{#include design.md}}
