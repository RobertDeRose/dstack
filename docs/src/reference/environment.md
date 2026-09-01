# Environment and defaults

| Setting | Default | Contract |
| --- | --- | --- |
| `DSTACK_COMMAND_TIMEOUT_SECONDS` | Per-tool values below | Positive numeric override applied uniformly to external commands |
| Feature base branch | `dev` when present, otherwise `main` | Planning and initialization use this only when no explicit base branch is supplied |
| Formula source | Package-owned TOML | Installed bytes must match exactly |
| Documentation source | `docs/src` | `docs/book.toml` must remain contained and canonical |
| Beads JSON envelope | Enabled internally | Controller parses the supported structured envelope |

Default command timeouts are 120 seconds for Git, 180 seconds for Beads and GitHub CLI, and 300 seconds for mdBook and
Python. A timeout says whether the operation may have mutated state and never claims rollback.

Beads chooses its actor through its native configuration and environment. Git uses native user, credential, remote, and
signing configuration. GitHub CLI uses its native authentication sources. dStack does not copy those credentials into
Beads or documentation and does not define a second credential store.

Repository configuration is durable only when it belongs to the project. Machine-local Beads runtime files and
`interactions.jsonl` remain untracked. Unknown environment overrides are not a supported dStack API.
