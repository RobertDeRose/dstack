# Metadata and labels

dStack uses a small stable vocabulary. Beads remains authoritative; these fields identify product intent and native
lifecycle roles, not transient execution state.

## Root metadata

| Key | Meaning |
| --- | --- |
| `dstack.base_branch` | Feature delivery target |
| `dstack.design_path` | Canonical tracked design path under `docs/src/features` |
| `dstack.pending_design_sha256` | Committed design digest for an incomplete approval attempt; never sufficient for implementation |
| `dstack.approved_design_sha256` | Digest of accepted committed design bytes; invalidated before reauthorization |
| `dstack.target_branch` | Project-alignment delivery target |
| `dstack.scope` | Durable alignment scope |

Never store commit hashes, worktree paths, claims, next commands, or delivery
state in metadata.

## Root and work labels

- `dstack:feature-idea` marks planned intent before materialization.
- `workflow:feature` and `feature:<slug>` identify a current feature root.
- `workflow:project-alignment` identifies an alignment root.
- `dstack:work:implementation` marks bounded implementation tasks.
- `dstack:work:correction` marks bounded alignment corrections.

Stable formula step labels identify specification/analysis, approval, implementation/corrections, and closeout/landing
roles. Formula validation owns the exact set; dynamic children do not duplicate root identity labels. Deprecated
compatibility aliases may be read only by explicit repair and must not be written by normal commands.
