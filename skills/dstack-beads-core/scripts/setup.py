#!/usr/bin/env python3
"""Install, validate, and explicitly repair dstack's Beads integration."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from dstack_docs import initialize_docs, validate_docs
from dstacklib import (
    ALIGNMENT_STEPS,
    FEATURE_STEPS,
    BeadsClient,
    DstackError,
    as_items,
    canonical_feature_design_path,
    feature_slug,
    git_root,
    has_label,
    issue_labels,
    issue_metadata,
    parse_json,
    root_metadata_value,
    run,
)

FORMULA_NAMES = ("dstack-feature", "dstack-project-alignment")
PREFLIGHT_VARS: dict[str, dict[str, str]] = {
    "dstack-feature": {
        "feature_title": "Dstack Formula Preflight",
        "feature_slug": "dstack-formula-preflight",
        "design_path": "docs/src/features/dstack-formula-preflight/design.md",
    },
    "dstack-project-alignment": {
        "audit_title": "Dstack Alignment Preflight",
        "audit_slug": "dstack-alignment-preflight",
        "scope": "formula validation",
    },
}


class SetupError(DstackError):
    """Raised when setup or repair cannot proceed safely."""


def package_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ensure_beads(root: Path, *, initialize: bool) -> None:
    if (root / ".beads").is_dir():
        return
    if not initialize:
        raise SetupError("Beads is not initialized; rerun setup after authorization")
    run(
        [
            "bd",
            "init",
            "--quiet",
            "--skip-agents",
            "--skip-hooks",
            "--non-interactive",
        ],
        cwd=root,
    )
    if not (root / ".beads").is_dir():
        raise SetupError("bd init completed without creating .beads")


def formula_vars(name: str) -> list[str]:
    result: list[str] = []
    for key, value in PREFLIGHT_VARS[name].items():
        result.extend(["--var", f"{key}={value}"])
    return result


def step_map(formula: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = formula.get("steps")
    if not isinstance(raw, list):
        raise SetupError("formula steps must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise SetupError("formula contains an invalid step")
        result[str(item["id"])] = item
    return result


def validate_formula_contract(name: str, formula: Mapping[str, Any]) -> None:
    steps = step_map(formula)
    if name == "dstack-feature":
        expected = {
            "specification": ("task", FEATURE_STEPS["specification"]),
            "approval": ("task", FEATURE_STEPS["approval"]),
            "implementation": ("epic", FEATURE_STEPS["implementation"]),
            "closeout": ("task", FEATURE_STEPS["closeout"]),
        }
        planning, approval, workstream, terminal = (
            "specification",
            "approval",
            "implementation",
            "closeout",
        )
    elif name == "dstack-project-alignment":
        expected = {
            "analysis": ("task", ALIGNMENT_STEPS["analysis"]),
            "approval": ("task", ALIGNMENT_STEPS["approval"]),
            "corrections": ("epic", ALIGNMENT_STEPS["corrections"]),
            "landing": ("task", ALIGNMENT_STEPS["landing"]),
        }
        planning, approval, workstream, terminal = (
            "analysis",
            "approval",
            "corrections",
            "landing",
        )
    else:
        raise SetupError(f"unknown dstack formula: {name}")

    if set(steps) != set(expected):
        raise SetupError(f"{name} must contain exactly {sorted(expected)}")
    for step_id, (expected_type, expected_label) in expected.items():
        step = steps[step_id]
        actual_type = str(step.get("type") or "task")
        if actual_type != expected_type:
            raise SetupError(f"{name} step {step_id} must be {expected_type}, got {actual_type}")
        if step.get("labels") != [expected_label]:
            raise SetupError(f"{name} step {step_id} must have only label {expected_label}")
        if step.get("metadata"):
            raise SetupError(f"{name} step {step_id} must not duplicate identity in metadata")
        encoded = json.dumps(step, sort_keys=True)
        labels = json.dumps(step.get("labels", []))
        metadata = json.dumps(step.get("metadata", {}))
        if "{{" in labels or "{{" in metadata:
            raise SetupError(f"{name} step {step_id} templates labels or metadata")
        if not encoded:
            raise SetupError("invalid formula step")

    if steps[approval].get("needs") != [planning]:
        raise SetupError(f"{name} approval must depend only on {planning}")
    gate = steps[approval].get("gate")
    if not isinstance(gate, dict) or gate.get("type") != "human":
        raise SetupError(f"{name} approval must carry a human gate")
    if steps[workstream].get("needs") or steps[workstream].get("gate"):
        raise SetupError(f"{name} workstream must remain an ungated epic container")
    if steps[terminal].get("needs") != [approval]:
        raise SetupError(f"{name} terminal must depend on approval")
    if steps[terminal].get("waits_for") != f"children-of({workstream})":
        raise SetupError(f"{name} terminal must use native dynamic child fan-in")


def validate_formula(
    root: Path,
    name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    result = run(["bd", "formula", "show", name, "--json"], cwd=root, env=env)
    payload = parse_json(result.stdout, context=f"bd formula show {name}")
    if not isinstance(payload, dict):
        raise SetupError(f"bd formula show returned a non-object for {name}")
    validate_formula_contract(name, payload)
    run(["bd", "mol", "seed", name, *formula_vars(name)], cwd=root, env=env)
    return payload


def validate_bundle(source_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="dstack-preflight-") as raw:
        scratch = Path(raw)
        run(["git", "init", "-q"], cwd=scratch)
        run(
            [
                "bd",
                "init",
                "--quiet",
                "--skip-agents",
                "--skip-hooks",
                "--non-interactive",
            ],
            cwd=scratch,
        )
        formula_dir = scratch / ".beads" / "formulas"
        formula_dir.mkdir(parents=True, exist_ok=True)
        for name in FORMULA_NAMES:
            shutil.copyfile(
                source_dir / f"{name}.formula.toml",
                formula_dir / f"{name}.formula.toml",
            )
        for name in FORMULA_NAMES:
            validate_formula(scratch, name)
            result = run(
                ["bd", "mol", "pour", name, *formula_vars(name), "--json"],
                cwd=scratch,
            )
            payload = parse_json(result.stdout, context=f"bd mol pour {name}")
            if not isinstance(payload, dict) or not (
                payload.get("root_id") or payload.get("new_epic_id")
            ):
                raise SetupError(f"isolated pour returned no root for {name}")


def copy_formula(source: Path, destination: Path, *, force: bool) -> str:
    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            return "unchanged"
        if not force:
            raise SetupError(
                f"formula differs: {destination}; rerun /setup-project --force"
            )
        state = "updated"
    else:
        state = "installed"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return state


def install(root_arg: Path, *, initialize: bool, force: bool) -> dict[str, Any]:
    root = git_root(root_arg)
    ensure_beads(root, initialize=initialize)
    client = BeadsClient(root)
    version = client.check_version()
    client.check_capabilities()
    source_dir = package_root() / "formulas"
    validate_bundle(source_dir)

    # Non-forced setup is deliberately strict. A forced setup is the explicit
    # compatibility boundary and lets repair normalize legacy documentation
    # before the completed book is validated.
    if force:
        require_mdbook()
        documentation_payload: dict[str, Any] = {}
        interaction_policy: dict[str, bool] = {}
    else:
        documentation_payload = initialize_docs(root)
        interaction_policy = ensure_interaction_log_policy(root)

    installed: dict[str, str] = {}
    for name in FORMULA_NAMES:
        installed[name] = copy_formula(
            source_dir / f"{name}.formula.toml",
            root / ".beads" / "formulas" / f"{name}.formula.toml",
            force=force,
        )
        validate_formula(root, name)
    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": installed,
        "preflight": "isolated-formula-pour",
        **documentation_payload,
        **interaction_policy,
    }


def doctor(root_arg: Path) -> dict[str, Any]:
    root = git_root(root_arg)
    if not (root / ".beads").is_dir():
        raise SetupError("Beads is not initialized")
    client = BeadsClient(root)
    version = client.check_version()
    client.check_capabilities()
    source_dir = package_root() / "formulas"
    documentation = validate_docs(root)
    statuses: dict[str, str] = {}
    for name in FORMULA_NAMES:
        installed = root / ".beads" / "formulas" / f"{name}.formula.toml"
        source = source_dir / f"{name}.formula.toml"
        if not installed.is_file():
            raise SetupError(f"missing installed formula: {installed}")
        if installed.read_bytes() != source.read_bytes():
            raise SetupError(
                f"installed formula differs from dstack package: {installed}"
            )
        validate_formula(root, name)
        statuses[name] = "available"
    return {
        "status": "ok",
        "root": str(root),
        "beads_version": version,
        "formulas": statuses,
        "documentation": documentation,
    }


def all_issue_inventory(client: BeadsClient) -> list[dict[str, Any]]:
    result = run(
        [
            "bd",
            "list",
            "--all",
            "--include-templates",
            "--include-gates",
            "--limit",
            "0",
            "--json",
        ],
        cwd=client.root,
    )
    return as_items(parse_json(result.stdout, context="bd list repair inventory"))


def legacy_template_artifacts(client: BeadsClient) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for summary in all_issue_inventory(client):
        issue_id = str(summary.get("id") or "")
        if not any(issue_id == name or issue_id.startswith(f"{name}.") for name in FORMULA_NAMES):
            continue
        issue = client.show(issue_id)
        if issue.get("is_template") is not True:
            raise SetupError(f"reserved dstack template ID is used by non-template issue {issue_id}")
        result.append(issue)
    return result


def add_gitignore_line(path: Path, line: str, *, header: str | None = None) -> bool:
    existing = path.read_text().splitlines() if path.exists() else []
    if line in existing:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if existing and existing[-1] != "":
            handle.write("\n")
        if header and header not in existing:
            handle.write(header + "\n")
        handle.write(line + "\n")
    return True


def ensure_interaction_log_policy(root: Path) -> dict[str, bool]:
    """Keep the Beads audit log local under dStack's Git-decoupling policy."""

    ignore_changed = add_gitignore_line(
        root / ".beads" / ".gitignore",
        "interactions.jsonl",
        header="# dStack: local Beads audit state (not repository history)",
    )
    was_tracked = tracked(root, ".beads/interactions.jsonl")
    if was_tracked:
        run(
            [
                "git",
                "rm",
                "--cached",
                "--force",
                "--ignore-unmatch",
                "--",
                ".beads/interactions.jsonl",
            ],
            cwd=root,
        )
    return {
        "interaction_log_untracked": was_tracked,
        "beads_gitignore_changed": ignore_changed,
    }


