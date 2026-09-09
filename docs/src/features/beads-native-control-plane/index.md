# Beads-native control plane

## Overview

The Beads-native control plane made Beads the durable source of dStack workflow state while Git remains responsible for
repository content and history. dStack reads those systems directly for deterministic workflow operations instead of
maintaining a separate state model.

The feature established the responsibility split that the current feature lifecycle builds on: Beads tracks workflow
progress and relationships, Git tracks repository work, skills make semantic decisions, and the dStack CLI performs
repeatable checks and repository mechanics.

## User Impact

Feature progress, task ownership, dependencies, approval gates, and completion are represented directly in Beads.
Interrupted repository work remains visible through Git, so a later session can resume existing tasks and worktrees
instead of reconstructing them from dStack-specific recovery data.

The workflow remains explicit: repository setup and deterministic checks do not create feature work, while the workflow
commands create and advance the Beads-backed feature lifecycle when requested.

## Implemented Design

{{#include design.md}}
