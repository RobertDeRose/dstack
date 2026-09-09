# Lean workflow and documentation lifecycle

## Overview

This feature established dStack's current feature lifecycle: plan the requested change, review it against the repository,
obtain human approval, implement bounded tasks, and close the completed feature. Project auditing remains a separate
repository-wide workflow that can create a remediation feature when it finds actionable drift.

The feature also defined how implementation evidence and feature documentation are published. Repository-changing tasks
own one canonical task commit, persistent task blockers control close readiness, and feature documentation is finalized
only after the delivered work passes close review.

## User Impact

Users get a predictable path from an initial request to a reviewed and documented implementation. Planning captures
intent before broad repository investigation, review turns the accepted direction into implementation tasks, and
implementation can safely resume or correct unpublished task commits without creating parallel workflow state.

Close reviews the complete delivered feature before publishing documentation. New or changed feature documentation
receives one close-owned documentation commit, while valid documentation already inherited unchanged from the base is
accepted without an empty replacement commit. Target repositories continue to own their own tests, builds, linters, and
other project-specific validation.

## Implemented Design

{{#include design.md}}
