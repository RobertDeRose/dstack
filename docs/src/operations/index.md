# Operations

dStack is opt-in. Activate the workflow with `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`,
`/audit-project`, or an explicit request to use dStack.

The workflow commands guide semantic work. The `dstack` CLI performs the deterministic operations named by those
commands. Use the [CLI reference](../reference/cli.md) for exact syntax.

For interrupted work, use [Recovery](recovery.md). For repository-wide drift review, use
[Project audit](project-audit.md).

Target repositories own their own test, lint, build, documentation, and other project-validation commands. dStack does
not impose this repository's development tooling on them.
