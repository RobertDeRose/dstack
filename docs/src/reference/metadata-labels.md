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
| `dstack.pending_alignment_plan_sha256` | Canonical alignment-plan digest while approval is incomplete |
| `dstack.approved_alignment_plan_sha256` | Canonical alignment-plan digest after approval |

Never store task-to-commit, implementation, delivery/finalization, evidence, or bookkeeping commit mappings, worktree
paths, claims, next commands, or delivery state in metadata. The narrow project-alignment `baseline_commit` workflow
input belongs only in the canonical plan description, never root metadata.

## Root and work labels

- `dstack:feature-idea` and one `feature:<slug>` label identify parentless planned intent before materialization.
- `workflow:feature` and one compatible `feature:<slug>` identity label a parentless feature epic or molecule.
- `workflow:project-alignment` and one compatible `audit:<slug>` identity label a parentless alignment molecule.
- `dstack:work:implementation` marks bounded implementation tasks.
- `dstack:work:correction` marks bounded alignment corrections.

Stable formula step labels identify specification/analysis, approval, implementation/corrections, and closeout/landing
roles. Formula validation owns the exact set; dynamic children do not duplicate root identity labels or root metadata.
Issue type alone never establishes a root because implementation and corrections workstreams are also epics. Deprecated
compatibility aliases may be read only by explicit repair and must not be written by normal commands.
