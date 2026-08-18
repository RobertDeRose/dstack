# Compatibility and legacy repair

Compatibility code is intentionally isolated from normal workflow execution.
It exists only to remove known historical dStack artifacts and adopt active
legacy features.

## Setup repair

Normal setup installs and validates formula source. It also applies dStack's
standard Git boundary: `.beads/interactions.jsonl` stays local and untracked,
while legitimate Beads repository configuration remains trackable. Normal setup
does not scan or rewrite all Beads work.

Explicit legacy repair may:

- remove verified persisted formula-template artifacts;
- remove obsolete duplicated metadata/labels from current molecules;
- repair an older repository that still tracks `.beads/interactions.jsonl`.

Run repair only through `/setup-project --force` or the explicit setup repair
command. Normal feature execution never runs it.

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
