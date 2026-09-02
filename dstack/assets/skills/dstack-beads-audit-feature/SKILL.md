---
dstack-managed: true
name: dstack-beads-audit-feature
description: "Audit approved intent, implementation, and current documentation for drift using deterministic evidence."
---

# Audit feature

The audit skill makes semantic judgments. dStack gathers facts; Beads owns all resulting work, blockers, gates, and
completion.

## Claim the native audit

Claim the audit only when Beads exposes it:

```bash
bd ready --parent <feature-root> --label dstack:step:audit --claim --json
```

If it is blocked, report the native blockers. Do not override fan-in or infer readiness from Git.

Collect deterministic evidence:

```bash
dstack ctl audit evidence <feature-root> --run-validation
```

Read targeted Beads history, source, or documentation only where the evidence identifies a material question. Compare:

- approved plan and recorded decisions;
- implementation tasks and dependencies;
- task acceptance criteria and reachable commits;
- observable code and test behavior;
- end-user, developer, and future-agent documentation;
- current documentation against historical rationale where relevant.

Classify each supported finding as implementation drift, documentation drift, plan drift, missing decision record, or
ambiguous authority. Cite repository paths and Beads IDs.

## Clear drift

For a clear defect:

1. reopen or release the audit to `open` and unassigned;
2. create an ordinary implementation task under the implementation epic;
3. give it acceptance criteria, commit labels, and the three-audience documentation matrix;
4. add a native blocker from the audit to the remediation task; and
5. return `/implement <feature-root>`.

Do not create an audit packet, correction ledger, or Markdown status file.

## Ambiguous authority

When it is unclear whether approved intent, code, or documentation is correct:

1. record the exact contradiction in a Beads comment;
2. release the audit claim;
3. create a native human gate blocking the audit and parent it to the feature root for discoverability; and
4. ask the user one targeted question.

After the answer, create or update a decision Bead, resolve the gate, and create ordinary remediation work when
required. Never silently choose which source is authoritative.

## Completion

When no material drift remains and validation passes:

1. verify every implementation child is closed;
2. close the implementation epic if it remains open;
3. close the audit task with an evidence-based reason; and
4. close the molecule root if the supported Beads version does not close it automatically.

Return the validation performed, decisions recorded, remediation created, and final native Beads status. Do not create a
mandatory reconciliation document or post-completion bookkeeping commit.
