"""Focused static boundary types for emitted dStack audit views."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class RootAuditFact(TypedDict):
    id: str
    title: str
    type: str
    status: str
    parent: str | None
    labels: list[str]
    dependencies: list[dict[str, str]]
    close_reason: Any
    description: str
    acceptance: str
    metadata: dict[str, Any]


class DesignAuditFact(TypedDict):
    path: str | None
    pending_sha256: str | None
    approved_sha256: str | None
    current_sha256: str | None
    head_sha256: str | None
    state: str | None
    approved: bool


class EvidenceAuditFact(TypedDict):
    status: str
    reason: NotRequired[str]
    range: NotRequired[str]
    source: NotRequired[str]
    target_ref: NotRequired[str]
    feature_branch: NotRequired[str]
    feature_branch_present: NotRequired[bool]
    worktree_present: NotRequired[bool]
    missing: NotRequired[list[str]]
    no_repository_change: NotRequired[list[str]]
    mapping: NotRequired[dict[str, list[dict[str, Any]]]]
    unexpected_footer_ids: NotRequired[list[str]]


class FeatureAuditView(TypedDict):
    audit_version: int
    kind: str
    classification: str
    root: RootAuditFact
    lifecycle: dict[str, Any]
    design: DesignAuditFact
    work: dict[str, Any]
    git_evidence: EvidenceAuditFact
    documentation: dict[str, Any]
    delivery: dict[str, Any]
    missing_observations: list[str]
