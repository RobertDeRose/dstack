from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dstack-beads-core/scripts"))
import dstack_compat
import dstack_delivery
import dstacklib
from dstacklib import DstackError

from scripted import ScriptedClient, call


def feature(issue_id: str, *, parent: str | None = None, slug: str = "demo", labels: list[str] | None = None, **extra):
    return {
        "id": issue_id,
        "issue_type": extra.pop("issue_type", "epic"),
        "status": extra.pop("status", "open"),
        "labels": labels if labels is not None else ["workflow:feature", f"feature:{slug}"],
        **({"parent": parent} if parent else {}),
        **extra,
    }


def alignment(issue_id: str, *, parent: str | None = None, slug: str = "audit", **extra):
    return {
        "id": issue_id,
        "issue_type": extra.pop("issue_type", "molecule"),
        "status": extra.pop("status", "open"),
        "labels": ["workflow:project-alignment", f"audit:{slug}"],
        **({"parent": parent} if parent else {}),
        **extra,
    }


@pytest.mark.parametrize(
    ("resolver", "issue", "message"),
    [
        (dstacklib.resolve_feature, feature("nested", parent="root"), "not a feature workflow root"),
        (
            dstacklib.resolve_feature,
            feature("nested", labels=["workflow:feature", "feature:demo", "audit:other"]),
            "not a feature workflow root",
        ),
        (dstacklib.resolve_alignment, alignment("nested", parent="root"), "not a project-alignment workflow root"),
    ],
)
def test_exact_nested_workflow_ids_are_rejected(tmp_path: Path, resolver, issue: dict, message: str) -> None:
    beads = ScriptedClient(tmp_path, call("show_optional", "nested", result=issue))
    with pytest.raises(DstackError, match=message):
        resolver(beads, "nested")
    beads.assert_exhausted()


def test_root_lists_require_parentless_unambiguous_identity(tmp_path: Path) -> None:
    valid = feature("valid")
    planned = feature("planned", labels=["dstack:feature-idea", "feature:planned"])
    inventory = [
        valid,
        planned,
        feature("nested", parent="valid"),
        feature("missing-identity", labels=["workflow:feature"]),
        feature("competing", labels=["workflow:feature", "feature:a", "feature:b"]),
        feature("cross-kind", labels=["workflow:feature", "feature:demo", "audit:other"]),
    ]
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=inventory))
    assert [item["id"] for item in dstacklib.feature_roots(beads)] == ["valid", "planned"]
    beads.assert_exhausted()


def test_alignment_roots_ignore_nested_pollution(tmp_path: Path) -> None:
    root = alignment("root")
    nested = alignment("nested", parent="root")
    cross_kind = alignment(
        "cross-kind",
        labels=["workflow:project-alignment", "audit:audit", "dstack:feature-idea"],
    )
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=[root, nested, cross_kind]))
    assert dstacklib.alignment_roots(beads) == [root]
    beads.assert_exhausted()


def test_adoption_accepts_parentless_metadata_only_legacy_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {
        "id": "legacy",
        "issue_type": "epic",
        "status": "open",
        "metadata": {"feature_slug": "legacy"},
    }
    strict = ScriptedClient(tmp_path, call("show_optional", "legacy", result=legacy))
    with pytest.raises(DstackError, match="not a feature workflow root"):
        dstacklib.resolve_feature(strict, "legacy")
    strict.assert_exhausted()

    beads = ScriptedClient(
        tmp_path,
        call("show_optional", "legacy", result=legacy),
        call("children", "legacy", result=[]),
    )
    monkeypatch.setattr(dstack_compat, "client_for", lambda root: beads)
    monkeypatch.setattr(dstack_compat, "descendants", lambda *args: [])
    output = []
    monkeypatch.setattr(dstack_compat, "emit", output.append)

    args = type("Args", (), {"root": tmp_path, "selector": "legacy"})()
    assert dstack_compat.cmd_adopt_inspect(args) == 0
    assert output[0]["legacy_root"] == legacy
    beads.assert_exhausted()


def test_adoption_replacement_lookup_ignores_nested_pollution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = feature("root")
    nested = feature("nested", parent="root")
    beads = ScriptedClient(tmp_path, call("list", all_statuses=True, result=[root, nested]))
    monkeypatch.setattr(dstack_compat, "feature_context", lambda client, selector: {"current": True})
    assert dstack_compat.current_feature_for_slug(beads, "demo", exclude_id="legacy") == root
    beads.assert_exhausted()


def test_delivery_exact_nested_workflow_id_is_rejected(tmp_path: Path) -> None:
    nested = feature("nested", parent="root")
    beads = ScriptedClient(tmp_path, call("show_optional", "nested", result=nested))
    with pytest.raises(DstackError, match="not a workflow root"):
        dstack_delivery._delivery_root(beads, "nested")
    beads.assert_exhausted()
