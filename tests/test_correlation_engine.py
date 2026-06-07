"""Tests for CorrelationEngine specialist."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import ServiceCorrelation
from agent.specialists.correlation_engine import CorrelationEngine, _parse_llm_response


SAMPLE_CORRELATION_JSON = json.dumps({
    "correlations": [
        {
            "service": "routing-engine",
            "error_count": 3,
            "error_codes": ["ROUTE_UNAVAILABLE"],
            "first_seen": "2026-06-01T14:56:11Z",
            "cascade_depth": 1,
        },
        {
            "service": "naviguard",
            "error_count": 1,
            "error_codes": ["MODEL_REGRESSION"],
            "first_seen": "2026-06-01T15:00:17Z",
            "cascade_depth": 2,
        },
    ]
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
    result = _parse_llm_response(SAMPLE_CORRELATION_JSON)
    assert result is not None
    assert len(result) == 2
    assert result[0].service == "routing-engine"
    assert result[0].cascade_depth == 1
    assert result[1].service == "naviguard"


def test_parse_llm_response_empty_returns_empty():
    assert _parse_llm_response("") is None


def test_parse_llm_response_bad_json():
    assert _parse_llm_response("bad") is None


@pytest.mark.asyncio
async def test_correlation_engine_run_success(sample_timeline, hormuz_window):
    start, end = hormuz_window
    engine = CorrelationEngine()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.correlation_engine.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.correlation_engine.Runner",
              return_value=_make_runner(SAMPLE_CORRELATION_JSON)),
        patch("agent.specialists.correlation_engine.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await engine.run(timeline=sample_timeline)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].service == "routing-engine"
    mock_toolset.close.assert_called_once()


@pytest.mark.asyncio
async def test_correlation_engine_falls_back_on_bad_response(sample_timeline):
    engine = CorrelationEngine()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.correlation_engine.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.correlation_engine.Runner",
              return_value=_make_runner("garbage")),
        patch("agent.specialists.correlation_engine.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await engine.run(timeline=sample_timeline)

    assert isinstance(result, list)
    assert result == []
