# dStack

dStack gives software-engineering agents a small set of deterministic repository operations around a Beads-backed
feature workflow.

The workflow is opt-in. Beads owns workflow state, Git owns repository content and history, and the target repository
owns its validation commands. dStack does not add another task database, readiness engine, or recovery journal.

Users interact with two surfaces:

- **workflow commands** such as `/plan-feature` and `/implement`, which load the stage-specific skill and guide semantic
  work; and
- **CLI commands** such as `dstack check task`, which validate or perform deterministic mechanics.

Start with [Getting started](getting-started/index.md). Use [Operations](operations/index.md) for day-to-day workflow and
recovery guidance, and [CLI reference](reference/cli.md) when you need exact command syntax.
