# Environment

| Setting | Default | Purpose |
| --- | --- | --- |
| `PI_CODING_AGENT_DIR` | `~/.pi/agent` | Agent resource installation target |
| `DSTACK_COMMAND_TIMEOUT_SECONDS` | Command-specific | Positive finite subprocess timeout override |
| `DSTACK_OUTPUT_FORMAT` | `compact` | Use `pretty` for standard-library indented JSON |
| `BD_JSON_ENVELOPE` | `1` in dStack subprocesses | Stable Beads JSON output |

Agent-facing output remains compact even when attached to a TTY. Set `DSTACK_OUTPUT_FORMAT=pretty` only for explicit
human-readable indentation; it adds no color or terminal control codes.

Target repositories own their project-validation contract. dStack skills run the command documented by the target
repository instead of imposing hk, mdBook, or another validation tool.

Planning records the base branch on the feature root. The default is `dev` when it exists and `main` otherwise. Feature
branches use `feat/<slug>` and conventional sibling worktrees use `<repository>.feat-<slug>`.
