# Delivery

Delivery remains a repository policy implemented with native Git and the hosting provider. dStack's minimal feature
workflow ends after implementation and documentation agree with approved intent.

The packaged `dstack-feature` formula deliberately ends at audit and is checked byte-for-byte. Projects that need
delivery tracking should model it in a separate native Beads formula or ordinary project task rather than modifying the
dStack formula under the same name. dStack does not infer a hidden delivery phase from an open root and does not
maintain PR-gate replacement state.

Before delivery, the project should require a clean feature worktree, passing hk checks, successful feature audit, and
the repository's normal protected-branch rules. Git remains authoritative for merge ancestry and delivery history.
