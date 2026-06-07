"""Tests for Orchestrator — sequential pipeline coordination."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import CriticVerdict, OrchestrationResult, PostmortemDraft
from agent.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_run_full_pipeline(
    incident_id, hormuz_window, sample_timeline, sample_correlations,
    sample_blast_radius, sample_root_cause, sample_similar_incidents, sample_draft, sample_verdict
):
    start, end = hormuz_window
    orch = Orchestrator()

    with (
        patch.object(orch._timeline_builder, "run", AsyncMock(return_value=sample_timeline)),
        patch.object(orch._correlation_engine, "run", AsyncMock(return_value=sample_correlations)),
        patch.object(orch._impact_calculator, "run", AsyncMock(return_value=sample_blast_radius)),
        patch.object(orch._root_cause_analyzer, "run", AsyncMock(return_value=sample_root_cause)),
        patch.object(orch._report_writer, "find_similar", AsyncMock(return_value=sample_similar_incidents)),
        patch.object(orch._critic, "review", AsyncMock(return_value=sample_verdict)),
    ):
        result = await orch.run(
            incident_id=incident_id,
            start_time=start,
            end_time=end,
        )

    assert isinstance(result, OrchestrationResult)
    assert result.draft.incident_id == incident_id
    assert result.draft.status == "draft"
    assert result.approved is True
    assert result.requires_human_review is True


@pytest.mark.asyncio
async def test_orchestrator_critic_always_last(
    incident_id, hormuz_window, sample_timeline, sample_correlations,
    sample_blast_radius, sample_root_cause, sample_similar_incidents
):
    start, end = hormuz_window
    call_order: list[str] = []
    orch = Orchestrator()

    async def track_timeline(**kw): call_order.append("timeline"); return sample_timeline
    async def track_correlation(**kw): call_order.append("correlation"); return sample_correlations
    async def track_impact(**kw): call_order.append("impact"); return sample_blast_radius
    async def track_rootcause(**kw): call_order.append("rootcause"); return sample_root_cause
    async def track_similar(**kw): call_order.append("similar"); return sample_similar_incidents
    async def track_critic(draft): call_order.append("critic"); return CriticVerdict(requires_human_review=True)

    with (
        patch.object(orch._timeline_builder, "run", side_effect=track_timeline),
        patch.object(orch._correlation_engine, "run", side_effect=track_correlation),
        patch.object(orch._impact_calculator, "run", side_effect=track_impact),
        patch.object(orch._root_cause_analyzer, "run", side_effect=track_rootcause),
        patch.object(orch._report_writer, "find_similar", side_effect=track_similar),
        patch.object(orch._critic, "review", side_effect=track_critic),
    ):
        await orch.run(incident_id=incident_id, start_time=start, end_time=end)

    assert call_order[-1] == "critic"
    assert call_order.index("timeline") < call_order.index("correlation")
    assert call_order.index("correlation") < call_order.index("impact")
    assert call_order.index("impact") < call_order.index("rootcause")
    assert call_order.index("rootcause") < call_order.index("similar")
    assert call_order.index("similar") < call_order.index("critic")


@pytest.mark.asyncio
async def test_orchestrator_write_postmortem_not_auto_called(
    incident_id, hormuz_window, sample_timeline, sample_correlations,
    sample_blast_radius, sample_root_cause, sample_similar_incidents, sample_verdict
):
    """write_postmortem must NOT be called during /run — only after /approve."""
    start, end = hormuz_window
    orch = Orchestrator()

    with (
        patch.object(orch._timeline_builder, "run", AsyncMock(return_value=sample_timeline)),
        patch.object(orch._correlation_engine, "run", AsyncMock(return_value=sample_correlations)),
        patch.object(orch._impact_calculator, "run", AsyncMock(return_value=sample_blast_radius)),
        patch.object(orch._root_cause_analyzer, "run", AsyncMock(return_value=sample_root_cause)),
        patch.object(orch._report_writer, "find_similar", AsyncMock(return_value=sample_similar_incidents)),
        patch.object(orch._report_writer, "write", AsyncMock()) as mock_write,
        patch.object(orch._critic, "review", AsyncMock(return_value=sample_verdict)),
    ):
        result = await orch.run(incident_id=incident_id, start_time=start, end_time=end)

    mock_write.assert_not_called()
    assert result.draft.status == "draft"
