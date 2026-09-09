# Environment

## User settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `PI_CODING_AGENT_DIR` | `~/.pi/agent` | Pi agent directory used by `dstack install`. |
| `DSTACK_COMMAND_TIMEOUT_SECONDS` | `120` | Positive finite timeout, in seconds, for generic Git/process commands. |
| `DSTACK_OUTPUT_FORMAT` | `compact` | Set to `pretty` for indented JSON output. |

Beads commands use a fixed 180-second timeout so lifecycle reads and writes are not affected by the generic command
timeout override.

The Beads adapter sets `BD_JSON_ENVELOPE=1` internally for `bd` subprocesses. Users do not need to set it, and generic
Git/process commands do not receive that Beads-specific environment setting.

## Repository defaults

Planning records the base branch on the feature root. The default is `dev` when that branch exists and `main` otherwise.
Feature branches use `feat/<slug>`, and the conventional sibling worktree path is `<repository>.feat-<slug>`.

Target repositories own their own validation commands. dStack does not require hk, mdBook, or another particular
project-validation tool.
