## dStack control-plane contract

Beads is the sole authority for feature workflow state, tasks, dependencies,
gates, claims, decisions, and the next ready item. Start or resume work from
native Beads output; never infer a workflow phase from Markdown or dStack state.

Use dStack only for deterministic repository mechanics: installing the formula,
enforcing feature worktree policy, validating plan/task structure, generating
commit messages, checking repository evidence, validating documentation, and
collecting read-only audit evidence.

Current repository documentation explains how the system works. Beads decision
records preserve why material choices were made. Git records what changed. Do
not create workflow ledgers, handoff packets, readiness caches, Git-SHA maps, or
mandatory feature-history documents.
