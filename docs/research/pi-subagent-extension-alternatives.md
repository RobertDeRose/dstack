# Research: Pi subagent extension alternatives

**Checked:** 2026-08-12 UTC

## Executive answer

The current reliability-first installation is `nicobailon/pi-subagents`, pinned at commit
`0cf7435913230564b3f930bf6b387545f91f5e37` (`v0.47.1`). It provides bounded whole-run execution, persisted sessions and
outputs, explicit wait/status controls, read-only acceptance gates, and optional Herdr presentation integration. It is
not a drop-in replacement for direct cmux child-pane orchestration.
[Its README](https://github.com/nicobailon/pi-subagents/blob/0cf7435913230564b3f930bf6b387545f91f5e37/README.md)
[its acceptance-gate reference](https://github.com/nicobailon/pi-subagents/blob/0cf7435913230564b3f930bf6b387545f91f5e37/docs/tool-reference.md#acceptance-gates)

The recent holistic-review failure exposed a completion/transport boundary in the former `edxeth/pi-subagents`
integration: durable reviewer output existed while the parent waited on a shell/mux sentinel. Its configured
`idle-timeout: 120` seconds also treated time inside a tool call as idle, which made a large packet read vulnerable to
premature failure. The redesigned contract therefore treats persisted session/output artifacts and bounded status
results as completion authority, and keeps cmux/Herdr visibility optional. The former local reviewer contract is
retained only in the pre-cutover session evidence; it is not a repository dependency.
[former timeout semantics](https://github.com/edxeth/pi-subagents/blob/7fee02db5269fa9884aa1ca12d427b86e359ce33/README.md#stop-a-runaway-child-with-time-limits)

**Recommendation:** keep the pinned `nicobailon/pi-subagents` baseline for reliability-first review orchestration.
Retain the former `edxeth/pi-subagents` only as an experimental visible-pane option behind an artifact-authority
adapter. If direct cmux/Herdr child panes become a hard requirement, trial that adapter separately; otherwise evaluate
`pi-native-subagents` and `pi-task` in a controlled A/B test rather than changing the production baseline.

## Evaluation criteria

I treated these as separate dimensions:

- **Model quality:** provider/model choice, context quality, and prompt quality. An extension cannot make a weak model
  reason well.
- **Lifecycle reliability:** bounded startup, timeout/cancellation, persistence, resume, failure reporting, and cleanup.
- **Evidence quality:** structured output, acceptance/verification gates, replay, and independent verification.
- **Visibility:** whether the child is a real inspectable cmux/Herdr pane.
- **Maturity signal:** released/published artifacts, test coverage, and explicit limitations. No candidate publishes a
  credible independent success-rate benchmark, so this is engineering evidence rather than a quality benchmark.

## Shortlist

| Candidate                               | cmux / Herdr                                                                                                                                                                                                                                           | Reliability evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Main risk                                                                                                                                                                                         | Verdict                                                                           |
|-----------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| **Former `edxeth/pi-subagents`**        | **Both**; also tmux, Zellij, WezTerm                                                                                                                                                                                                                   | Separate foreground/background and sync/async modes; session modes; timeout and idle-timeout; parent-owned timeout wrap-up; provider-error recovery; session persistence; fake cmux/Herdr tests and guarded live tests. [README](https://github.com/edxeth/pi-subagents/blob/7fee02db5269fa9884aa1ca12d427b86e359ce33/README.md) [runtime tests](https://github.com/edxeth/pi-subagents/tree/7fee02db5269fa9884aa1ca12d427b86e359ce33/test)                                                                                                                                                                                                          | Observed completion/transport split: durable reviewer output existed while the parent waited on a shell/mux sentinel. Direct cmux visibility is useful, but pane state must not be authoritative. | **Experimental only until lifecycle is fixed.**                                   |
| **Installed `nicobailon/pi-subagents`** | Herdr status/inspector/project-pane integration; not the same direct cmux/Herdr child-pane backend. [Herdr API docs](https://github.com/nicobailon/pi-subagents/blob/0cf7435913230564b3f930bf6b387545f91f5e37/docs/extension-api.md#herdr-integration) | Published npm release `v0.47.1`; unit, integration, and E2E test suites; acceptance evidence levels; host-side verification commands; worktree isolation; persisted status/artifacts; model catalogs and fallback models. [release](https://github.com/nicobailon/pi-subagents/releases/tag/v0.47.1) [tool reference](https://github.com/nicobailon/pi-subagents/blob/0cf7435913230564b3f930bf6b387545f91f5e37/docs/tool-reference.md#acceptance-gates) [CI](https://github.com/nicobailon/pi-subagents/actions)                                                                                                                                     | Large/complex surface; gives up direct cmux child-pane orchestration and needs project-specific lifecycle integration.                                                                            | **Reliability-first replacement.**                                                |
| **`@vorsakha/pi-native-subagents`**     | No documented cmux/Herdr backend; has its own Pi dashboard.                                                                                                                                                                                            | Native Pi, Claude Code, and Codex backends; capability routing; explicit access policies; read-only/full modes; sandboxed workflow scripts; bounded concurrency/budgets; approvals; durable journals and replay; independent-provider routing. [README](https://github.com/vorsakha/pi-native-subagents/blob/f61d4bb9291dfee40b76acbbb8fe1baa6c21b742/README.md) [manager tests](https://github.com/vorsakha/pi-native-subagents/blob/f61d4bb9291dfee40b76acbbb8fe1baa6c21b742/tests/manager.test.ts) [workflow tests](https://github.com/vorsakha/pi-native-subagents/blob/f61d4bb9291dfee40b76acbbb8fe1baa6c21b742/tests/workflow-manager.test.ts) | Explicitly experimental; Git/local install rather than a published npm release; no visual cmux/Herdr panes.                                                                                       | **Most interesting quality/reliability pilot**, not a production replacement yet. |
| **`@shreyasdevadiga/pi-task`**          | No cmux/Herdr integration; native Pi TUI instead.                                                                                                                                                                                                      | Native in-process `AgentSession`; documented provider retries, typed events, final error metadata; isolated child sessions; resumable background work; cancellable concurrency leases; turn/output budgets; 14+ focused test files. [README](https://github.com/Shreyasd10/pi-task/blob/61c03ccd20c7e31ff22c5913e7a41de5b890d02c/README.md) [runtime](https://github.com/Shreyasd10/pi-task/blob/61c03ccd20c7e31ff22c5913e7a41de5b890d02c/src/task-runtime.ts) [tests](https://github.com/Shreyasd10/pi-task/tree/61c03ccd20c7e31ff22c5913e7a41de5b890d02c/test)                                                                                     | Early Git-only project; npm publication is documented as future work; mid-run steering is deferred.                                                                                               | **Good second pilot** if process isolation is the suspected cause of failures.    |
| **`pi-vigil`**                          | No cmux/Herdr integration.                                                                                                                                                                                                                             | Small workflow-agnostic lifecycle: durable child Pi sessions, explicit `wait`, bounded polling, fail-fast/late bootstrap failure detection, guarded completion, transcript search/read, and a substantial deterministic unit suite. Published npm `v0.1.6`. [README](https://github.com/itgeorge/pi-vigil/blob/f228e2bd0c93d0b28f85555bb179dc6dafc7c66c/README.md) [release](https://github.com/itgeorge/pi-vigil/releases/tag/v0.1.6)                                                                                                                                                                                                               | Intentionally has no retry, no background watcher, no workflow policy, and no visible terminal integration.                                                                                       | **Reliable primitive, not a full replacement** for the current workflow.          |
| **`@itc-steve/pi-herdr`**               | **Herdr only**, no cmux.                                                                                                                                                                                                                               | Difficulty-based model routing; local-first single-stream seat; queue/overflow policy; output artifacts; exclusive write lanes; monitored jobs; npm `v1.1.3`; focused tests. [README](https://github.com/itc-steve/pi-herdr/blob/12c2be873444f28457a0878df231fdf9554429e6/README.md) [release](https://github.com/itc-steve/pi-herdr/releases/tag/v1.1.3)                                                                                                                                                                                                                                                                                            | Requires Herdr and is narrower than the current extension; it does not improve the underlying model.                                                                                              | **Consider only for Herdr-first/local-model routing.**                            |

## cmux-specific options I would not choose as the replacement

- **`pi-cmux`** is a useful complement, not a subagent lifecycle replacement. Its documented features are notifications,
  sidebar status, splits, commands, directory jumps, review handoffs, and continuation sessions.
  [README](https://github.com/javiermolinar/pi-cmux/blob/c8ff70fe7c0c059f671f5f511801f6554655ada0/README.md)
- **`@mporenta/pi-cmux-orchestrator`** is a promising visible transport layer: it starts real Pi workers in cmux, tracks
  ownership, heartbeats, stale/ presumed-dead states, bounded startup, and human takeover. However, the npm package is
  only `0.1.1`, explicitly says it does not enforce a workflow, and its shipped tarball contains the runtime source but
  no test suite. [README](https://unpkg.com/@mporenta/pi-cmux-orchestrator@0.1.1/README.md)
  [package manifest](https://unpkg.com/@mporenta/pi-cmux-orchestrator@0.1.1/package.json)
- **`cmux-subagent`** is an agent skill, not a replacement extension. It is a very small async `cmux` + intercom handoff
  and has no published lifecycle or test evidence comparable to the candidates above.
  [README](https://github.com/elecnix/cmux-subagent/blob/c9a7e7087b888ef6150eeda4044309d634281535/README.md)

This matches cmux's own design statement: cmux supplies terminal, pane, notification, CLI, and socket primitives; it is
deliberately "a primitive, not a solution." Visibility alone should not be mistaken for orchestration reliability.
[cmux README](https://github.com/manaflow-ai/cmux/blob/b17c260b619f1e988b1f477bf45800268666bf92/README.md#the-zen-of-cmux)

Herdr is a stronger native runtime surface than a simple pane launcher: its agent docs describe real panes, state
authority, rollups, automation primitives, and Pi lifecycle hooks. The former `edxeth` extension already used that
surface, so switching to a Herdr-only extension would not automatically add a missing capability.
[Herdr agents](https://herdr.dev/docs/agents/) [Herdr automation](https://herdr.dev/docs/agent-automation/)

## Recommended decision path

### 1. Stabilize the replacement baseline

1. Pin `nicobailon/pi-subagents` to commit `0cf7435` or release `v0.47.1`; do not use an unpinned moving `main` for
   reliability-sensitive runs.
2. Keep the dstack reviewer definitions on supported frontmatter: fresh context, no inherited project context or skills,
   empty extension allowlist, read-only acceptance, and a 600,000 ms whole-run deadline. Do not emulate an idle timeout;
   a quiet tool call is not proof of failure.
3. Make large reviewers acknowledge before consuming the packet, and shard or summarize packet inputs so the first model
   response is not delayed by a large sequential read.
4. Treat session/output artifacts and explicit wait/status results as completion authority. Keep cmux/Herdr only for
   optional visibility and retry transport reads without converting a pane error into reviewer failure.

### 2. Run a controlled replacement trial

Use the same model, task, prompt, repository snapshot, and fresh context for:

1. `nicobailon/pi-subagents@0.47.1` at the pinned commit;
2. former `edxeth/pi-subagents` at the pinned commit;
3. `@vorsakha/pi-native-subagents` from a pinned commit;
4. `@shreyasd10/pi-task` from a pinned commit.

Run at least five repetitions of each of these bounded tasks:

- read-only review of a fixed packet with a required short initial ACK;
- factual repository scout with exact file/line evidence;
- small implementation in an isolated worktree followed by a fresh verifier;
- forced timeout/cancellation and resume recovery.

Record completion rate, timeout rate, provider/process failures, valid artifact rate, evidence omissions, resume
correctness, cleanup correctness, latency, and cost. Run the cmux/Herdr visual test separately; otherwise a pane-launch
failure can be incorrectly attributed to model quality.

### 3. Selection rule

- **Need reliability-first review orchestration:** keep `nicobailon/pi-subagents` pinned and validate its persisted
  artifacts.
- **Need direct cmux/Herdr child panes:** trial `edxeth/pi-subagents` only through an adapter that makes session/report
  artifacts authoritative over pane state.
- **Need better cross-provider independence, access policy, replay, and workflow gates more than visible panes:** pilot
  `pi-native-subagents`.
- **Need a smaller native Pi task runner with fewer process/mux failure modes:** pilot `pi-task`.
- **Need only a simple durable lifecycle:** use `pi-vigil`, but add the missing workflow policy in project skills rather
  than expecting the extension to supply it.

## Evidence gaps

There is no independent benchmark comparing the candidates' model quality, completion rates, or hallucination rates. The
reliability judgments above are based on first-party architecture, failure handling, tests, release/install surfaces,
and stated limitations. The A/B trial is necessary before replacing the selected extension in production.
