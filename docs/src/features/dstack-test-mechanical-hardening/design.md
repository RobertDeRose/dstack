# Feature design

## Goal

Reduce duplicated Beads semantics in tests and make the controller easier to understand, validate, and operate without
changing dStack's authority model or public command entry point. Real Beads remains the release authority for lifecycle
behavior; fast tests exercise only controller decisions and protocol handling.

## User-visible behavior

- `dstackctl.py` remains the single executable entry point with the existing command names, selectors, and JSON
  envelope. Mutations return touched native objects; inspect commands return full current dashboards.
- Every public command and flag has concise help that explains its mechanics, required inputs, failure boundaries, and
  at least one useful example where the operation is not self-explanatory.
- Real-Beads acceptance scenarios run against isolated repositories in JSON-envelope mode and fail when the selected
  `bd` binary is unavailable. Required CI jobs run each real scenario separately from the fast suite.
- Fast tests use ordered, immutable call/response snapshots. They do not calculate readiness, gates, dependency fan-in,
  ownership, or lifecycle transitions.
- Repeated read-heavy controller operations use bounded subprocess work within one invocation. A write invalidates any
  request-local read cache; no cache or command history persists outside the process.
- A complete isolated dogfood run proves the plan/start/review/implement/close path using only native Beads and Git
  state. It leaves no dStack state file, packet, ledger, or other external workflow artifact.

## Non-goals

- No second Beads implementation, workflow database, packet format, scheduler, ownership ledger, Git-SHA mapping, or
  persistent cache.
- No new public lifecycle command, plugin system, dependency-injection framework, third-party dependency, or
  coverage-percentage gate.
- No semantic classification of test fixtures and no replacement of Beads readiness, gate, dependency, ownership, or
  completion semantics with Python.
- No network-dependent GitHub test suite. The external PR boundary is exercised through native `gh:pr` gate records and
  isolated Git refs; GitHub itself remains the external provider's responsibility.
- No removal of compatibility behavior until supported repositories are proven not to use it. Compatibility is isolated
  explicitly when removal is not yet justified.

## Existing patterns and reuse

- Reuse `dstackctl.py` as the only public executable and `dstacklib.py` as the standard-library adapter for Beads JSON
  envelopes, Git primitives, worktrees, and stateless errors.
- Reuse the existing `BeadsClient` and command-handler boundaries with a small ordered response harness rather than
  adding fake state behavior.
- Use two isolated real-Beads scenarios: one native contract and one complete dStack feature smoke journey.
- Require `bd` on `PATH` and fail acceptance during session preflight when it is unavailable.
- Reuse `argparse`, `subprocess.run` with argument lists, `git log`, and native Beads commands. No new dependency is
  needed.

## Design

### Fast controller boundary

Fast tests call controller handlers in-process with ordered Beads call/response snapshots. Adapter tests replace only
the native command runner to verify exact arguments, JSON parsing, cache invalidation, and failures. The harness has no
lifecycle state and unsupported calls fail loudly.

Tests that need readiness, ownership, gates, fan-in, or supersession use the real `bd` boundary. Tests for controller
validation, command construction, Git policy, and failure propagation use declared snapshots and real temporary Git
repositories.

### Real-Beads acceptance boundary

The isolated real-Beads harness contains two focused scenarios:

- a native contract covering both formula shapes and pours, gates, readiness, claims, ownership, child fan-in,
  supersession, and worktrees; and
- one complete feature journey covering full setup, specification approval, Git-backed implementation, closeout, and
  delivery.

The harness requires `bd` on `PATH`; absence fails the session before test collection. Each scenario creates a temporary
Git/Beads repository and never uses the project's live workflow database. CI installs the locked Beads version through
mise and runs the scenarios as separate required jobs.

### Internal controller boundaries

Keep `skills/dstack-beads-core/scripts/dstackctl.py` as a thin executable wrapper that parses arguments and translates
`DstackError` into the existing exit/JSON behavior. Move handlers and command-specific policy into a small
standard-library package beside it with these responsibility boundaries:

- feature lifecycle and feature views;
- project-alignment lifecycle and views;
- evidence, documentation, and delivery operations;
- explicit compatibility/adoption and setup-repair operations; and
- shared command helpers used by those handlers.

`dstacklib.py` remains the shared native Beads/Git adapter used by the wrapper, setup, and command modules. Imports are
ordinary Python modules; there is no plugin registry or dependency-injection layer. Existing public functions are
replaced only after their callers and JSON/error behavior have compatibility coverage.

### Help contract