def tracked(root: Path, path: str) -> bool:
    return (
        run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=root,
            check=False,
        ).returncode
        == 0
    )


def normalize_current_features(client: BeadsClient, *, force: bool) -> list[str]:
    changed: list[str] = []
    roots = client.list(all_statuses=True, labels=["workflow:feature"])
    for root in roots:
        root_id = str(root.get("id") or "")
        if not root_id:
            continue
        slug = feature_slug(root)
        base = root_metadata_value(root, "dstack.base_branch", "base_branch")
        design = root_metadata_value(root, "dstack.design_path", "design_path")
        root_args: list[str] = []
        root_metadata = issue_metadata(root)
        if base and not root_metadata.get("dstack.base_branch"):
            root_args.extend(["--set-metadata", f"dstack.base_branch={base}"])
        if slug:
            canonical_design = canonical_feature_design_path(slug)
            if design != canonical_design or not root_metadata.get("dstack.design_path"):
                root_args.extend(
                    ["--set-metadata", f"dstack.design_path={canonical_design}"]
                )
        for key in ("feature_slug", "base_branch", "branch", "worktree_path", "adopted_from"):
            if key in issue_metadata(root):
                root_args.extend(["--unset-metadata", key])
        for label in issue_labels(root):
            if label == "dstack:delivery-ready":
                root_args.extend(["--remove-label", label])
        if root_args:
            if not force:
                changed.append(root_id)
            else:
                client.update(root_id, *root_args)
                changed.append(root_id)

        children = client.children(root_id)
        for child in children:
            child_id = str(child.get("id") or "")
            child_args: list[str] = []
            metadata = issue_metadata(child)
            for key in ("dstack_step", "base_branch", "design_path"):
                if key in metadata:
                    child_args.extend(["--unset-metadata", key])
            for label in issue_labels(child):
                if label == "feature:{{feature_slug}}" or (slug and label == f"feature:{slug}"):
                    child_args.extend(["--remove-label", label])
            if child_args:
                if force:
                    client.update(child_id, *child_args)
                changed.append(child_id)

        implementation = next(
            (child for child in children if has_label(child, FEATURE_STEPS["implementation"])),
            None,
        )
        if implementation:
            for task in client.children(str(implementation["id"])):
                task_args: list[str] = []
                for label in issue_labels(task):
                    if label == "feature:{{feature_slug}}" or (slug and label == f"feature:{slug}"):
                        task_args.extend(["--remove-label", label])
                if task_args:
                    if force:
                        client.update(str(task["id"]), *task_args)
                    changed.append(str(task["id"]))
    return sorted(set(changed))


