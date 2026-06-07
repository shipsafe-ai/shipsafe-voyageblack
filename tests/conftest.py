"""Shared fixtures for VoyageBlack tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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

# ---------------------------------------------------------------------------
# Hormuz crisis time window
# ---------------------------------------------------------------------------

START_TIME = datetime(2026, 6, 1, 14, 57, 0, tzinfo=timezone.utc)  # t2: VoyageBlack opens
END_TIME = datetime(2026, 6, 1, 15, 2, 0, tzinfo=timezone.utc)     # t7: human decision
INCIDENT_ID = "HORMUZ-2026-0601"


@pytest.fixture
def hormuz_window() -> tuple[datetime, datetime]:
    return START_TIME, END_TIME


@pytest.fixture
def incident_id() -> str:
    return INCIDENT_ID


# ---------------------------------------------------------------------------
# Sample timeline entries
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_entries() -> list[TimelineEntry]:
    return [
        TimelineEntry(
            timestamp=datetime(2026, 6, 1, 14, 55, 0, tzinfo=timezone.utc),
            service="ukmto-feed",
            level="CRITICAL",
            message="UKMTO advisory: Strait of Hormuz transit restriction in effect.",
            event_id="EVT-001",
        ),
        TimelineEntry(
            timestamp=datetime(2026, 6, 1, 14, 56, 11, tzinfo=timezone.utc),
            service="routing-engine",
            level="ERROR",
            message="Route recalculation failed for IMO 9811000: primary waypoint restricted.",
            error_code="ROUTE_UNAVAILABLE",
            event_id="EVT-003",
        ),
        TimelineEntry(
            timestamp=datetime(2026, 6, 1, 15, 0, 17, tzinfo=timezone.utc),
            service="naviguard",
            level="CRITICAL",
            message="AI routing model regression detected. Crisis avoidance score: 31%.",
            error_code="MODEL_REGRESSION",
            event_id="EVT-007",
        ),
    ]


@pytest.fixture
def sample_timeline(sample_entries) -> IncidentTimeline:
    return IncidentTimeline(
        correlation_id=INCIDENT_ID,
        start_time=START_TIME,
        end_time=END_TIME,
        entries=sample_entries,
        services_involved=["ukmto-feed", "routing-engine", "naviguard"],
    )


@pytest.fixture
def sample_correlations() -> list[ServiceCorrelation]:
    return [
        ServiceCorrelation(
            service="routing-engine",
            error_count=3,
            error_codes=["ROUTE_UNAVAILABLE"],
            first_seen=datetime(2026, 6, 1, 14, 56, tzinfo=timezone.utc),
            cascade_depth=1,
        ),
        ServiceCorrelation(
            service="naviguard",
            error_count=1,
            error_codes=["MODEL_REGRESSION"],
            first_seen=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
            cascade_depth=2,
        ),
    ]


@pytest.fixture
def sample_blast_radius() -> BlastRadius:
    return BlastRadius(
        total_errors=5,
        services_affected=4,
        error_rate_per_service={"routing-engine": 75.0, "naviguard": 100.0},
        estimated_duration_minutes=7.0,
        cascade_chain=["ukmto-feed", "routing-engine", "naviguard", "agentops"],
    )


@pytest.fixture
def sample_root_cause() -> RootCauseHypothesis:
    return RootCauseHypothesis(
        primary_cause="Unvalidated algorithm change (MR !447) merged without scenario tests.",
        contributing_factors=[
            "AIS signal loss masked early warning signals",
            "Stale Jebel Ali feed (4h 26m lag) prevented real-time rerouting",
        ],
        confidence=0.87,
        evidence=["EVT-005: MR !447 merged with bypassed tests", "EVT-007: 41% regression"],
    )


@pytest.fixture
def sample_similar_incidents() -> list[SimilarIncident]:
    return [
        SimilarIncident(
            id="REDSEA-2024-1210",
            title="Red Sea shipping disruption — Houthi threat response",
            similarity_score=0.87,
            root_cause="Regional security advisory triggered mass rerouting without validated fallback routes.",
            resolution="Activated pre-approved Cape of Good Hope diversions; updated crisis avoidance model.",
        )
    ]


@pytest.fixture
def sample_draft(sample_timeline, sample_correlations, sample_blast_radius,
                 sample_root_cause, sample_similar_incidents) -> PostmortemDraft:
    return PostmortemDraft(
        incident_id=INCIDENT_ID,
        title="Strait of Hormuz Transit Restriction — AI Routing Regression",
        severity="CRITICAL",
        timeline=sample_timeline,
        correlations=sample_correlations,
        blast_radius=sample_blast_radius,
        root_cause=sample_root_cause,
        similar_incidents=sample_similar_incidents,
        recommendations=[
            "Mandate scenario test passage before merging routing algorithm changes.",
            "Implement AIS signal loss alerting with <5min detection threshold.",
        ],
        status="draft",
    )


@pytest.fixture
def sample_verdict() -> CriticVerdict:
    return CriticVerdict(
        approved=True,
        injection_detected=False,
        requires_human_review=True,
        risk_level="low",
        reasoning="No injection detected. Postmortem contains external-write recommendation; human review required.",
        confidence_multiplier=1.0,
    )


@pytest.fixture
def sample_result(sample_draft, sample_verdict) -> OrchestrationResult:
    return OrchestrationResult(
        draft=sample_draft,
        verdict=sample_verdict,
        approved=sample_verdict.approved,
        requires_human_review=sample_verdict.requires_human_review,
    )


# ---------------------------------------------------------------------------
# Mock MCP tool helpers
# ---------------------------------------------------------------------------

def make_mock_tool(name: str, return_json: str) -> MagicMock:
    """Create a mock ADK tool that returns a fixed JSON string."""
    tool = MagicMock()
    tool.name = name
    return tool


def make_mock_toolset(tools: list[MagicMock]) -> MagicMock:
    toolset = MagicMock()
    toolset.get_tools = AsyncMock(return_value=tools)
    toolset.close = AsyncMock()
    return toolset


# ---------------------------------------------------------------------------
# Mock Gemini runner event
# ---------------------------------------------------------------------------

def make_runner_event(text: str, is_final: bool = True) -> MagicMock:
    part = MagicMock()
    part.text = text
    content = MagicMock()
    content.parts = [part]
    event = MagicMock()
    event.content = content
    event.is_final_response = MagicMock(return_value=is_final)
    return event


async def mock_runner_stream(events: list[MagicMock]):
    for ev in events:
        yield ev
