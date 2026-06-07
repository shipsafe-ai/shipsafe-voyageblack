"""CorrelationEngine — finds service error correlation via Agent Builder MCP."""

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
from agent.models import IncidentTimeline, ServiceCorrelation

_TOOLS = ["service_error_correlation"]

_INSTRUCTION = """\
You are CorrelationEngine, service dependency analyst for VoyageBlack.

Call service_error_correlation with the incident time window parameters.
The tool runs an ES|QL aggregation that groups errors by service and error_code.

For each service in the results:
- Count total errors
- Collect distinct error_codes
- Record first_seen timestamp
- Infer cascade_depth: 0 for root trigger, 1 for first downstream, 2 for second, etc.
  Use temporal ordering to determine depth — earlier first_seen = lower depth.

Return ONLY this JSON (no prose, no markdown fences):
{
  "correlations": [
    {
      "service": "string",
      "error_count": integer,
      "error_codes": ["string"],
      "first_seen": "ISO8601 or null",
      "cascade_depth": integer
    }
  ]
}\
"""


def _parse_llm_response(text: str) -> list[ServiceCorrelation] | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    for candidate in [text, *re.findall(r"\{[\s\S]*\}", text)]:
        try:
            data = json.loads(candidate)
            if "correlations" in data:
                return [ServiceCorrelation(**c) for c in data["correlations"]]
        except Exception:
            pass
    return None


class CorrelationEngine:
    """Queries Elasticsearch for cross-service error correlation via Agent Builder MCP.

    Uses service_error_correlation (ES|QL aggregation by service + error_code).
    Returns list of ServiceCorrelation ordered by cascade depth.
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    async def run(self, timeline: IncidentTimeline) -> list[ServiceCorrelation]:
        prompt = (
            f"Find service error correlation for incident {timeline.correlation_id}.\n"
            f"Time window: {timeline.start_time.isoformat()} → {timeline.end_time.isoformat()}\n"
            f"Services seen in timeline: {', '.join(timeline.services_involved)}\n\n"
            "Call service_error_correlation. Return correlations JSON."
        )

        tools, toolset = await get_agent_builder_tools(_TOOLS)
        try:
            agent = Agent(
                model=self._model,
                name="correlation_engine",
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

        correlations = _parse_llm_response(result_text)
        if correlations is None:
            return []
        return sorted(correlations, key=lambda c: c.cascade_depth)
