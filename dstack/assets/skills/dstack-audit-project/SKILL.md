---
dstack-managed: true
name: dstack-audit-project
description: "Audit current project behavior and documentation, then plan bounded remediation through the normal lifecycle."
disable-model-invocation: true
---

# Audit project

Run only when explicitly invoked. This operation audits the current repository rather than an existing feature and does
not create a parallel audit ledger.

## Assess

1. Run `dstack init`, then `dstack check formula` to verify committed policy before any remediation feature is poured.
2. Search `bd memories <focused terms> --json` and recall only relevant entries.
3. Inspect current architecture, behavior, tests, security and operations guidance, and accepted decisions.
4. Run the target repository's documented validation contract.

Current repository documentation and accepted decisions outrank stale memory. Classify supported drift as behavior,
documentation, test, security, operational, or decision drift. Ask the user when authority is material and ambiguous.
Propose memory corrections or retirement, and mutate memory only after explicit approval.

If no actionable drift remains, report the evidence and stop without creating a feature.

## Create the remediation plan

For actionable drift, create one normal `dstack-feature` remediation molecule using the same identity and base-branch
rules as `/plan-feature`. Claim only its plan step. Store:

- the audit scope and observed evidence in the request description and comments;
- observable remediation outcomes in acceptance criteria; and
- a publishable design beginning at heading level three with Goals, User-facing behavior, Implemented design,
  Compatibility and constraints, Validation, and Non-goals.

Resolve material questions before finalizing. Run `dstack check plan --bead <plan>`, then close only the plan step. Do
not create implementation tasks, approve scope, or implement remediation during project audit.

Return the remediation root, findings, decisions, and `/review-plan <root>`.
