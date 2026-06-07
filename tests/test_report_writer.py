"""Tests for ReportWriter specialist (similar_past_incident + write_postmortem via Agent Builder)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import PostmortemDraft, SimilarIncident
from agent.specialists.report_writer import ReportWriter, _parse_similar_incidents


SAMPLE_SIMILAR_JSON = json.dumps({
    "similar_incidents": [
        {
            "id": "REDSEA-2024-1210",
            "title": "Red Sea shipping disruption — Houthi threat response",
            "similarity_score": 0.87,
            "root_cause": "Regional security advisory triggered mass rerouting without validated fallback.",
            "resolution": "Activated Cape of Good Hope diversions; updated crisis avoidance model.",
        }
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


def test_parse_similar_incidents_valid():
    result = _parse_similar_incidents(SAMPLE_SIMILAR_JSON)
    assert result is not None
    assert len(result) == 1
    assert result[0].similarity_score == 0.87
    assert result[0].id == "REDSEA-2024-1210"


def test_parse_similar_incidents_bad_json():
    assert _parse_similar_incidents("bad") is None


def test_parse_similar_incidents_empty():
    assert _parse_similar_incidents("") is None


@pytest.mark.asyncio
async def test_report_writer_find_similar(sample_draft):
    writer = ReportWriter()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.report_writer.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.report_writer.Runner",
              return_value=_make_runner(SAMPLE_SIMILAR_JSON)),
        patch("agent.specialists.report_writer.InMemorySessionService",
              return_value=mock_session_service),
    ):
        similar = await writer.find_similar(draft=sample_draft)

    assert isinstance(similar, list)
    assert len(similar) == 1
    assert similar[0].similarity_score == 0.87
    mock_toolset.close.assert_called_once()


@pytest.mark.asyncio
async def test_report_writer_write_postmortem_uses_agent_builder(sample_draft):
    writer = ReportWriter()

    write_response = json.dumps({"document_id": "HORMUZ-2026-0601", "status": "written"})

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.report_writer.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))) as mock_get,
        patch("agent.specialists.report_writer.Runner",
              return_value=_make_runner(write_response)),
        patch("agent.specialists.report_writer.InMemorySessionService",
              return_value=mock_session_service),
    ):
        doc_id = await writer.write(draft=sample_draft)

    mock_get.assert_called_once()
    assert doc_id == "HORMUZ-2026-0601"


@pytest.mark.asyncio
async def test_report_writer_find_similar_fallback_on_bad_response(sample_draft):
    writer = ReportWriter()

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session_service = MagicMock()
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_toolset = MagicMock()
    mock_toolset.get_tools = AsyncMock(return_value=[])
    mock_toolset.close = AsyncMock()

    with (
        patch("agent.specialists.report_writer.get_agent_builder_tools",
              AsyncMock(return_value=([], mock_toolset))),
        patch("agent.specialists.report_writer.Runner",
              return_value=_make_runner("garbage")),
        patch("agent.specialists.report_writer.InMemorySessionService",
              return_value=mock_session_service),
    ):
        similar = await writer.find_similar(draft=sample_draft)

    assert similar == []
