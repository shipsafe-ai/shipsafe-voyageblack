"""Tests for RootCauseAnalyzer specialist (Gemini reasoning, no MCP tools)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import RootCauseHypothesis
from agent.specialists.root_cause_analyzer import RootCauseAnalyzer, _parse_llm_response


SAMPLE_ROOT_CAUSE_JSON = json.dumps({
    "primary_cause": "Unvalidated algorithm change (MR !447) merged without scenario tests.",
    "contributing_factors": [
        "AIS signal loss masked early warning signals",
        "Stale Jebel Ali feed (4h 26m lag)",
    ],
    "confidence": 0.87,
    "evidence": [
        "EVT-005: MR !447 merged with bypassed tests",
        "EVT-007: 41% routing regression post-merge",
    ],
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


def test_parse_root_cause_valid():
    result = _parse_llm_response(SAMPLE_ROOT_CAUSE_JSON)
    assert result is not None
    assert isinstance(result, RootCauseHypothesis)
    assert result.confidence == 0.87
    assert len(result.contributing_factors) == 2


def test_parse_root_cause_bad_json():
    assert _parse_llm_response("bad") is None


def test_parse_root_cause_empty():
    assert _parse_llm_response("") is None


@pytest.mark.asyncio
async def test_root_cause_analyzer_no_mcp_tools(sample_timeline, sample_correlations, sample_blast_radius):
    analyzer = RootCauseAnalyzer()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    with (
        patch("agent.specialists.root_cause_analyzer.Runner",
              return_value=_make_runner(SAMPLE_ROOT_CAUSE_JSON)),
        patch("agent.specialists.root_cause_analyzer.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await analyzer.run(
            timeline=sample_timeline,
            correlations=sample_correlations,
            blast_radius=sample_blast_radius,
        )

    # No MCP tools used — pure Gemini reasoning (module imports no MCP functions)
    assert isinstance(result, RootCauseHypothesis)
    assert result.confidence == 0.87


@pytest.mark.asyncio
async def test_root_cause_fallback_on_bad_response(sample_timeline, sample_correlations, sample_blast_radius):
    analyzer = RootCauseAnalyzer()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    with (
        patch("agent.specialists.root_cause_analyzer.Runner",
              return_value=_make_runner("not json")),
        patch("agent.specialists.root_cause_analyzer.InMemorySessionService",
              return_value=mock_session_service),
    ):
        result = await analyzer.run(
            timeline=sample_timeline,
            correlations=sample_correlations,
            blast_radius=sample_blast_radius,
        )

    assert isinstance(result, RootCauseHypothesis)
    assert result.confidence == 0.0
    assert result.primary_cause != ""
