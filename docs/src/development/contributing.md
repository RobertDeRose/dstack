# Contributing

dStack is developed internally using dStack itself, but the contribution boundary for other developers is a GitHub pull
request. You do not need to reproduce the maintainer's Beads workflow state to propose a change.

## Submit a change

1. Fork the repository and create a branch for the change, or create a branch directly if you have repository access.
2. Follow [Development setup](setup.md) to install the repository tools and Python environment.
3. Make a focused change and add or update tests and documentation when behavior changes.
4. Run the relevant checks from [Testing and validation](validation.md).
5. Open a [GitHub pull request](https://github.com/RobertDeRose/dstack/pulls) describing the problem, the change, and
   how it was validated.

Pull requests are the review and merge surface for external contributions. Keep the change scoped to the problem being
solved; unrelated cleanup is easier to review as a separate pull request.

## Maintainer workflow

Maintainers use dStack recursively for feature work in this repository:

```text
/plan-feature -> /review-plan -> approval -> /implement -> /close-feature
```

That workflow records the accepted design and implementation work in Beads and publishes completed feature designs into
this documentation. It is the project's internal development process, not an additional requirement for submitting a
pull request.
