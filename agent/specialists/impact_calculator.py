"""ImpactCalculator — blast radius via standalone Elasticsearch MCP (esql tool).

Demonstrates deep integration with docker.elastic.co/mcp/elasticsearch in addition
to the Agent Builder MCP used by other specialists.
"""

from __future__ import annotations

import json
import os
import re

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from agent.elastic_mcp import get_elasticsearch_tools
from agent.models import BlastRadius, IncidentTimeline, ServiceCorrelation

_TOOLS = ["esql"]

_INSTRUCTION = """\
You are ImpactCalculator, blast radius analyst for VoyageBlack.

Use the esql tool to run ES|QL aggregation queries against the logs-hormuz-* index.
Run this query (substitute actual start_time and end_time values):

  FROM logs-hormuz-*
  | WHERE @timestamp >= "START_TIME" AND @timestamp <= "END_TIME"
  | STATS
      total_errors = COUNT(*),
      services_hit = COUNT_DISTINCT(service),
      by level
  | SORT total_errors DESC

Also run a per-service error rate query:

  FROM logs-hormuz-*
  | WHERE @timestamp >= "START_TIME" AND @timestamp <= "END_TIME"
  | STATS
      total = COUNT(*),
      errors = COUNT_IF(level IN ("CRITICAL","ERROR"))
      BY service
  | EVAL error_rate_pct = ROUND(errors * 100.0 / total, 1)
  | SORT errors DESC

Use results to compute:
- total_errors: sum of all CRITICAL+ERROR log counts
- services_affected: count of distinct services with errors
- error_rate_per_service: {service_name: error_rate_pct}
- estimated_duration_minutes: (end_time - start_time) in minutes
- cascade_chain: services ordered by first error timestamp (earliest first)

Return ONLY this JSON (no prose, no markdown fences):
{
  "total_errors": integer,
  "services_affected": integer,
  "error_rate_per_service": {"service": float},
  "estimated_duration_minutes": float,
  "cascade_chain": ["service"]
}\
"""


def _parse_llm_response(text: str) -> BlastRadius | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    for candidate in [text, *re.findall(r"\{[\s\S]*\}", text)]:
        try:
            return BlastRadius.model_validate_json(candidate)
        except Exception:
            pass
        try:
            return BlastRadius(**json.loads(candidate))
        except Exception:
            pass
    return None


def _fallback(timeline: IncidentTimeline, correlations: list[ServiceCorrelation]) -> BlastRadius:
    total = sum(c.error_count for c in correlations)
    duration = (timeline.end_time - timeline.start_time).total_seconds() / 60.0
    chain = [c.service for c in sorted(correlations, key=lambda c: c.cascade_depth)]
    return BlastRadius(
        total_errors=total,
        services_affected=len(correlations),
        error_rate_per_service={},
        estimated_duration_minutes=round(duration, 1),
        cascade_chain=chain,
    )


class ImpactCalculator:
    """Calculates blast radius via standalone ES MCP server (esql tool).

    Uses docker.elastic.co/mcp/elasticsearch esql tool for raw ES|QL aggregations.
    This is deliberately different from Agent Builder tools — demonstrating both
    MCP servers are in production use.
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.thinking_text: str = ""

    async def run(
        self,
        timeline: IncidentTimeline,
        correlations: list[ServiceCorrelation],
        thinking_queue=None,
    ) -> BlastRadius:
        duration_min = (timeline.end_time - timeline.start_time).total_seconds() / 60.0
        prompt = (
            f"Calculate blast radius for incident {timeline.correlation_id}.\n"
            f"Time window: {timeline.start_time.isoformat()} → {timeline.end_time.isoformat()}\n"
            f"Duration: {duration_min:.1f} minutes\n"
            f"Services with errors: {[c.service for c in correlations]}\n\n"
            "Use the esql tool to run aggregation queries. "
            "Substitute actual ISO timestamps in the WHERE clauses. "
            "Return BlastRadius JSON."
        )

        instruction = _INSTRUCTION.replace("START_TIME", timeline.start_time.isoformat())
        instruction = instruction.replace("END_TIME", timeline.end_time.isoformat())

        from agent.runner_utils import run_agent_with_thinking
        tools, toolset = await get_elasticsearch_tools(_TOOLS)
        try:
            result_text, self.thinking_text = await run_agent_with_thinking(
                self._model, "impact_calculator", instruction, tools, prompt,
                thinking_queue=thinking_queue,
            )
        finally:
            await toolset.close()

        blast = _parse_llm_response(result_text)
        if blast is None or (blast.total_errors == 0 and blast.services_affected == 0 and correlations):
            return _fallback(timeline, correlations)
        return blast
