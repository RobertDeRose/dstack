# Compatibility and legacy repair

Compatibility code is intentionally isolated from normal workflow execution. It exists only to remove known historical
dStack artifacts and adopt active legacy features.

## Supported boundary

- Beads: `bd version 1.2.2 (6c124203e)` exactly.
- mdBook: `mdbook v0.5.3` exactly.
- Python: 3.13.

Setup doctor requires `--delivery-mode merge|pr`. Both profiles reject a pinned version mismatch. Merge mode checks only
local/common requirements and does not require a remote, GitHub, or `gh`. PR mode additionally requires a usable
GitHub-compatible target remote, authenticated `gh`, and native Beads `gh:pr` gate capability. Run dStack with the
mise/aqua-installed acceptance binary first on `PATH`; a separately installed Homebrew 1.2.2 binary has different build
output and is not covered by the exact contract. Upgrades require an explicit compatibility change, formula preflight,
fast validation, and both isolated real-Beads acceptance scenarios; changing a version constraint without that evidence
is unsupported.

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

Run repair only through `/setup-project --force` or the explicit setup repair
command. Forced setup first normalizes mechanically safe legacy documentation,
then completes missing core documentation/navigation, applies the remaining
known compatibility repair, and finally performs strict mdBook validation.
This order lets a repairable legacy source or navigation shape reach the
canonical layout before strict validation. The resulting mdBook must validate.
Normal setup creates missing core documentation but never relocates legacy
content; normal feature execution never runs compatibility repair.

## Active legacy feature adoption

`/adopt-feature` first runs a deterministic inspection that classifies obvious
old lifecycle nodes. The agent decides only which ambiguous tasks represent
real remaining product work. The apply step then pours one current molecule,
recreates selected remaining tasks, uses native `supersedes` relationships, and
leaves specification approval open.

No migration packet, manifest, Git-SHA mapping, or dStack migration database is
created. Closed historical work remains in place.

When no active old-dStack features remain in supported repositories, the
adoption command may be moved to an optional compatibility package or removed.
