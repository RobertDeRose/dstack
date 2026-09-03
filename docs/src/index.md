# dStack

dStack gives software-engineering agents a small, deterministic set of repository operations around a native Beads
workflow.

The dStack workflow is opt-in: ordinary requests do not invoke Beads or create tasks. When explicitly activated, Beads
owns workflow state. Git owns repository content and history. hk owns repeatable project checks. Skills make semantic
decisions, while `dstack ctl` validates and performs repository mechanics.

Start with [Getting started](getting-started/index.md), then read the [Architecture](architecture/index.md) and
[Feature lifecycle](development/feature-lifecycle.md).
