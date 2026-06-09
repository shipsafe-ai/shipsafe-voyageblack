"""Shared ADK runner helper with Gemini thinking token collection."""

from __future__ import annotations

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
) -> tuple[str, str]:
    """Run ADK agent with Gemini thinking enabled.

    Returns (response_text, thinking_text). thinking_text contains Gemini's
    chain-of-thought tokens — empty string if model returns none.
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
                elif text:
                    if event.is_final_response():
                        result_text = text
                    elif "{" in text:
                        _json_fallback = text

    return (result_text or _json_fallback), "\n\n".join(thinking_parts)
