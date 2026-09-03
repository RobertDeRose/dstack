# Getting started

Install dStack as a Python tool and install the four targeted agent skills:

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install_skills
```

Initialize Beads directly and install the versioned dStack formula:

```bash
bd init --quiet --non-interactive
dstack ctl formula install
dstack ctl formula check
```

dStack never initializes Beads and never uses stealth mode. Start a feature with `/plan-feature`. Resume work from
native Beads output; the skills do not require a Markdown task list.
