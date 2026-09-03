# Environment

| Setting | Default | Purpose |
| --- | --- | --- |
| `PI_CODING_AGENT_DIR` | `~/.pi/agent` | Agent resource installation target |
| `DSTACK_COMMAND_TIMEOUT_SECONDS` | Command-specific | Positive finite subprocess timeout override |
| `BD_JSON_ENVELOPE` | `1` in dStack subprocesses | Stable Beads JSON output |

Project validation always runs `hk check -a`. Agent-facing commands cannot replace it with a weaker command or alternate
Git evidence range.

Planning records the base branch on the feature root. The default is `dev` when it exists and `main` otherwise. Feature
branches use `feat/<slug>` and conventional sibling worktrees use `<repository>.feat-<slug>`.
