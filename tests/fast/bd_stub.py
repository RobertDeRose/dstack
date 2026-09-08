"""Read-only subprocess boundary for CLI tests; native behavior has separate acceptance coverage."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    args = sys.argv[1:]
    data = json.loads(Path(os.environ["DSTACK_TEST_BEADS"]).read_text(encoding="utf-8"))
    with Path(os.environ["DSTACK_TEST_CALLS"]).open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    issues = data["issues"]

    def option(name: str) -> str | None:
        return args[args.index(name) + 1] if name in args else None

    value: Any
    if args == ["--version"]:
        print("bd version 1.2.2 (boundary fixture)")
        return 0
    if args[:1] == ["where"]:
        value = {"path": data["workspace"]}
    elif args[:2] == ["worktree", "list"]:
        value = data["worktrees"]
    elif args[:1] == ["show"]:
        ids = [data.get("aliases", {}).get(arg, arg) for arg in args[1:] if not arg.startswith("--")]
        missing = [issue_id for issue_id in ids if issue_id not in issues]
        if missing:
            print(
                json.dumps({"schema_version": 1, "data": {"error": "issue not found", "code": "not_found"}}),
                file=sys.stderr,
            )
            return 1
        value = []
        for issue_id in ids:
            issue = dict(issues[issue_id])
            issue["comment_count"] = len(issue.get("comments", []))
            if "--include-comments" not in args:
                issue.pop("comments", None)
                issue["comments_omitted"] = True
            else:
                issue.setdefault("comments", [])
            value.append(issue)
    elif args[:1] == ["list"]:
        value = [dict(issue) for issue in issues.values()]
        for flag, field in (("--parent", "parent"), ("--type", "issue_type"), ("--status", "status")):
            selected = option(flag)
            if selected is not None:
                value = [issue for issue in value if issue.get(field) == selected]
        label = option("--label")
        if label:
            value = [issue for issue in value if label in issue.get("labels", [])]
        # List summaries need not hydrate the long fields that bd show supplies.
        value = [
            {
                key: value
                for key, value in issue.items()
                if key not in {"description", "design", "notes", "comments", "dependencies"}
            }
            for issue in value
        ]
    elif args[:1] == ["history"]:
        value = [{"id": args[1], "event": "created"}]
    elif args[:1] == ["ready"]:
        value = data.get("ready", [])
    else:
        raise AssertionError(f"unmodeled native operation: {args}")
    print(json.dumps({"schema_version": 1, "data": value}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
