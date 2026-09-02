# Delivery

Delivery remains a repository policy implemented with native Git and the hosting
provider. dStack's minimal feature workflow ends after implementation and
documentation agree with approved intent.

A project may add an ordinary delivery task or native `gh:pr` gate when delivery
must be represented in Beads. That task belongs to the project's formula or
reviewed implementation graph; dStack does not infer a hidden delivery phase from
an open root and does not maintain PR-gate replacement state.

Before delivery, the project should require a clean feature worktree, passing hk
checks, successful feature audit, and the repository's normal protected-branch
rules. Git remains authoritative for merge ancestry and delivery history.
