# Getting started

Install dStack as a Python tool, install the targeted agent skills, and install the native Beads formula in the project:

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install_skills
dstack ctl infra install
```

Start a feature with `/plan-feature`. Resume work from native Beads output; the skills do not require a Markdown task
list.
