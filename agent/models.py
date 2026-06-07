"""Shared Pydantic models for VoyageBlack specialist pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TimelineEntry(BaseModel):
    timestamp: datetime
    service: str
    level: Literal["CRITICAL", "ERROR", "WARNING", "INFO"]
    message: str
    error_code: str | None = None
    duration_ms: int | None = None
    event_id: str | None = None


class IncidentTimeline(BaseModel):
    correlation_id: str
    start_time: datetime
    end_time: datetime
    entries: list[TimelineEntry] = Field(default_factory=list)
    services_involved: list[str] = Field(default_factory=list)


class ServiceCorrelation(BaseModel):
    service: str
    error_count: int = 0
    error_codes: list[str] = Field(default_factory=list)
    first_seen: datetime | None = None
    cascade_depth: int = 0


class BlastRadius(BaseModel):
    total_errors: int = 0
    services_affected: int = 0
    error_rate_per_service: dict[str, float] = Field(default_factory=dict)
    estimated_duration_minutes: float = 0.0
    cascade_chain: list[str] = Field(default_factory=list)


class RootCauseHypothesis(BaseModel):
    primary_cause: str = ""
    contributing_factors: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class SimilarIncident(BaseModel):
    id: str
    title: str
    similarity_score: float
    root_cause: str
    resolution: str


class PostmortemDraft(BaseModel):
    incident_id: str
    title: str = ""
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "HIGH"
    timeline: IncidentTimeline
    correlations: list[ServiceCorrelation] = Field(default_factory=list)
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    root_cause: RootCauseHypothesis = Field(default_factory=RootCauseHypothesis)
    similar_incidents: list[SimilarIncident] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    status: Literal["draft", "approved", "written"] = "draft"


class CriticVerdict(BaseModel):
    approved: bool = True
    injection_detected: bool = False
    injection_fields: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    risk_level: Literal["none", "low", "medium", "high", "critical"] = "none"
    reasoning: str = ""
    blocked_content: list[str] = Field(default_factory=list)
    confidence_multiplier: float = 1.0


class OrchestrationResult(BaseModel):
    draft: PostmortemDraft
    verdict: CriticVerdict
    approved: bool
    requires_human_review: bool
