"""Tests for TimelineBuilder specialist."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import IncidentTimeline
from agent.specialists.timeline_builder import TimelineBuilder, _parse_llm_response


SAMPLE_TIMELINE_JSON = json.dumps({
    "correlation_id": "HORMUZ-2026-0601",
    "start_time": "2026-06-01T14:57:00Z",
    "end_time": "2026-06-01T15:02:00Z",
    "entries": [
        {
            "timestamp": "2026-06-01T14:55:00Z",
            "service": "ukmto-feed",
            "level": "CRITICAL",
            "message": "UKMTO advisory: transit restriction in effect.",
            "event_id": "EVT-001",
        },
        {
            "timestamp": "2026-06-01T15:00:17Z",
            "service": "naviguard",
            "level": "CRITICAL",
            "message": "AI routing model regression: 31% crisis avoidance score.",
            "error_code": "MODEL_REGRESSION",
            "event_id": "EVT-007",
        },
    ],
    "services_involved": ["ukmto-feed", "naviguard"],
})


def _make_runner(json_response: str):
    mock_event = MagicMock()
    mock_event.content.parts = [MagicMock(text=json_response)]
    mock_event.is_final_response.return_value = True

    async def fake_run_async(**kwargs):
        yield mock_event

    runner = MagicMock()
    runner.run_async = fake_run_async
    return runner


def test_parse_llm_response_valid():
    result = _parse_llm_response(SAMPLE_TIMELINE_JSON)
    assert result is not None
    assert isinstance(result, IncidentTimeline)
    assert result.correlation_id == "HORMUZ-2026-0601"
    assert len(result.entries) == 2
    assert result.entries[0].service == "ukmto-feed"
    assert result.entries[1].error_code == "MODEL_REGRESSION"


def test_parse_llm_response_with_markdown_fence():
    fenced = f"```json\n{SAMPLE_TIMELINE_JSON}\n```"
    result = _parse_llm_response(fenced)
    assert result is not None
    assert len(result.entries) == 2


def test_parse_llm_response_empty_returns_none():
    assert _parse_llm_response("") is None


def test_parse_llm_response_bad_json_returns_none():
    assert _parse_llm_response("not json") is None


@pytest.mark.asyncio
async def test_timeline_builder_run_success(hormuz_window, incident_id):
    start_time, end_time = hormuz_window
    builder = TimelineBuilder()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.timeline_builder.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.timeline_builder.Runner",
              return_value=_make_runner(SAMPLE_TIMELINE_JSON)),
        patch("agent.specialists.timeline_builder.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await builder.run(
            incident_id=incident_id,
            start_time=start_time,
            end_time=end_time,
        )

    assert isinstance(result, IncidentTimeline)
    assert result.correlation_id == incident_id
    assert len(result.entries) == 2
    mock_toolset.close.assert_called_once()


@pytest.mark.asyncio
async def test_timeline_builder_falls_back_on_bad_response(hormuz_window, incident_id):
    start_time, end_time = hormuz_window
    builder = TimelineBuilder()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.timeline_builder.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.timeline_builder.Runner",
              return_value=_make_runner("garbage response")),
        patch("agent.specialists.timeline_builder.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await builder.run(
            incident_id=incident_id,
            start_time=start_time,
            end_time=end_time,
        )

    assert isinstance(result, IncidentTimeline)
    assert result.correlation_id == incident_id
    assert result.entries == []
