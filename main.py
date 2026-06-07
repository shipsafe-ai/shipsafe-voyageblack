"""Cloud Run entry point — FastAPI server on port 8080."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.elastic_mcp import get_elasticsearch_tools
from agent.models import OrchestrationResult, PostmortemDraft
from agent.orchestrator import Orchestrator
from agent.specialists.report_writer import ReportWriter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        from shipsafe_shared.instrumentation import init_telemetry
        init_telemetry("voyageblack")
    except ImportError:
        pass
    yield


app = FastAPI(
    title="ShipSafe VoyageBlack",
    description="Automated postmortem generation from incident logs — powered by Elastic",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    incident_id: str
    start_time: datetime
    end_time: datetime


class ApproveResponse(BaseModel):
    document_id: str
    incident_id: str
    status: str = "written"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=OrchestrationResult)
async def run(req: RunRequest) -> OrchestrationResult:
    """Run full VoyageBlack pipeline. Returns PostmortemDraft (status=draft) + CriticVerdict.

    Postmortem is NOT written to Elasticsearch yet — call POST /approve/{incident_id} after review.
    """
    try:
        orch = Orchestrator()
        return await orch.run(
            incident_id=req.incident_id,
            start_time=req.start_time,
            end_time=req.end_time,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/run/stream")
async def run_stream(
    incident_id: str,
    start_time: str,
    end_time: str,
) -> StreamingResponse:
    """SSE stream — emits stage completion events as pipeline executes.

    Client connects, sees 6 stage events + final result event.
    Used by dashboard for live progress display.
    """
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)

    async def event_generator():
        try:
            from agent.specialists.timeline_builder import TimelineBuilder
            from agent.specialists.correlation_engine import CorrelationEngine
            from agent.specialists.impact_calculator import ImpactCalculator
            from agent.specialists.root_cause_analyzer import RootCauseAnalyzer
            from agent.specialists.report_writer import ReportWriter
            from agent.critic import Critic
            from agent.models import PostmortemDraft

            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

            def emit(stage: str, data: dict) -> str:
                return f"data: {json.dumps({'stage': stage, **data})}\n\n"

            # Stage 1
            timeline = await TimelineBuilder().run(
                incident_id=incident_id, start_time=start_dt, end_time=end_dt
            )
            yield emit("TimelineBuilder", {
                "status": "done",
                "entry_count": len(timeline.entries),
                "services": timeline.services_involved,
            })

            # Stage 2
            correlations = await CorrelationEngine().run(timeline=timeline)
            yield emit("CorrelationEngine", {
                "status": "done",
                "service_count": len(correlations),
                "max_cascade_depth": max((c.cascade_depth for c in correlations), default=0),
            })

            # Stage 3
            blast = await ImpactCalculator().run(timeline=timeline, correlations=correlations)
            yield emit("ImpactCalculator", {
                "status": "done",
                "total_errors": blast.total_errors,
                "services_affected": blast.services_affected,
                "duration_minutes": blast.estimated_duration_minutes,
            })

            # Stage 4
            root_cause = await RootCauseAnalyzer().run(
                timeline=timeline, correlations=correlations, blast_radius=blast
            )
            yield emit("RootCauseAnalyzer", {
                "status": "done",
                "confidence": root_cause.confidence,
                "primary_cause_preview": root_cause.primary_cause[:80],
            })

            # Stage 5
            draft = PostmortemDraft(
                incident_id=incident_id,
                timeline=timeline,
                correlations=correlations,
                blast_radius=blast,
                root_cause=root_cause,
            )
            writer = ReportWriter()
            similar = await writer.find_similar(draft=draft)
            draft.similar_incidents = similar
            yield emit("ReportWriter", {
                "status": "done",
                "similar_count": len(similar),
                "top_similarity": similar[0].similarity_score if similar else 0.0,
            })

            # Stage 6
            from agent.critic import Critic
            verdict = await Critic().review(draft)
            draft.status = "draft"
            yield emit("Critic", {
                "status": "done",
                "approved": verdict.approved,
                "injection_detected": verdict.injection_detected,
                "risk_level": verdict.risk_level,
            })

            # Final result
            result = OrchestrationResult(
                draft=draft,
                verdict=verdict,
                approved=verdict.approved,
                requires_human_review=verdict.requires_human_review,
            )
            yield f"data: {json.dumps({'stage': '__result__', 'result': result.model_dump(mode='json')})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'stage': '__error__', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/approve/{incident_id}", response_model=ApproveResponse)
async def approve(incident_id: str, draft: PostmortemDraft) -> ApproveResponse:
    """Human approval gate — writes postmortem to Elasticsearch.

    Only call after reviewing the PostmortemDraft from POST /run.
    Triggers ReportWriter.write() which uses the write_postmortem Agent Builder MCP tool.
    """
    if draft.incident_id != incident_id:
        raise HTTPException(
            status_code=400,
            detail=f"incident_id mismatch: path={incident_id} body={draft.incident_id}",
        )
    try:
        draft.status = "approved"
        writer = ReportWriter()
        doc_id = await writer.write(draft=draft)
        return ApproveResponse(document_id=doc_id, incident_id=incident_id, status="written")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _query_postmortems_via_mcp(limit: int) -> list:
    """Run ES|QL via standalone ES MCP esql tool to list postmortems."""
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    esql = (
        f"FROM postmortems-shipsafe "
        f"| SORT created_at DESC "
        f"| LIMIT {limit} "
        f"| KEEP incident_id, title, severity, created_at, services_affected, status"
    )

    tools, toolset = await get_elasticsearch_tools(["esql"])
    try:
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        agent = Agent(
            model=model,
            name="postmortem_lister",
            instruction=(
                "Run the provided ES|QL query using the esql tool. "
                "Return the raw JSON array of results. No prose."
            ),
            tools=tools,
        )
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="voyageblack", user_id="system")
        runner = Runner(agent=agent, app_name="voyageblack", session_service=session_service)
        result_text = ""
        async for event in runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=f"Run this ES|QL query: {esql}")],
            ),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text and event.is_final_response():
                        result_text = part.text
    finally:
        await toolset.close()

    try:
        return json.loads(result_text)
    except Exception:
        return []


@app.get("/postmortems")
async def list_postmortems(limit: int = 20) -> dict:
    """List past postmortems from postmortems-shipsafe via standalone ES MCP esql tool."""
    try:
        postmortems = await _query_postmortems_via_mcp(limit)
        return {"postmortems": postmortems, "total": len(postmortems)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/postmortems/{incident_id}")
async def get_postmortem(incident_id: str) -> dict:
    """Fetch specific postmortem by incident_id via standalone ES MCP search tool."""
    try:
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types

        tools, toolset = await get_elasticsearch_tools(["search"])
        try:
            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            agent = Agent(
                model=model,
                name="postmortem_fetcher",
                instruction=(
                    "Search the postmortems-shipsafe index for the given incident_id. "
                    "Return the full document JSON. No prose."
                ),
                tools=tools,
            )
            session_service = InMemorySessionService()
            session = await session_service.create_session(
                app_name="voyageblack", user_id="system"
            )
            runner = Runner(
                agent=agent, app_name="voyageblack", session_service=session_service
            )
            result_text = ""
            async for event in runner.run_async(
                user_id="system",
                session_id=session.id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=(
                        f"Search postmortems-shipsafe index for incident_id={incident_id}. "
                        "Return the document."
                    ))],
                ),
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text and event.is_final_response():
                            result_text = part.text
        finally:
            await toolset.close()

        try:
            doc = json.loads(result_text)
        except Exception:
            doc = {"raw": result_text}

        return doc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/mcp/status")
async def mcp_status() -> dict:
    """Health check for both MCP servers.

    Tests standalone ES MCP (list_indices) and Agent Builder MCP (tool list).
    Used by `voyageblack connect` CLI command.
    """
    from agent.elastic_mcp import get_agent_builder_tools

    standalone_ok = False
    agent_builder_ok = False
    indices: list[str] = []
    agent_builder_tools: list[str] = []

    # Test standalone ES MCP
    try:
        tools, toolset = await get_elasticsearch_tools(["list_indices"])
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types

        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        agent = Agent(
            model=model,
            name="mcp_checker",
            instruction="Call list_indices and return the index names as a JSON array. No prose.",
            tools=tools,
        )
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="voyageblack", user_id="system")
        runner = Runner(agent=agent, app_name="voyageblack", session_service=session_service)
        result_text = ""
        async for event in runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part(text="List all Elasticsearch indices.")],
            ),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text and event.is_final_response():
                        result_text = part.text
        await toolset.close()
        standalone_ok = True
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, list):
                indices = [str(i) for i in parsed]
        except Exception:
            pass
    except Exception:
        pass

    # Test Agent Builder MCP
    try:
        ab_tools, ab_toolset = await get_agent_builder_tools()
        agent_builder_tools = [t.name for t in ab_tools]
        await ab_toolset.close()
        agent_builder_ok = len(agent_builder_tools) > 0
    except Exception:
        pass

    return {
        "standaloneOk": standalone_ok,
        "agentBuilderOk": agent_builder_ok,
        "indices": indices,
        "agentBuilderTools": agent_builder_tools,
    }


@app.post("/demo/seed")
async def demo_seed(dry_run: bool = False) -> dict:
    """Bulk-load Hormuz crisis fixtures to Elasticsearch.

    Wait ~30s after this for ELSER to auto-embed semantic_content fields.
    Then POST /run with incident_id=HORMUZ-2026-0601.
    """
    if dry_run:
        return {"status": "dry_run", "message": "Seed skipped — dry_run=true"}
    try:
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "scripts/load_fixtures.py"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        seeded = 0
        for line in (result.stdout or "").splitlines():
            if "seeded" in line.lower():
                for word in line.split():
                    if word.isdigit():
                        seeded = int(word)
                        break
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "seeded": seeded,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
