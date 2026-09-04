---
dstack-managed: true
name: dstack-audit-feature
description: "Audit approved intent, implementation, and current documentation for drift using deterministic evidence."
---

# Audit feature

Use this skill only when explicitly invoked; that invocation activates the dStack workflow. The audit skill makes
semantic judgments. dStack gathers bounded facts; Beads owns all resulting work, blockers, gates, and completion once
activated.

## Claim the native audit

Claim the audit only when Beads exposes it:

```bash
bd ready --parent <feature-root> --label dstack:step:audit --claim --json
```

If it is blocked, report native blockers. Do not override fan-in or infer readiness from Git.

Collect deterministic summary evidence:

```bash
dstack audit <feature-root>
```

The command runs project and documentation validation and returns a bounded index. Fetch full content only for a
material discrepancy:

```bash
dstack audit <feature-root> --include-plan
dstack audit <feature-root> --include-task <task-id>
dstack audit <feature-root> --include-decision <decision-id>
dstack audit <feature-root> --history-for <bead-id>
```

Compare:

- approved plan and recorded decisions;
- implementation tasks and dependencies;
- task acceptance criteria and reachable commits;
- observable code and test behavior;
- end-user, developer, and future-agent documentation;
- current documentation against accepted decisions and current rationale.

Classify each supported finding as implementation drift, documentation drift, plan drift, missing decision record, or
ambiguous authority. Cite repository paths and Beads IDs.

## Clear drift

For a clear defect:

1. release the audit claim to open and unassigned;
2. create an ordinary task directly under the implementation epic;
3. use `--no-inherit-labels`, acceptance criteria, commit labels, and the three-audience documentation matrix;
4. include `--deps blocked-by:<approval-step>` in the create operation; and
5. verify native waits-for fan-in blocks audit before returning `/implement <feature-root>`.

Do not add a direct task-to-audit blocker. Do not create an audit packet, correction ledger, or Markdown status file.

## Ambiguous authority

When it is unclear whether approved intent, code, or documentation is correct:

1. record the exact contradiction in a Beads comment;
2. release the audit claim;
3. create a native human gate blocking the audit and parent it to the feature root for discoverability; and
4. ask the user one targeted question.

After the answer, create or update a decision Bead, resolve the gate, and create ordinary remediation work when
required. Never silently choose which source is authoritative.

## Completion

When no material drift remains and deterministic checks pass, close the audit task with an evidence-based reason. Then
close the molecule root if it remains open and native Beads reports it as closeable. The fact that the audit was
claimable is the implementation fan-in proof; do not recalculate child completion.

Return validation performed, decisions recorded, remediation created, and final native Beads status. Do not create a
mandatory reconciliation document or post-completion bookkeeping commit.
