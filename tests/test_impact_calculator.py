"""Tests for ImpactCalculator specialist (uses standalone ES MCP esql tool)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import BlastRadius
from agent.specialists.impact_calculator import ImpactCalculator, _parse_llm_response


SAMPLE_BLAST_JSON = json.dumps({
    "total_errors": 5,
    "services_affected": 4,
    "error_rate_per_service": {
        "routing-engine": 75.0,
        "naviguard": 100.0,
        "fivetran-sync": 33.3,
        "agentops": 20.0,
    },
    "estimated_duration_minutes": 7.0,
    "cascade_chain": ["ukmto-feed", "routing-engine", "naviguard", "agentops"],
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


def test_parse_blast_radius_valid():
    result = _parse_llm_response(SAMPLE_BLAST_JSON)
    assert result is not None
    assert isinstance(result, BlastRadius)
    assert result.total_errors == 5
    assert result.services_affected == 4
    assert len(result.cascade_chain) == 4
    assert result.error_rate_per_service["naviguard"] == 100.0


def test_parse_blast_radius_empty_returns_none():
    assert _parse_llm_response("") is None


def test_parse_blast_radius_bad_json():
    assert _parse_llm_response("not json") is None


@pytest.mark.asyncio
async def test_impact_calculator_uses_standalone_mcp(sample_timeline, sample_correlations, hormuz_window):
    start, end = hormuz_window
    calc = ImpactCalculator()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.impact_calculator.get_elasticsearch_tools",
              AsyncMock(return_value=([], mock_toolset))) as mock_get_tools,
        patch("agent.specialists.impact_calculator.Runner",
              return_value=_make_runner(SAMPLE_BLAST_JSON)),
        patch("agent.specialists.impact_calculator.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await calc.run(
            timeline=sample_timeline,
            correlations=sample_correlations,
        )

    # Verify it used get_elasticsearch_tools (standalone MCP), not agent builder
    mock_get_tools.assert_called_once()
    assert isinstance(result, BlastRadius)
    assert result.total_errors == 5
    assert result.services_affected == 4


@pytest.mark.asyncio
async def test_impact_calculator_fallback(sample_timeline, sample_correlations):
    calc = ImpactCalculator()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.impact_calculator.get_elasticsearch_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.impact_calculator.Runner",
              return_value=_make_runner("garbage")),
        patch("agent.specialists.impact_calculator.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await calc.run(
            timeline=sample_timeline,
            correlations=sample_correlations,
        )

    assert isinstance(result, BlastRadius)
    # Fallback: derive from correlations data
    assert result.services_affected == len(sample_correlations)
