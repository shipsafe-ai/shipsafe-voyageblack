"""Cloud Run entry point — FastAPI server on port 8080."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.ais_stream import get_recent_alerts, get_vessel_positions, format_as_log_entries, start_ais_feed
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
    ais_key = os.environ.get("AISSTREAM_API_KEY", "")
    if ais_key:
        asyncio.create_task(start_ais_feed(ais_key))
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

            # Padding flush: forces Envoy/Cloud Run to start streaming immediately
            yield f": {'x' * 2048}\n\n"

            # Stage 1
            yield emit("TimelineBuilder", {"status": "running"})
            await asyncio.sleep(0)
            tb = TimelineBuilder()
            timeline = await tb.run(
                incident_id=incident_id, start_time=start_dt, end_time=end_dt
            )
            if tb.thinking_text:
                yield emit("TimelineBuilder", {"status": "thinking", "thinking": tb.thinking_text})
            yield emit("TimelineBuilder", {
                "status": "done",
                "entry_count": len(timeline.entries),
                "services": timeline.services_involved,
            })

            # Stage 2
            yield emit("CorrelationEngine", {"status": "running"})
            await asyncio.sleep(0)
            ce = CorrelationEngine()
            correlations = await ce.run(timeline=timeline)
            if ce.thinking_text:
                yield emit("CorrelationEngine", {"status": "thinking", "thinking": ce.thinking_text})
            yield emit("CorrelationEngine", {
                "status": "done",
                "service_count": len(correlations),
                "max_cascade_depth": max((c.cascade_depth for c in correlations), default=0),
            })

            # Stage 3
            yield emit("ImpactCalculator", {"status": "running"})
            await asyncio.sleep(0)
            ic = ImpactCalculator()
            blast = await ic.run(timeline=timeline, correlations=correlations)
            if ic.thinking_text:
                yield emit("ImpactCalculator", {"status": "thinking", "thinking": ic.thinking_text})
            yield emit("ImpactCalculator", {
                "status": "done",
                "total_errors": blast.total_errors,
                "services_affected": blast.services_affected,
                "duration_minutes": blast.estimated_duration_minutes,
            })

            # Stage 4
            yield emit("RootCauseAnalyzer", {"status": "running"})
            await asyncio.sleep(0)
            rca = RootCauseAnalyzer()
            root_cause = await rca.run(
                timeline=timeline, correlations=correlations, blast_radius=blast
            )
            if rca.thinking_text:
                yield emit("RootCauseAnalyzer", {"status": "thinking", "thinking": rca.thinking_text})
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
            yield emit("ReportWriter", {"status": "running"})
            await asyncio.sleep(0)
            writer = ReportWriter()
            similar = await writer.find_similar(draft=draft)
            draft.similar_incidents = similar
            if writer.thinking_text:
                yield emit("ReportWriter", {"status": "thinking", "thinking": writer.thinking_text})
            yield emit("ReportWriter", {
                "status": "done",
                "similar_count": len(similar),
                "top_similarity": similar[0].similarity_score if similar else 0.0,
            })

            # Stage 6
            yield emit("Critic", {"status": "running"})
            await asyncio.sleep(0)
            critic = Critic()
            verdict = await critic.review(draft)
            draft.status = "draft"
            if critic.thinking_text:
                yield emit("Critic", {"status": "thinking", "thinking": critic.thinking_text})
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

    standalone_error: str = ""
    agent_builder_error: str = ""

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
    except Exception as exc:
        standalone_error = str(exc)

    # Test Agent Builder MCP
    try:
        ab_tools, ab_toolset = await get_agent_builder_tools()
        agent_builder_tools = [t.name for t in ab_tools]
        await ab_toolset.close()
        agent_builder_ok = len(agent_builder_tools) > 0
    except Exception as exc:
        agent_builder_error = str(exc)

    return {
        "standaloneOk": standalone_ok,
        "agentBuilderOk": agent_builder_ok,
        "indices": indices,
        "agentBuilderTools": agent_builder_tools,
        "standaloneError": standalone_error,
        "agentBuilderError": agent_builder_error,
    }


def _run_script(script: str, cwd: str) -> dict:
    """Run a Python script as subprocess, return stdout/stderr/returncode."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


