"""Tests for Pydantic models — field validation, defaults, status transitions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.models import (
    BlastRadius,
    CriticVerdict,
    IncidentTimeline,
    OrchestrationResult,
    PostmortemDraft,
    RootCauseHypothesis,
    ServiceCorrelation,
    SimilarIncident,
    TimelineEntry,
)


def test_timeline_entry_defaults():
    entry = TimelineEntry(
        timestamp=datetime(2026, 6, 1, 14, 55, tzinfo=timezone.utc),
        service="test-svc",
        level="ERROR",
        message="something failed",
    )
    assert entry.error_code is None
    assert entry.duration_ms is None
    assert entry.event_id is None


def test_incident_timeline_empty_defaults():
    timeline = IncidentTimeline(
        correlation_id="INC-001",
        start_time=datetime(2026, 6, 1, 14, 55, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 1, 15, 2, tzinfo=timezone.utc),
    )
    assert timeline.entries == []
    assert timeline.services_involved == []


def test_postmortem_draft_default_status():
    entry = TimelineEntry(
        timestamp=datetime(2026, 6, 1, 14, 55, tzinfo=timezone.utc),
        service="svc",
        level="INFO",
        message="msg",
    )
    timeline = IncidentTimeline(
        correlation_id="INC-001",
        start_time=datetime(2026, 6, 1, 14, 55, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 1, 15, 2, tzinfo=timezone.utc),
        entries=[entry],
    )
    draft = PostmortemDraft(incident_id="INC-001", timeline=timeline)
    assert draft.status == "draft"
    assert draft.severity == "HIGH"
    assert draft.correlations == []
    assert draft.recommendations == []


def test_critic_verdict_approved_by_default():
    verdict = CriticVerdict()
    assert verdict.approved is True
    assert verdict.injection_detected is False
    assert verdict.requires_human_review is False
    assert verdict.confidence_multiplier == 1.0


def test_root_cause_confidence_range(sample_root_cause):
    assert 0.0 <= sample_root_cause.confidence <= 1.0


def test_similar_incident_score_range(sample_similar_incidents):
    for inc in sample_similar_incidents:
        assert 0.0 <= inc.similarity_score <= 1.0


def test_blast_radius_defaults():
    br = BlastRadius()
    assert br.total_errors == 0
    assert br.services_affected == 0
    assert br.cascade_chain == []


def test_orchestration_result_requires_human_review(sample_result):
    assert sample_result.requires_human_review is True
    assert sample_result.draft.status == "draft"


def test_postmortem_draft_full(sample_draft):
    assert sample_draft.incident_id == "HORMUZ-2026-0601"
    assert sample_draft.severity == "CRITICAL"
    assert len(sample_draft.timeline.entries) == 3
    assert len(sample_draft.correlations) == 2
    assert len(sample_draft.similar_incidents) == 1
    assert sample_draft.similar_incidents[0].similarity_score == 0.87
