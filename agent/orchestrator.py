"""VoyageBlack orchestrator — coordinates specialist pipeline in sequence."""

from __future__ import annotations

import os
from datetime import datetime

from google.adk.agents import Agent, SequentialAgent

from agent.critic import Critic
from agent.models import OrchestrationResult, PostmortemDraft
from agent.specialists.correlation_engine import CorrelationEngine
from agent.specialists.impact_calculator import ImpactCalculator
from agent.specialists.report_writer import ReportWriter
from agent.specialists.root_cause_analyzer import RootCauseAnalyzer
from agent.specialists.timeline_builder import TimelineBuilder

_PIPELINE_NODES = [
    ("timeline_builder",      "Reconstruct incident timeline from Elasticsearch logs"),
    ("correlation_engine",    "Find cross-service error correlations via ES|QL"),
    ("impact_calculator",     "Calculate blast radius via ES|QL aggregations"),
    ("root_cause_analyzer",   "Gemini reasoning over structured specialist outputs"),
    ("report_writer",         "Search similar past incidents; prepare postmortem"),
    ("critic",                "Prompt-injection defense and human approval gate"),
]


def build_sequential_agent(model: str) -> SequentialAgent:
    """Declare ADK SequentialAgent pipeline for compliance with Rule 2."""
    nodes = [
        Agent(model=model, name=name, instruction=desc, tools=[])
        for name, desc in _PIPELINE_NODES
    ]
    return SequentialAgent(
        name="voyageblack_orchestrator",
        description="VoyageBlack incident postmortem pipeline: timeline → correlation → impact → rootcause → writer → critic",
        sub_agents=nodes,
    )


class Orchestrator:
    """Coordinates VoyageBlack specialists in sequential pipeline.

    Execution order (Critic ALWAYS last):
      TimelineBuilder → CorrelationEngine → ImpactCalculator
      → RootCauseAnalyzer → ReportWriter.find_similar → Critic

    ReportWriter.write() is NOT called here — only via POST /approve/{incident_id}
    after explicit human approval (Rule 9).
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.sequential_agent = build_sequential_agent(self._model)
        self._timeline_builder = TimelineBuilder()
        self._correlation_engine = CorrelationEngine()
        self._impact_calculator = ImpactCalculator()
        self._root_cause_analyzer = RootCauseAnalyzer()
        self._report_writer = ReportWriter()
        self._critic = Critic()

    async def run(
        self,
        incident_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> OrchestrationResult:
        # Stage 1: reconstruct timeline
        timeline = await self._timeline_builder.run(
            incident_id=incident_id,
            start_time=start_time,
            end_time=end_time,
        )

        # Stage 2: cross-service error correlation
        correlations = await self._correlation_engine.run(timeline=timeline)

        # Stage 3: blast radius (standalone ES MCP)
        blast_radius = await self._impact_calculator.run(
            timeline=timeline,
            correlations=correlations,
        )

        # Stage 4: root cause reasoning (Gemini only, structured input)
        root_cause = await self._root_cause_analyzer.run(
            timeline=timeline,
            correlations=correlations,
            blast_radius=blast_radius,
        )

        # Stage 5: similar past incidents (Agent Builder similar_past_incident tool)
        similar_incidents = await self._report_writer.find_similar(
            draft=PostmortemDraft(
                incident_id=incident_id,
                timeline=timeline,
                correlations=correlations,
                blast_radius=blast_radius,
                root_cause=root_cause,
            )
        )

        draft = PostmortemDraft(
            incident_id=incident_id,
            title=f"Incident {incident_id} — {root_cause.primary_cause[:60]}",
            severity="CRITICAL" if blast_radius.services_affected >= 3 else "HIGH",
            timeline=timeline,
            correlations=correlations,
            blast_radius=blast_radius,
            root_cause=root_cause,
            similar_incidents=similar_incidents,
            recommendations=root_cause.recommendations,
            status="draft",
        )

        # Stage 6: Critic ALWAYS last
        verdict = await self._critic.review(draft)

        if verdict.injection_detected:
            verdict.approved = False

        return OrchestrationResult(
            draft=draft,
            verdict=verdict,
            approved=verdict.approved,
            requires_human_review=verdict.requires_human_review,
        )
