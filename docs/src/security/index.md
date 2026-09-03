# Security

dStack runs trusted local tools with the invoking user's filesystem, Git, Beads, and hook privileges. Review repository
files, formulas, documentation, and hook configuration before authorizing mutations.

Commands use argument arrays rather than shell interpolation. Path checks reject absolute, traversing, and
symlink-escaping paths for worktrees, documentation, formulas, and installed agent resources.

Do not put secrets, credentials, private keys, customer data, or unredacted incident material in Beads, documentation,
commit messages, or command output. Keep Beads interaction data subject to the project's retention and redaction policy.

History rewrites, destructive cleanup, and repository delivery require explicit native authorization.
