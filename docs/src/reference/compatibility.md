# Compatibility and legacy repair

Compatibility code is intentionally isolated from normal workflow execution. It exists only to remove known historical
dStack artifacts and adopt active legacy features.

## Supported boundary

- Beads: `bd version 1.2.2 (6c124203e)` exactly.
- mdBook: `mdbook v0.5.3` exactly.
- Python: 3.14 (the package lock currently selects 3.14.7).

Setup doctor requires `--delivery-mode merge|pr`. Both profiles reject a pinned version mismatch. Merge mode checks only
local/common requirements and does not require a remote, GitHub, or `gh`. PR mode additionally requires a usable
GitHub-compatible target remote, authenticated `gh`, and native Beads `gh:pr` gate capability. The bundled launcher runs
Python entry points in the package-relative `mise.toml`/`mise.lock` environment, so an ambient `PATH` entry—including a
separately installed Homebrew 1.2.2 binary—cannot replace the tested build. Prepare missing tools with
`mise --cd <dstack-package-root> install --locked`. Upgrades require an explicit compatibility change, formula
preflight, fast validation, and both isolated real-Beads acceptance scenarios; changing a version constraint without
that evidence is unsupported.

## Pinned compatibility shims

| Limitation | Reproducer | Compensation | Retirement condition |
| --- | --- | --- | --- |
| Blocking dependencies must connect like issue kinds | Real formula contract pour and gate/readiness scenario | A task-sized approval milestone carries the human gate; dynamic tasks depend on the milestone | Supported Beads proves the intended cross-kind topology and migrated formulas pass acceptance |
| Dynamic-child terminal readiness can ignore a nonterminal direct child | Real contract and smoke fan-in refusal | dStack only vetoes terminal claim when a direct child is nonterminal; Beads still supplies positive readiness | Supported Beads natively blocks the terminal in the pinned reproducer |
| Terminal completion can auto-close the molecule root before Git delivery | Real smoke closeout/landing scenario | dStack reopens only the automatically closed root while delivery is pending | Supported Beads provides a native delivered boundary or no longer auto-closes in the reproducer |

These shims are narrow negative safety checks, not a second readiness engine. No stable upstream issue reference is
recorded for the pinned build; the executable acceptance reproducer is the retirement evidence.

## Setup repair

Normal setup installs and validates formula source. It also applies dStack's standard Git boundary:
`.beads/interactions.jsonl` stays local and untracked, while legitimate Beads repository configuration remains
trackable. Normal setup does not scan or rewrite all Beads work.

Explicit legacy repair may:

- remove verified persisted formula-template artifacts;
- remove obsolete duplicated metadata/labels from current molecules;
- repair an older repository that still tracks `.beads/interactions.jsonl`;
- canonicalize a safe non-`src` mdBook `[book].src` tree into `docs/src` while preserving its relative layout; and
- move mechanically placed book content from elsewhere under `docs/` into `docs/src`, including chapters named by
  `SUMMARY.md`, mdBook include targets, referenced local assets, and the historical `docs/features/<slug>/design.md`
  layout.

Documentation migration is conservative and conflict checked. Navigation and local references are rewritten with the
move, query/fragment suffixes are preserved, authored content is not overwritten, and retries derive everything again
from visible filesystem/configuration truth. Markdown outside `docs/src` whose chapter placement is not mechanically
established is reported and left for agent/user judgment; dStack does not invent a taxonomy or silently turn a prose
cross-link into a `SUMMARY.md` hierarchy. Repository source/configuration files outside `docs/` are never treated as
documentation merely because a page links to them. Missing reconciliation records for older delivered features are
reported for authorship rather than created as empty pages.

Run repair only through `/setup-project --force` or the explicit setup repair command. Forced setup first normalizes
mechanically safe legacy documentation, then completes missing core documentation/navigation, applies the remaining
known compatibility repair, and finally performs strict mdBook validation. This order lets a repairable legacy source or
navigation shape reach the canonical layout before strict validation. The resulting mdBook must validate. Normal setup
creates missing core documentation but never relocates legacy content; normal feature execution never runs compatibility
repair.

Setup repair uses strict `dstack.setup-plan/v3` mutation records. The reviewed SHA-256 covers the complete canonical
operation object, including controller-content state and exact Python, Beads, and mdBook outputs, rather than display
summaries. Apply receives only that digest, recomputes one object, rejects controller/runtime drift or unmerged
authority source, and executes it without a second discovery pass. Initialization is an explicit reviewed operation, and
filesystem/formula/navigation records carry their exact source, destination, content, conflict, and before/after hash
predicates. Tool and isolated formula-bundle preflight completes before target mutation. Drift requires a new plan.

## Active legacy feature adoption

`/adopt-feature` is an explicit compatibility boundary. Planning consumes a strict temporary
`dstack.adoption-classification/v1` JSON document with exactly `schema`, `legacy_root_id`, and sorted `entries`. Every
open executable descendant appears exactly once under one of the supported classifications: completed history, remaining
implementation, obsolete lifecycle ceremony, unresolved decision, or preserved unchanged. Completed history requires
sorted Git-footer/source/test/documentation evidence and either verified evidence or an explicit accepted-risk reason.
Remaining and preserved recreation entries carry exact replacement title, description, acceptance, and priority;
unresolved decisions carry either an incorporated design section or a named native blocker. Unknown fields, IDs, paths,
strategies, missing work, duplicate entries, and unsupported relationships fail before any Beads mutation.

The pure planner inventories all descendants, closed history, outgoing external blockers, and incoming external
dependents. Its in-memory plan records exact replacement parent/label/approval requirements,
preserve/redirect/lifecycle-only relationship operations, add-before-remove ordering, and supersession postconditions.
Native task/bug/chore/gate relationships are checked against the pinned Beads compatibility matrix; an unsupported
bug/chore approval topology or root remap fails before pour. Apply is a separate two-pass native execution: exact
replacement content, parent, labels, and approval edges converge first; compatible outgoing blockers and incoming
external dependents are added and reread before old edges are removed. Unsupported incoming translation fails closed,
while planned nonblocking context is preserved. Native readiness is checked before and around translation. Interruption
retries use native replacement associations, relationships, and supersession only; no migration map is written.
Incorporated decisions keep their blocker and the legacy root unsuperseded until an approved committed-design retry
verifies resolution. Closed historical work remains in place.

When no active old-dStack features remain in supported repositories, the adoption command may be moved to an optional
compatibility package or removed.
