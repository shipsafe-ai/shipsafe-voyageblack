"""ReportWriter — finds similar past incidents and writes postmortems via Agent Builder MCP."""

from __future__ import annotations

import json
import os
import re

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from agent.elastic_mcp import get_agent_builder_tools
from agent.models import PostmortemDraft, SimilarIncident

_SIMILAR_TOOLS = ["similar_past_incident"]
_WRITE_TOOLS = ["write_postmortem"]

_FIND_INSTRUCTION = """\
You are ReportWriter (find mode), postmortem researcher for VoyageBlack.

Call similar_past_incident with the incident description to search the postmortems-shipsafe
Elasticsearch index using ELSER semantic similarity.

Return ONLY this JSON (no prose, no markdown fences):
{
  "similar_incidents": [
    {
      "id": "string",
      "title": "string",
      "similarity_score": float between 0.0 and 1.0,
      "root_cause": "string",
      "resolution": "string"
    }
  ]
}\
"""

_WRITE_INSTRUCTION = """\
You are ReportWriter (write mode), postmortem publisher for VoyageBlack.

You have received an approved PostmortemDraft (JSON). Call write_postmortem to index
it to the postmortems-shipsafe Elasticsearch index.

The write_postmortem tool will return the document_id on success.

Return ONLY this JSON (no prose, no markdown fences):
{
  "document_id": "string",
  "status": "written"
}\
"""


def _parse_similar_incidents(text: str) -> list[SimilarIncident] | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    for candidate in [text, *re.findall(r"\{[\s\S]*\}", text)]:
        try:
            data = json.loads(candidate)
            if "similar_incidents" in data:
                return [SimilarIncident(**s) for s in data["similar_incidents"]]
        except Exception:
            pass
    return None


def _parse_write_response(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    for candidate in [text, *re.findall(r"\{[\s\S]*\}", text)]:
        try:
            data = json.loads(candidate)
            return data.get("document_id")
        except Exception:
            pass
    return None


async def _run_agent(model: str, name: str, instruction: str, tools: list, prompt: str) -> str:
    agent = Agent(model=model, name=name, instruction=instruction, tools=tools)
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="voyageblack", user_id="system")
    runner = Runner(agent=agent, app_name="voyageblack", session_service=session_service)

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
    return result_text or _json_fallback


class ReportWriter:
    """Searches postmortems index for similar incidents and writes approved postmortems.

    Both operations use Agent Builder MCP tools:
    - find_similar: similar_past_incident (ELSER semantic search over postmortems-shipsafe)
    - write: write_postmortem (upsert to postmortems-shipsafe — ONLY after human approval)
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    async def find_similar(self, draft: PostmortemDraft) -> list[SimilarIncident]:
        """Search postmortems-shipsafe for semantically similar past incidents."""
        query = (
            f"{draft.root_cause.primary_cause} "
            f"{' '.join(draft.root_cause.contributing_factors[:2])}"
        )
        prompt = (
            f"Find similar past incidents for: incident_id={draft.incident_id}\n"
            f"Root cause query: {query}\n"
            f"Services: {', '.join(draft.timeline.services_involved)}\n\n"
            "Call similar_past_incident. Return similar_incidents JSON."
        )

        tools, toolset = await get_agent_builder_tools(_SIMILAR_TOOLS)
        try:
            result_text = await _run_agent(
                self._model, "report_writer_find", _FIND_INSTRUCTION, tools, prompt
            )
        finally:
            await toolset.close()

        similar = _parse_similar_incidents(result_text)
        return similar if similar is not None else []

    async def write(self, draft: PostmortemDraft) -> str:
        """Write approved postmortem to postmortems-shipsafe.

        Uses Elasticsearch REST API directly — Agent Builder write_postmortem tool
        is "Index search" type (read-only MCP). Direct REST ensures the document is
        actually indexed with all fields so ELSER can embed semantic_content.
        MUST only be called after explicit human approval (POST /approve/{incident_id}).
        """
        import httpx
        from agent import config

        doc = {
            "incident_id": draft.incident_id,
            "title": draft.title,
            "root_cause": draft.root_cause.primary_cause,
            "timeline_summary": " ".join([
                f"{e.timestamp.isoformat()} [{e.service}] {e.message}"
                for e in (draft.timeline.entries or [])[:5]
            ]),
            "services_affected": draft.timeline.services_involved,
            "severity": draft.severity,
            "status": "written",
            "recommendations": draft.recommendations,
            "created_at": draft.timeline.end_time.isoformat(),
        }

        url = f"{config.ELASTIC_CLOUD_URL}/postmortems-shipsafe/_doc/{draft.incident_id}"
        headers = {
            "Authorization": f"ApiKey {config.ELASTIC_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(url, json=doc, headers=headers)
            resp.raise_for_status()

        return draft.incident_id
