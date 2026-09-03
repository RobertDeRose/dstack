# Compatibility

dStack supports the exactly tested Beads 1.2.2 release. Compatibility is proven through behavioral acceptance tests,
not broad major-version assumptions or exact prose matching.

Required native behavior includes:

- formula parsing and persistent molecule pouring;
- parent/label filtered ready work and atomic claims;
- create-with-dependencies and parent-label inheritance controls;
- blocking, parent-child, and waits-for dependencies;
- human gates;
- dynamic implementation children;
- `bd worktree` create/list/remove/info;
- shared Beads discovery across linked worktrees;
- `bd history` and JSON output; and
- Git-hook integration through hk.

The audit uses only formula `children-of(implementation)` fan-in. Explicit task-to-audit blockers are rejected because
they duplicate the same workflow guarantee and can drift independently.

The implementation epic is structural and has no `blocks` dependency on the approval task. Beads 1.2.2 enforces
same-kind blocking edges, so review creates each task-shaped implementation child atomically with its approval blocker.

Formula changes are normal reviewed project-configuration changes. Existing molecules remain historical native Beads
graphs and are not migrated merely because a packaged formula changes. No compatibility-audit stamp or formula migration
state is maintained.
