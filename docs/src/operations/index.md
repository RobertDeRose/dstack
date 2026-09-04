# Operations

The dStack workflow is opt-in. Normal work does not use Beads. Invoke `/plan-feature`, `/review-plan`, `/implement`,
`/close-feature`, or `/audit-project` (or explicitly request dStack) to activate it.

When active, use targeted prompts for planning, review, implementation, close, and [project audit](project-audit.md).
Use dStack for the deterministic operations in the [command contracts](../reference/cli.md). Do not run `bd prime` as a
generic session hook; hidden skills provide their own workflow context.

This repository's project-validation contract is:

```bash
hk check -a
```

Other target repositories own and document their validation command.
