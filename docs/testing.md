# Testing dStack

## Running the suite

```bash
uv run pytest
```

The default uv development group includes pytest and PyYAML, so a clean clone
does not require manual `uv add` commands.

## Test layers

1. Pure/unit tests validate parsing, selector rules, Git evidence, docs policy,
   and idempotent transition decisions.
2. A fast Beads test double exercises failure injection and expected command
   sequences.
3. Real-Beads integration tests exercise the supported `bd` binary, formulas,
   gates, ready work, claims, fan-in, JSON envelope mode, and cleanup.

The test double is never release authority for Beads behavior.

## Release acceptance

A release must verify, when a real `bd` binary is available:

- formula install and isolated pour;
- no persisted template pollution;
- legitimate tracked Beads configuration versus forbidden runtime state;
- local/untracked `.beads/interactions.jsonl`;
- a committed repository setup boundary before feature execution;
- human gate and approval milestone;
- dynamic task creation and atomic claim;
- dynamic child fan-in;
- design digest approval;
- commit footer audit after history rewriting;
- stale remote-base PR refusal;
- no post-delivery Git mutation;
- explicit legacy adoption;
- `BD_JSON_ENVELOPE=1` output.

Set `DSTACK_REAL_BD` to the binary path to force the real integration suite.
