---
dstack-managed: true
name: dstack-audit-project
description: "Audit current project behavior and documentation, then plan bounded remediation through the normal lifecycle."
disable-model-invocation: true
---

# Audit project

This audits the current repository rather than an existing feature.

## dStack operations

Use these dStack commands when remediation is required:

```bash
dstack init
dstack check formula
dstack check plan --bead <root>
```

Initialization and formula validation must succeed before pouring a new remediation molecule. Run the plan check after
recording the remediation plan and before closing its plan step.

## Assess

Search `bd memories <focused terms> --json` and recall only relevant entries. Inspect current architecture, behavior,
tests, security and operations guidance, and accepted decisions. Run the target repository's documented validation
contract and `bd dep cycles --json` as a project-health check.

Classify supported drift as behavior, documentation, test, security, operational, or decision drift. Ask the user when
authority is material and ambiguous.

If no actionable drift remains, report the evidence and stop without creating a feature.

## Create the remediation plan

Resume an explicitly supplied remediation molecule before considering new work. Otherwise create one normal
`dstack-feature` remediation molecule using `/plan-feature` identity and base-branch rules, then claim only its plan
step. Store the audit scope and evidence in description/comments, observable remediation outcomes in acceptance
criteria, and a publishable six-section design beginning at heading level three.

Resolve material questions, run `dstack check plan --bead <root>`, then close only the plan step. Do not create
implementation tasks, approve scope, or implement remediation during project audit.

Return the remediation root, findings, decisions, and `/review-plan <root>`.
