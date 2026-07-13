#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: S603
"""Resolve a dstack feature epic by number, slug, name, or Beads ID."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


FEATURE_TITLE = re.compile(r"^F(?P<number>[0-9]+)\s*[\u2014\u2013-]\s*(?P<name>.+)$", re.IGNORECASE)
FEATURE_REFERENCE = re.compile(r"^F?(?P<number>[0-9]+)(?:[-:/_\s]+(?P<name>.+))?$", re.IGNORECASE)
OPEN_STATUSES = {"open", "ready"}


def run_json(command: Sequence[str], *, cwd: Path) -> Any:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip())
        message = f"Command failed ({completed.returncode}): {' '.join(command)}"
        if details:
            message += f"\n{details}"
        raise SystemExit(message)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        message = f"Expected JSON from {' '.join(command)}"
        raise SystemExit(message) from exc


def as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): item for key, item in parsed.items()}
    return {}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def issue_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, Mapping):
        candidate = payload.get("issues") or payload.get("items") or payload.get("results")
        values = candidate if isinstance(candidate, list) else []
    else:
        values = []
    return [as_mapping(value) for value in values if isinstance(value, Mapping)]


def feature_identity(issue: Mapping[str, Any]) -> dict[str, Any]:
    metadata = as_mapping(issue.get("metadata"))
    title = str(issue.get("title") or "").strip()
    title_match = FEATURE_TITLE.match(title)

    number_value = metadata.get("feature_number")
    number = str(number_value).strip() if number_value is not None else ""
    if number.casefold().startswith("f"):
        number = number[1:]
    if not number and title_match is not None:
        number = title_match.group("number")
    if number.isdigit():
        number = number.zfill(max(3, len(number)))

    name_value = metadata.get("feature_name")
    name = str(name_value).strip() if name_value is not None else ""
    if not name and title_match is not None:
        name = title_match.group("name").strip()
    if not name:
        name = title

    slug_value = metadata.get("feature_slug")
    slug = str(slug_value).strip() if slug_value is not None else ""
    if not slug:
        slug = slugify(name)

    reference = f"{number}-{slug}" if number and slug else slug or number or title
    status = str(issue.get("status") or "").strip()
    issue_type = str(issue.get("issue_type") or issue.get("type") or "").strip()
    return {
        "id": str(issue.get("id") or "").strip(),
        "title": title,
        "issue_type": issue_type,
        "status": status,
        "priority": issue.get("priority"),
        "feature_number": number,
        "feature_slug": slug,
        "feature_name": name,
        "feature_reference": reference,
        "design_path": metadata.get("design_path"),
        "implemented_path": metadata.get("implemented_path"),
        "base_branch": metadata.get("base_branch"),
        "implementation_repository": metadata.get("implementation_repository"),
        "implementation_path": metadata.get("implementation_path"),
        "workflow_kind": metadata.get("workflow_kind"),
        "metadata": metadata,
    }


def list_features(root: Path, *, ready_only: bool) -> list[dict[str, Any]]:
    if ready_only:
        command = [
            "bd",
            "ready",
            "--type",
            "epic",
            "--label",
            "workflow:feature",
            "--json",
            "--limit",
            "0",
        ]
    else:
        command = [
            "bd",
            "list",
            "--all",
            "--type",
            "epic",
            "--label",
            "workflow:feature",
            "--json",
            "--limit",
            "0",
        ]
    features = [feature_identity(issue) for issue in issue_list(run_json(command, cwd=root))]
    return [feature for feature in features if feature["id"]]


def priority_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "").strip().casefold().removeprefix("p")
    return int(text) if text.isdigit() else 99


def feature_sort_key(feature: Mapping[str, Any]) -> tuple[int, int, str, str]:
    number = str(feature.get("feature_number") or "")
    numeric_number = int(number) if number.isdigit() else 10**12
    return (
        priority_value(feature.get("priority")),
        numeric_number,
        str(feature.get("feature_name") or "").casefold(),
        str(feature.get("id") or ""),
    )


def selector_matches(feature: Mapping[str, Any], selector: str) -> tuple[bool, bool]:
    """Return exact and partial match signals for a human selector."""
    query = selector.strip().casefold()
    if not query:
        return False, False

    issue_id = str(feature.get("id") or "").casefold()
    number = str(feature.get("feature_number") or "").casefold()
    slug = str(feature.get("feature_slug") or "").casefold()
    name = str(feature.get("feature_name") or "").casefold()
    title = str(feature.get("title") or "").casefold()
    reference = str(feature.get("feature_reference") or "").casefold()

    exact_values = {issue_id, number, f"f{number}" if number else "", slug, name, title, reference}
    if query in exact_values:
        return True, True

    reference_match = FEATURE_REFERENCE.match(selector.strip())
    if reference_match is not None:
        query_number = reference_match.group("number").lstrip("0") or "0"
        feature_number = number.lstrip("0") or "0"
        query_name = reference_match.group("name")
        if query_number == feature_number and (not query_name or slugify(query_name) in {slug, slugify(name)}):
            return True, True

    partial_values = (name, title, slug, reference)
    partial = any(query in value for value in partial_values if value)
    return False, partial


def candidate_lines(features: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for feature in sorted(features, key=feature_sort_key):
        reference = feature.get("feature_reference") or feature.get("id")
        lines.append(f"  - {reference}: {feature.get('title')} [{feature.get('id')}]")
    return "\n".join(lines) or "  - none"


def resolve_selector(features: Sequence[dict[str, Any]], selector: str) -> dict[str, Any]:
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for feature in features:
        is_exact, is_partial = selector_matches(feature, selector)
        if is_exact:
            exact.append(feature)
        elif is_partial:
            partial.append(feature)

    matches = exact or partial
    if len(matches) == 1:
        return matches[0]
    if not matches:
        message = f"No feature epic matches {selector!r}. Available features:\n{candidate_lines(features)}"
        raise SystemExit(message)
    message = f"Feature selector {selector!r} is ambiguous. Matching features:\n{candidate_lines(matches)}"
    raise SystemExit(message)


def next_feature(root: Path) -> dict[str, Any]:
    ready = list_features(root, ready_only=True)
    eligible = [
        feature for feature in ready if not feature["status"] or str(feature["status"]).casefold() in OPEN_STATUSES
    ]
    if not eligible:
        all_features = list_features(root, ready_only=False)
        raise SystemExit(
            "No ready feature epic is available. Open feature epics:\n"
            + candidate_lines(
                [
                    feature
                    for feature in all_features
                    if not feature["status"] or str(feature["status"]).casefold() in OPEN_STATUSES
                ]
            )
        )
    return min(eligible, key=feature_sort_key)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("selector", nargs="?", help="Feature ID, F-number, <number>-<slug>, slug, or name.")
    group.add_argument("--next", action="store_true", help="Select the next ready open feature epic.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository containing Beads state.")
    parser.add_argument("--json", action="store_true", help="Print the complete resolved feature as JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.next:
        feature = next_feature(root)
    else:
        selector = args.selector
        if selector is None:
            message = "Feature selector is required when --next is not used"
            raise AssertionError(message)
        feature = resolve_selector(list_features(root, ready_only=False), selector)
    feature["recommended_command"] = f"/start-feature {feature['feature_reference']}"
    if args.json:
        print(json.dumps(feature, indent=2, sort_keys=True))
    else:
        print(feature["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
