# Operations

The dStack workflow is opt-in. Normal work does not use Beads. Invoke `/plan-feature`, `/review-plan`, `/implement`, or
`/audit-feature` (or explicitly request dStack) to activate it.

When the workflow is active, use the targeted skills for planning, review, implementation, and audit. Use dStack for the
deterministic operations described in the [command contracts](../reference/cli.md). Do not run `bd prime` as a generic
session hook; dStack skills provide the workflow context they need.

The project validation contract is:

```bash
hk check -a
```
