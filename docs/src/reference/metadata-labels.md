# Metadata and labels

dStack uses a small stable vocabulary. Beads remains authoritative; these fields identify product intent and native
lifecycle roles, not transient execution state.

## Root metadata

| Key | Meaning |
| --- | --- |
| `dstack.created_formula_version` | Formula contract version that created/materialized the workflow root; historical provenance |
| `dstack.formula_version` | Latest formula contract version whose semantics were approved/audited for the workflow root |
| `dstack.base_branch` | Feature delivery target |
| `dstack.design_path` | Canonical tracked design path under `docs/src/features` |
| `dstack.pending_design_sha256` | Committed design digest for an incomplete approval attempt; never sufficient for implementation |
| `dstack.approved_design_sha256` | Digest of accepted committed design bytes; invalidated before reauthorization |

Never store task-to-commit, implementation, delivery/finalization, or evidence commit mappings, worktree paths, claims,
next commands, repository snapshots, or delivery state in metadata. `/project-audit` stores no audit result or review
packet; accepted corrective work uses the ordinary feature graph.

## Root and work labels

- `dstack:feature-idea` and one `feature:<slug>` label identify parentless planned intent before materialization.
- `workflow:feature` and one compatible `feature:<slug>` identity label a parentless feature epic or molecule.
- `dstack:work:implementation` marks bounded implementation tasks.

Stable formula step labels identify specification, approval, implementation, and closeout roles. Formula validation owns
the exact set; dynamic children do not duplicate root identity labels or root metadata. Issue type alone never establishes
a root because implementation workstreams are also epics. Historical compatibility aliases may be read when resolving
old work but are not normalized merely because a formula changes.