def normalize_current_alignments(client: BeadsClient, *, force: bool) -> list[str]:
    changed: list[str] = []
    roots = client.list(all_statuses=True, labels=["workflow:project-alignment"])
    for root in roots:
        root_id = str(root.get("id") or "")
        if not root_id:
            continue
        root_args: list[str] = []
        target = root_metadata_value(root, "dstack.target_branch", "target_branch")
        scope = root_metadata_value(root, "dstack.scope", "scope")
        root_metadata = issue_metadata(root)
        if target and not root_metadata.get("dstack.target_branch"):
            root_args.extend(["--set-metadata", f"dstack.target_branch={target}"])
        if scope and not root_metadata.get("dstack.scope"):
            root_args.extend(["--set-metadata", f"dstack.scope={scope}"])
        for key in ("audit_slug", "target_branch", "branch", "worktree_path"):
            if key in issue_metadata(root):
                root_args.extend(["--unset-metadata", key])
        for label in issue_labels(root):
            if label == "dstack:delivery-ready":
                root_args.extend(["--remove-label", label])
        if root_args:
            if force:
                client.update(root_id, *root_args)
            changed.append(root_id)

        for child in client.children(root_id):
            child_args: list[str] = []
            for key in ("dstack_step", "target_branch", "scope"):
                if key in issue_metadata(child):
                    child_args.extend(["--unset-metadata", key])
            for label in issue_labels(child):
                if label.startswith("audit:"):
                    child_args.extend(["--remove-label", label])
            if child_args:
                if force:
                    client.update(str(child["id"]), *child_args)
                changed.append(str(child["id"]))
    return sorted(set(changed))


