"""TimelineBuilder — reconstructs incident timeline via Agent Builder MCP tools."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from agent.elastic_mcp import get_agent_builder_tools
from agent.models import IncidentTimeline, TimelineEntry

_TOOLS = ["incident_logs_timewindow", "incident_logs_semantic"]

_INSTRUCTION = """\
You are TimelineBuilder, an incident analysis specialist for VoyageBlack.

You have access to two Elasticsearch tools:
- incident_logs_timewindow: fetch logs within a time window by correlation_id
- incident_logs_semantic: semantic search over logs using ELSER

Steps:
1. Call incident_logs_timewindow with the provided start_time, end_time, and correlation_id.
2. If you find fewer than 3 entries, also call incident_logs_semantic with the correlation_id as query.
3. Merge results, deduplicate by event_id, sort ascending by timestamp.
4. Extract the services_involved list from unique service values.

Return ONLY this JSON (no prose, no markdown fences):
{
  "correlation_id": "string",
  "start_time": "ISO8601",
  "end_time": "ISO8601",
  "entries": [
    {
      "timestamp": "ISO8601",
      "service": "string",
      "level": "CRITICAL|ERROR|WARNING|INFO",
      "message": "string",
      "error_code": "string or null",
      "duration_ms": integer or null,
      "event_id": "string or null"
    }
  ],
  "services_involved": ["string"]
}\
"""


def _parse_llm_response(text: str) -> IncidentTimeline | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    for candidate in [text, *re.findall(r"\{[\s\S]*\}", text)]:
        try:
            return IncidentTimeline.model_validate_json(candidate)
        except Exception:
            pass
        try:
            return IncidentTimeline(**json.loads(candidate))
        except Exception:
            pass
    return None


def _fallback(incident_id: str, start_time: datetime, end_time: datetime) -> IncidentTimeline:
    return IncidentTimeline(
        correlation_id=incident_id,
        start_time=start_time,
        end_time=end_time,
        entries=[],
        services_involved=[],
    )


class TimelineBuilder:
    """Queries Elasticsearch for incident log timeline via Agent Builder MCP.

    Uses incident_logs_timewindow (ES|QL time-bounded) and incident_logs_semantic
    (ELSER semantic search) to reconstruct the incident timeline.
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    async def run(
        self,
        incident_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> IncidentTimeline:
        prompt = (
            f"Build incident timeline.\n"
            f"incident_id (correlation_id): {incident_id}\n"
            f"start_time: {start_time.isoformat()}\n"
            f"end_time: {end_time.isoformat()}\n\n"
            "Call incident_logs_timewindow then incident_logs_semantic if needed. "
            "Return IncidentTimeline JSON."
        )

        tools, toolset = await get_agent_builder_tools(_TOOLS)
        try:
            agent = Agent(
                model=self._model,
                name="timeline_builder",
                instruction=_INSTRUCTION,
                tools=tools,
            )
            session_service = InMemorySessionService()
            session = await session_service.create_session(
                app_name="voyageblack", user_id="system"
            )
            runner = Runner(
                agent=agent,
                app_name="voyageblack",
                session_service=session_service,
            )

            result_text = ""
            _json_fallback = ""
            async for event in runner.run_async(
                user_id="system",
                session_id=session.id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=prompt)],
                ),
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            if event.is_final_response():
                                result_text = part.text
                            elif "{" in part.text:
                                _json_fallback = part.text
            if not result_text:
                result_text = _json_fallback
        finally:
            await toolset.close()

        timeline = _parse_llm_response(result_text)
        if timeline is None:
            return _fallback(incident_id, start_time, end_time)
        return timeline
