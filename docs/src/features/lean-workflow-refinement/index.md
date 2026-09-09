# Lean workflow and documentation lifecycle

## Overview

dStack keeps workflow authority in Beads while limiting its own role to deterministic repository mechanics. The
user-facing lifecycle is `/plan-feature`, `/review-plan`, human approval, `/implement`, and `/close-feature`.
`/audit-project` is separate and creates a normal remediation feature only when a broader project review finds confirmed
drift.

Planning records intent, review reconciles that intent with focused repository and memory evidence, and implementation
resumes or claims one ready task at a time. Close performs the holistic delivery review before documentation
publication. Human gates protect approval and material ambiguity; persistent task blockers control close readiness.

## User impact

The workflow does not activate merely because Beads is installed or a dStack skill is available. Users explicitly invoke
workflow commands, while packaged skills remain unavailable for automatic model selection. Beads owns claims,
dependencies, readiness, gates, decisions, and durable workflow state. Current repository documentation and accepted
decisions take precedence over stale memory.

Each repository-changing implementation task produces one canonical commit with a `Task:` trailer. Plain task titles
default to `feat(<slug>)`; explicit conventional prefixes select another supported type. Safe corrections are folded
into that unpublished commit.

Feature documentation is deferred until close. New or changed documentation receives one close-owned
`docs(<slug>): <feature title>` commit. Documentation already inherited unchanged from the base is accepted without an
empty replacement commit. Target repositories continue to own their validation commands, while dStack validates only
the feature-document structure and ownership it requires.

## Implemented design

{{#include design.md}}
