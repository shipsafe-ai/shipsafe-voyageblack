"""Tests for FastAPI endpoints — /run, /approve, /postmortems, /health."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.models import CriticVerdict, OrchestrationResult, PostmortemDraft
from main import app


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_run_returns_draft_status(sample_result):
    with patch("main.Orchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(return_value=sample_result)
        mock_orch_cls.return_value = mock_orch

        resp = client.post("/run", json={
            "incident_id": "HORMUZ-2026-0601",
            "start_time": "2026-06-01T14:57:00Z",
            "end_time": "2026-06-01T15:02:00Z",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"]["status"] == "draft"
    assert body["requires_human_review"] is True


@pytest.mark.asyncio
async def test_run_missing_fields():
    resp = client.post("/run", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_approve_writes_postmortem(sample_draft):
    with patch("main.ReportWriter") as mock_writer_cls:
        mock_writer = MagicMock()
        mock_writer.write = AsyncMock(return_value="HORMUZ-2026-0601")
        mock_writer_cls.return_value = mock_writer

        resp = client.post(
            "/approve/HORMUZ-2026-0601",
            content=sample_draft.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "written"
    assert body["document_id"] == "HORMUZ-2026-0601"
    mock_writer.write.assert_called_once()


@pytest.mark.asyncio
async def test_postmortems_uses_elasticsearch_mcp():
    # Patch the extracted helper that uses standalone ES MCP
    with patch("main._query_postmortems_via_mcp", AsyncMock(return_value=[])) as mock_query:
        resp = client.get("/postmortems")

    # Endpoint must delegate to _query_postmortems_via_mcp (standalone MCP), not direct REST
    mock_query.assert_called_once()
    assert resp.status_code == 200
    assert resp.json()["postmortems"] == []


def test_demo_seed_endpoint_exists():
    # Just verify endpoint registered — actual seeding hits ES
    resp = client.post("/demo/seed", params={"dry_run": "true"})
    # 200 or 422 (missing body), not 404
    assert resp.status_code != 404
