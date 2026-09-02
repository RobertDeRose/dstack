# Compatibility

The controller supports Beads 1.x beginning with 1.2.2. Compatibility is proven through behavioral acceptance tests, not
exact build-string matching.

Required native behavior includes:

- formula parsing and persistent molecule pouring;
- parent/label filtered ready work and atomic claims;
- blocking and parent-child dependencies;
- human gates;
- dynamic implementation children;
- `bd worktree` create/list/remove/info;
- shared Beads discovery across linked worktrees;
- `bd history`, `bd doctor`, and JSON output; and
- Git-hook integration through hk.

The reviewed task graph adds explicit task-to-audit blockers as a conservative native fallback in addition to formula
`children-of(implementation)` fan-in. This is still Beads state; dStack does not recalculate fan-in.

The implementation epic is structural and has no `blocks` dependency on the approval task. Beads 1.2.2 enforces
same-kind blocking edges, so review attaches approval directly to each task-shaped implementation child instead.

Formula changes are normal reviewed project-configuration changes. Existing molecules remain historical native Beads
graphs and are not migrated merely because a packaged formula changes. No compatibility-audit stamp or formula migration
state is maintained.
