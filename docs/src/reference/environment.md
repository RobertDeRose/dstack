# Environment

| Setting | Default | Purpose |
| --- | --- | --- |
| `PI_CODING_AGENT_DIR` | `~/.pi/agent` | Agent resource installation target |
| `DSTACK_COMMAND_TIMEOUT_SECONDS` | Command-specific | Positive finite subprocess timeout override |
| `DSTACK_OUTPUT_FORMAT` | `auto` | `pretty`, `compact`, or terminal-aware `auto` Rich JSON formatting |
| `BD_JSON_ENVELOPE` | `1` in dStack subprocesses | Stable Beads JSON output |

Project validation always runs `hk check -a`. Agent-facing commands cannot replace it with a weaker command or alternate
Git evidence range. In `auto` output mode, terminal streams use pretty JSON and redirected streams use compact JSON; set
`DSTACK_OUTPUT_FORMAT=compact` when an agent is attached to a PTY; otherwise Rich formats the terminal output.

Planning records the base branch on the feature root. The default is `dev` when it exists and `main` otherwise. Feature
branches use `feat/<slug>` and conventional sibling worktrees use `<repository>.feat-<slug>`.
