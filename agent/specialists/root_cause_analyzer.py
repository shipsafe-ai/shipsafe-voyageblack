"""RootCauseAnalyzer — pure Gemini reasoning over structured specialist outputs."""

from __future__ import annotations

import json
import os
import re

from agent.models import BlastRadius, IncidentTimeline, RootCauseHypothesis, ServiceCorrelation

_INSTRUCTION = """\
You are RootCauseAnalyzer, incident root cause expert for VoyageBlack.

You receive structured data (JSON) from upstream specialists — NOT raw log text.
Use your reasoning to identify the primary cause and contributing factors.

Evidence quality guide:
- Cascade depth 0 correlations = potential root cause services
- Events tightly clustered in time after an anomaly = indicators, not causes
- high cascade_depth + early timestamp = cascading victim, not origin

Return ONLY this JSON (no prose, no markdown fences):
{
  "primary_cause": "string — one sentence, specific",
  "contributing_factors": ["string"],
  "confidence": float between 0.0 and 1.0,
  "evidence": ["string — cite specific event_id (e.g. EVT-004) or a metric (e.g. 'cargo-tracker: 3 CRITICAL errors'). Do NOT include raw JSON."],
  "recommendations": [
    "string — specific, actionable recommendation derived from the evidence above",
    "string — each item must reference a specific service, pattern, or failure mode found in the data"
  ]
}\
"""


def _parse_llm_response(text: str) -> RootCauseHypothesis | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    for candidate in [text, *re.findall(r"\{[\s\S]*\}", text)]:
        try:
            return RootCauseHypothesis.model_validate_json(candidate)
        except Exception:
            pass
        try:
            return RootCauseHypothesis(**json.loads(candidate))
        except Exception:
            pass
    return None


def _fallback(timeline: IncidentTimeline, correlations: list[ServiceCorrelation]) -> RootCauseHypothesis:
    root_svc = correlations[0].service if correlations else "unknown"
    return RootCauseHypothesis(
        primary_cause=f"Root cause analysis unavailable — suspected origin: {root_svc}",
        contributing_factors=[c.service for c in correlations[1:3]],
        confidence=0.0,
        evidence=[],
    )


class RootCauseAnalyzer:
    """Pure Gemini reasoning — no MCP tools.

    Receives structured outputs from TimelineBuilder, CorrelationEngine, and
    ImpactCalculator. Never receives raw log content directly — only sanitized
    structured data to prevent prompt injection.
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.thinking_text: str = ""

    async def run(
        self,
        timeline: IncidentTimeline,
        correlations: list[ServiceCorrelation],
        blast_radius: BlastRadius,
        thinking_queue=None,
    ) -> RootCauseHypothesis:
        # Pass structured data only — no raw log messages concatenated
        structured_input = {
            "incident_id": timeline.correlation_id,
            "duration_minutes": blast_radius.estimated_duration_minutes,
            "services_involved": timeline.services_involved,
            "cascade_chain": blast_radius.cascade_chain,
            "correlations": [
                {
                    "service": c.service,
                    "error_count": c.error_count,
                    "error_codes": c.error_codes,
                    "cascade_depth": c.cascade_depth,
                }
                for c in correlations
            ],
            "timeline_event_count": len(timeline.entries),
            "event_ids_with_errors": [
                e.event_id for e in timeline.entries
                if e.level in ("CRITICAL", "ERROR") and e.event_id
            ],
        }

        prompt = (
            "Analyze incident root cause from structured specialist data.\n\n"
            f"=== Structured Data ===\n{json.dumps(structured_input, indent=2)}\n\n"
            "Identify primary_cause, contributing_factors, confidence, evidence. "
            "Return RootCauseHypothesis JSON."
        )

        try:
            from agent.runner_utils import run_gemini_direct_with_thinking
            result_text, self.thinking_text = await run_gemini_direct_with_thinking(
                self._model, _INSTRUCTION, prompt,
                thinking_queue=thinking_queue,
            )
        except Exception:
            if thinking_queue is not None:
                await thinking_queue.put(None)  # ensure sentinel on error
            return _fallback(timeline, correlations)

        hypothesis = _parse_llm_response(result_text)
        if hypothesis is None:
            return _fallback(timeline, correlations)
        return hypothesis
