# Development setup

Clone the repository and enter the checkout:

```bash
git clone https://github.com/RobertDeRose/dstack.git
cd dstack
```

Install the development tools declared by `mise.toml` and synchronize the Python development environment:

```bash
mise install
uv sync --dev --locked
```

The repository currently targets Python 3.14. mise installs the configured Python version together with Beads, hk,
mdBook, Ruff, ty, rumdl, and the other command-line tools used by the project.

List the repository tasks with:

```bash
mise tasks ls
```

If hk is not already enabled globally on your machine, install this repository's Git hooks with:

```bash
hk install
```

See [Repository tooling](tooling.md) for how the repository uses these tools, then run the checks in
[Testing and validation](validation.md) before opening a pull request.
