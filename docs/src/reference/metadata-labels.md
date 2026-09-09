# Metadata and labels

A feature root carries:

```text
workflow:feature
feature:<slug>
dstack.base_branch=<branch>
```

Formula steps use:

```text
dstack:step:plan
dstack:step:review
dstack:step:approval
dstack:step:implementation
dstack:step:audit
```

The public lifecycle calls the last step the **close step**. `dstack:step:audit` is its stable internal label for
compatibility with existing feature molecules.

Implementation tasks use:

```text
dstack:work:implementation
```

Task notes record delivered repository work as ordered `Implementation:` fragments. Each fragment is one concise line of
no more than 96 characters. dStack preserves technical punctuation, adds the commit bullet marker, and does not wrap the
text. Planned task description/design text is not commit evidence.

Commit type and scope are derived from the feature/task contract rather than separate labels. Legacy labels may remain
on features created by an older workflow version, but new tasks do not require them.

Beads decision issues use the `decision` type, label `decision:<slug>`, and an exact `relates-to` dependency on the
feature root. The formula's human approval gate has await ID `approve-<slug>-plan`. Material ambiguity may create a
separate human gate that directly blocks the close step.

Workflow status, readiness, claims, worktree paths, commit IDs, validation results, and next actions remain in Beads and
Git rather than being copied into dStack metadata.
