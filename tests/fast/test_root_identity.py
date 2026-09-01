from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from dstack import delivery as dstack_delivery
from dstack import core as dstacklib
from dstack.core import DstackError

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


@pytest.mark.parametrize(
    ("resolver", "issue", "message"),
    [
        (dstacklib.resolve_feature, feature("nested", parent="root"), "not a feature workflow root"),
        (
            dstacklib.resolve_feature,
            feature("nested", labels=["workflow:feature", "feature:demo", "audit:other"]),
            "not a feature workflow root",
        ),
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


def test_metadata_only_historical_root_is_not_a_controller_input(tmp_path: Path) -> None:
    legacy = {
        "id": "legacy",
        "issue_type": "epic",
        "status": "open",
        "metadata": {"feature_slug": "legacy"},
    }
    beads = ScriptedClient(tmp_path, call("show_optional", "legacy", result=legacy))
    with pytest.raises(DstackError, match="not a feature workflow root"):
        dstacklib.resolve_feature(beads, "legacy")
    beads.assert_exhausted()


def test_delivery_exact_nested_workflow_id_is_rejected(tmp_path: Path) -> None:
    nested = feature("nested", parent="root")
    beads = ScriptedClient(tmp_path, call("show_optional", "nested", result=nested))
    with pytest.raises(DstackError, match="not a feature workflow root"):
        dstack_delivery._delivery_root(beads, "nested")
    beads.assert_exhausted()