@app.post("/demo/seed")
async def demo_seed(dry_run: bool = False) -> dict:
    """Create index mappings + bulk-load Hormuz crisis fixtures to Elasticsearch.

    Runs create_mappings.py first (idempotent), then load_fixtures.py.
    Wait ~30s after this for ELSER to auto-embed semantic_content fields.
    Then POST /run with incident_id=HORMUZ-2026-0601.
    """
    if dry_run:
        return {"status": "dry_run", "message": "Seed skipped — dry_run=true"}
    try:
        cwd = os.path.dirname(os.path.abspath(__file__))
        mapping_result = _run_script("scripts/create_mappings.py", cwd)
        if mapping_result["returncode"] != 0:
            return {
                "status": "error",
                "stage": "create_mappings",
                "stdout": mapping_result["stdout"][-500:],
                "stderr": mapping_result["stderr"][-500:],
            }
        fixture_result = _run_script("scripts/load_fixtures.py", cwd)
        seeded = 0
        for line in fixture_result["stdout"].splitlines():
            if line.startswith("SEEDED_COUNT:"):
                try:
                    seeded = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break
        return {
            "status": "ok" if fixture_result["returncode"] == 0 else "error",
            "seeded": seeded,
            "mappings_stdout": mapping_result["stdout"][-300:],
            "stdout": fixture_result["stdout"][-500:],
            "stderr": fixture_result["stderr"][-500:],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/demo/seed/generic")
async def demo_seed_generic(dry_run: bool = False) -> dict:
    """Create index mappings + bulk-load generic incident fixtures — auth→payment→notification cascade.

    Demonstrates VoyageBlack works for any ops team, not just maritime.
    Incident: OIDC token validation bug cascades across auth/payment/notification services.
    incident_id: AUTH-OUTAGE-2026-0607
    window: 2026-06-07T09:01:00Z → 2026-06-07T09:06:00Z
    """
    if dry_run:
        return {"status": "dry_run", "message": "Seed skipped — dry_run=true"}
    try:
        cwd = os.path.dirname(os.path.abspath(__file__))
        mapping_result = _run_script("scripts/create_mappings.py", cwd)
        if mapping_result["returncode"] != 0:
            return {
                "status": "error",
                "stage": "create_mappings",
                "stdout": mapping_result["stdout"][-500:],
                "stderr": mapping_result["stderr"][-500:],
            }
        fixture_result = _run_script("scripts/load_generic_fixtures.py", cwd)
        seeded = 0
        for line in fixture_result["stdout"].splitlines():
            if line.startswith("SEEDED_COUNT:"):
                try:
                    seeded = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break
        return {
            "status": "ok" if fixture_result["returncode"] == 0 else "error",
            "seeded": seeded,
            "incident_id": "AUTH-OUTAGE-2026-0607",
            "start_time": "2026-06-07T09:01:00Z",
            "end_time": "2026-06-07T09:06:00Z",
            "mappings_stdout": mapping_result["stdout"][-300:],
            "stdout": fixture_result["stdout"][-500:],
            "stderr": fixture_result["stderr"][-500:],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/debug/thinking")
async def debug_thinking() -> dict:
    """Test if Vertex AI returns thought parts. Shows raw part attributes."""
    from agent.runner_utils import run_gemini_direct_with_thinking
    from google import genai
    from google.genai import types as genai_types

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")

    try:
        if use_vertex:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT", "shipsafe-ai")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            client = genai.Client(vertexai=True, project=project, location=location)
        else:
            client = genai.Client()

        try:
            thinking_cfg = genai_types.ThinkingConfig(include_thoughts=True, thinking_budget=4096)
        except TypeError:
            thinking_cfg = genai_types.ThinkingConfig(include_thoughts=True)

        response = await client.aio.models.generate_content(
            model=model,
            contents="What is 2+2? Think step by step.",
            config=genai_types.GenerateContentConfig(
                system_instruction="You are a helpful assistant.",
                thinking_config=thinking_cfg,
            ),
        )

        parts_info = []
        if response.candidates:
            for i, part in enumerate(response.candidates[0].content.parts):
                parts_info.append({
                    "index": i,
                    "thought": getattr(part, "thought", "MISSING"),
                    "text_len": len(getattr(part, "text", "") or ""),
                    "text_preview": (getattr(part, "text", "") or "")[:100],
                    "attrs": [a for a in dir(part) if not a.startswith("_") and a not in ("model_fields", "model_config")],
                })

        text, thinking = await run_gemini_direct_with_thinking(
            model, "You are helpful.", "What is 2+2? Think step by step."
        )
        return {
            "model": model,
            "use_vertex": use_vertex,
            "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "not-set"),
            "parts": parts_info,
            "extracted_thinking_len": len(thinking),
            "extracted_text": text[:200],
        }
    except Exception as exc:
        return {"error": str(exc), "type": type(exc).__name__}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


@app.get("/ais")
async def ais_status() -> dict:
    """Live AIS safety broadcasts and vessel positions in the Hormuz corridor."""
    return {
        "safety_alerts": get_recent_alerts(),
        "vessels": get_vessel_positions(),
        "log_entries_available": len(format_as_log_entries()),
        "description": "Real maritime safety broadcasts from aisstream.io — enriches incident timeline",
        "source": "aisstream.io",
    }
