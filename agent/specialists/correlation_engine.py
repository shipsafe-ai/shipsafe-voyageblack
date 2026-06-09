"""CorrelationEngine — finds service error correlation via Agent Builder MCP."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

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
- Infer cascade_depth from first_seen ordering: sort services by first_seen ascending,
  assign 0 to earliest (root trigger), 1 to next, 2 to next, etc.
  NEVER assign the same cascade_depth to multiple services unless first_seen timestamps are identical.
  The service with the lowest first_seen timestamp is always cascade_depth 0.

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
        self.thinking_text: str = ""

    async def run(self, timeline: IncidentTimeline) -> list[ServiceCorrelation]:
        prompt = (
            f"Find service error correlation for incident {timeline.correlation_id}.\n"
            f"Time window: {timeline.start_time.isoformat()} → {timeline.end_time.isoformat()}\n"
            f"Services seen in timeline: {', '.join(timeline.services_involved)}\n\n"
            "Call service_error_correlation. Return correlations JSON."
        )

        from agent.runner_utils import run_agent_with_thinking
        tools, toolset = await get_agent_builder_tools(_TOOLS)
        try:
            result_text, self.thinking_text = await run_agent_with_thinking(
                self._model, "correlation_engine", _INSTRUCTION, tools, prompt
            )
        finally:
            await toolset.close()

        correlations = _parse_llm_response(result_text)
        if correlations is None:
            return []
        correlations = sorted(correlations, key=lambda c: c.cascade_depth)
        # Enforce unique depths if LLM assigned all 0 — re-rank by first_seen
        depths = [c.cascade_depth for c in correlations]
        if len(set(depths)) == 1 and len(correlations) > 1:
            ordered = sorted(correlations, key=lambda c: (c.first_seen or datetime.max))
            for i, c in enumerate(ordered):
                c.cascade_depth = i
            correlations = ordered
        return correlations