def repair_legacy(root_arg: Path, *, force: bool) -> dict[str, Any]:
    root = git_root(root_arg)
    client = BeadsClient(root)
    client.check_version()
    templates = legacy_template_artifacts(client)
    normalized = sorted(
        set(normalize_current_features(client, force=force)) | set(normalize_current_alignments(client, force=force))
    )
    interaction_tracked = tracked(root, ".beads/interactions.jsonl")
    beads_ignore = root / ".beads" / ".gitignore"
    ignore_lines = beads_ignore.read_text().splitlines() if beads_ignore.exists() else []
    interaction_ignore_missing = "interactions.jsonl" not in ignore_lines

    if (templates or normalized or interaction_tracked or interaction_ignore_missing) and not force:
        return {
            "status": "repair-required",
            "template_artifacts": [item["id"] for item in templates],
            "molecule_items_to_normalize": normalized,
            "interaction_log_tracked": interaction_tracked,
            "interaction_log_ignore_missing": interaction_ignore_missing,
        }

    removed: list[str] = []
    if templates:
        ids = sorted(str(item["id"]) for item in templates)
        run(["bd", "delete", *ids, "--dry-run", "--json"], cwd=root)
        run(["bd", "delete", *ids, "--force", "--json"], cwd=root)
        removed = ids

    interaction_policy = ensure_interaction_log_policy(root)

    return {
        "status": "ok",
        "template_artifacts_removed": removed,
        "molecule_items_normalized": normalized,
        **interaction_policy,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    install_parser = sub.add_parser("install")
    install_parser.add_argument("--root", type=Path, default=Path.cwd())
    install_parser.add_argument("--init", action="store_true")
    install_parser.add_argument("--force", action="store_true")

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--root", type=Path, default=Path.cwd())

    repair_parser = sub.add_parser("repair-legacy")
    repair_parser.add_argument("--root", type=Path, default=Path.cwd())
    repair_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install":
            payload = install(args.root, initialize=args.init, force=args.force)
        elif args.command == "doctor":
            payload = doctor(args.root)
        else:
            payload = repair_legacy(args.root, force=args.force)
    except DstackError as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if payload.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
