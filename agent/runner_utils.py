"""Shared runner helpers with Gemini thinking token collection."""

from __future__ import annotations

import asyncio
import os

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types


async def run_agent_with_thinking(
    model: str,
    name: str,
    instruction: str,
    tools: list,
    prompt: str,
    thinking_queue: asyncio.Queue | None = None,
) -> tuple[str, str]:
    """Run ADK agent (for MCP-tool specialists).

    Returns (response_text, thinking_text).
    If thinking_queue is provided, each thinking chunk is put into it as it arrives.
    A None sentinel is always put last so consumers can detect completion.
    """
    agent = Agent(
        model=model,
        name=name,
        instruction=instruction,
        tools=tools,
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(include_thoughts=True)
        ),
    )
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="voyageblack", user_id="system")
    runner = Runner(agent=agent, app_name="voyageblack", session_service=session_service)

    result_text = ""
    _json_fallback = ""
    thinking_parts: list[str] = []

    try:
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
                    is_thought = getattr(part, "thought", False)
                    text = getattr(part, "text", "") or ""
                    if is_thought and text:
                        thinking_parts.append(text)
                        if thinking_queue is not None:
                            await thinking_queue.put(text)
                    elif text:
                        if event.is_final_response():
                            result_text = text
                        elif "{" in text:
                            _json_fallback = text
    finally:
        if thinking_queue is not None:
            await thinking_queue.put(None)  # sentinel — always signal done

    return (result_text or _json_fallback), "\n\n".join(thinking_parts)


async def run_gemini_direct_with_thinking(
    model: str,
    system_instruction: str,
    prompt: str,
    thinking_queue: asyncio.Queue | None = None,
) -> tuple[str, str]:
    """Direct google.genai API call — reliably captures thought parts.

    Use for no-tool specialists (RootCauseAnalyzer, Critic) where ADK is
    unnecessary and doesn't reliably expose thought parts through events.
    Returns (response_text, thinking_text).
    """
    from google import genai

    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    if use_vertex:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "shipsafe-ai"))
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        client = genai.Client(vertexai=True, project=project, location=location)
    else:
        client = genai.Client()

    # thinking_budget enables thinking on Vertex AI; include_thoughts returns thought parts
    try:
        thinking_cfg = genai_types.ThinkingConfig(include_thoughts=True, thinking_budget=4096)
    except TypeError:
        thinking_cfg = genai_types.ThinkingConfig(include_thoughts=True)

    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            thinking_config=thinking_cfg,
        ),
    )

    result_text = ""
    thinking_parts: list[str] = []

    try:
        if response.candidates:
            for part in response.candidates[0].content.parts:
                # thought=True marks thinking tokens; check both attribute and dict form
                is_thought = getattr(part, "thought", None) or (
                    hasattr(part, "__dict__") and part.__dict__.get("thought")
                )
                text = getattr(part, "text", "") or ""
                if is_thought and text:
                    thinking_parts.append(text)
                    if thinking_queue is not None:
                        await thinking_queue.put(text)
                elif text:
                    result_text = text
    finally:
        if thinking_queue is not None:
            await thinking_queue.put(None)  # sentinel

    return result_text, "\n\n".join(thinking_parts)