Give the top-level parser, each command group, each public subcommand, and each flag a concise description. Help text
describes whether an operation reads, claims, mutates Beads, mutates Git, requires a worktree, or may fail closed. Tests
enumerate the public parser paths and verify that help is available, contains the required positional/flag explanation,
and does not execute the operation. Tests avoid exact full-output snapshots so wording can improve without turning help
into a brittle API.

### Bounded read work

Make read caching request-local to one `BeadsClient`/controller invocation. Cache only immutable reads such as the
current issue inventory, children, and capability-independent views; clear the cache after every native Beads write or
other operation that can change Beads state. Prefer one inventory/read pass for relationship-heavy views over repeated
per-child `show` calls. Do not serialize cache contents or preserve them between invocations.

Change reachable footer auditing to parse commit subjects, bodies, and changed paths from one Git log invocation rather
than launching one Git process per commit. Keep the current reachable-history semantics, unknown-footer rejection,
multiple-footer support, and rewrite safety unchanged. Add command-count tests with stable upper bounds and explicit
cache-invalidation tests; do not assert wall-clock timing.

### Compatibility and dogfood

Keep compatibility operations behind their explicit commands and in a separate module. Preserve their current public
behavior while documenting the eligibility rule for eventual retirement: when supported repositories contain no active
legacy workflow, the compatibility module may be removed in a later reviewed change. Normal feature, alignment,
evidence, and delivery paths must not run repair or migration logic.

The dogfood scenario runs the complete lifecycle in a temporary repository with real Beads when required. It asserts
that all durable outcomes are represented by Beads and Git, that the candidate can be delivered through the existing
controller, and that no dStack-specific state file, packet, ledger, or tracked runtime artifact appears. Any
observations are test assertions or durable review evidence, never a second workflow record.

### Implementation slices

The work is divided into bounded slices so the fake migration, real acceptance, controller split, help contract, and
subprocess reduction can be reviewed independently. A final integration slice reconciles compatibility isolation, help
coverage, command-count behavior, and the complete dogfood scenario without changing the public lifecycle surface.

## Failure / security / compatibility behavior

- A missing required real `bd`, invalid explicit binary, malformed canned response, unexpected fake command, or injected
  subprocess error fails with a useful nonzero result; no Beads or Git transition is inferred after failure.
- The fake never executes scenario content. It reads test-owned data as JSON and invokes no shell command from that
  data. Production subprocess calls continue to use argument arrays, not shell interpolation.
- Request-local caches are cleared before or after every state-changing Beads operation so stale ownership, gate,
  dependency, and completion data cannot influence a later decision in the same invocation.
- Real-Beads failures remain visible at the native boundary. The controller does not convert a fake success into release
  evidence, and missing required integration prerequisites fail closed.
- Public command names, selectors, JSON envelope handling, successful fields, native close reasons, and exit-code
  boundaries remain compatible. New help text and additive diagnostic fields do not require callers to parse private
  implementation details.
- Compatibility code remains opt-in and cannot rewrite historical workflow state during ordinary commands. Temporary
  test repositories and recorder files are isolated outside the project candidate.
- No secret or Git/Beads commit identity is written to a persistent test protocol log; recorder paths are temporary and
  test-controlled.

## Validation strategy

- Write behavior-first tests for the protocol stub: canned success, argument recording, injected failure, malformed
  response, and unsupported command.
- Run the focused controller/package tests against the stub and verify they no longer depend on fake readiness, gate,
  ownership, or dependency semantics.
- Run real-Beads scenarios in JSON-envelope mode when `bd` is available, with a required-binary mode for release
  validation. Cover every listed native lifecycle and delivery boundary, including failure recovery and concurrent
  claims.
- Exercise every public `--help` path and assert useful flag/mechanics text without exact-output snapshots.
- Measure bounded subprocess calls for repeated views and footer audits, verify writes invalidate reads, and confirm no
  cache files are created.
- Run the isolated end-to-end dogfood scenario and assert no external workflow state or tracked runtime Beads files are
  produced.
- Run Python compilation, focused tests, the full repository suite, formula and setup checks, real-Beads integration
  where available/required, `git diff --check`, Git object validation, and the documentation policy guard.

## Documentation impact

- **End user/operator:** update `docs/src/development/tooling.md` and the existing workflow reference with the
  real-Beads prerequisite/required mode, useful help behavior, and the distinction between fast protocol tests and
  release acceptance. No new workflow-state document is needed.
- **Developer/reviewer:** update `docs/src/architecture/index.md` and testing guidance with the controller module
  boundaries, fake-versus-real authority rule, request-local cache ceiling, compatibility isolation, and command-count
  regression expectations.
- **Future agent/auditor:** retain this design, the real-Beads scenarios, the protocol-contract tests, and the dogfood
  assertions as durable evidence that lifecycle semantics are not duplicated in a fake and that the public controller
  remains stateless and compatible.
