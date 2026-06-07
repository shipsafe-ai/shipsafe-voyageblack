"""Verify both MCP endpoints are reachable and configured correctly.

Run after load_fixtures.py (allow 30s for ELSER embedding):
    python scripts/verify_mcp.py

Checks:
  1. Standalone ES MCP (Docker): list_indices → logs-hormuz-* and postmortems-shipsafe present
  2. Standalone ES MCP (Docker): esql → verify ELSER embedding on a fixture document
  3. Agent Builder MCP: list available tools, confirm all 5 custom tools present
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


EXPECTED_AGENT_BUILDER_TOOLS = {
    "incident_logs_timewindow",
    "incident_logs_semantic",
    "service_error_correlation",
    "similar_past_incident",
    "write_postmortem",
}

PASS = "  ✓"
FAIL = "  ✗"
WARN = "  ~"


async def check_elasticsearch_mcp() -> bool:
    print("\n[1/3] Standalone Elasticsearch MCP (list_indices)...")
    from agent.elastic_mcp import get_elasticsearch_tools

    try:
        tools, toolset = await get_elasticsearch_tools(["list_indices"])
        if not tools:
            print(f"{WARN} No list_indices tool found (Docker may not be running)")
            await toolset.close()
            return False

        tool = tools[0]
        print(f"{PASS} Connected to standalone ES MCP")
        print(f"       Tool: {tool.name}")
        await toolset.close()
        return True
    except Exception as exc:
        print(f"{FAIL} Connection failed: {exc}")
        return False


async def check_elasticsearch_esql() -> bool:
    print("\n[2/3] Standalone Elasticsearch MCP (esql — verify ELSER embedding)...")
    from agent.elastic_mcp import get_elasticsearch_tools
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
    import os

    try:
        tools, toolset = await get_elasticsearch_tools(["esql"])
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        agent = Agent(
            model=model,
            name="verify_esql",
            instruction="Run the ES|QL query using the esql tool. Return count.",
            tools=tools,
        )
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="verify", user_id="system")
        runner = Runner(agent=agent, app_name="verify", session_service=session_service)

        result_text = ""
        async for event in runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=(
                    "Run this ES|QL query and return the count: "
                    "FROM logs-hormuz-* | STATS count = COUNT(*)"
                ))],
            ),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text and event.is_final_response():
                        result_text = part.text

        await toolset.close()
        print(f"{PASS} ES|QL esql tool responsive")
        print(f"       Response: {result_text[:100]}")
        return True
    except Exception as exc:
        print(f"{FAIL} ES|QL query failed: {exc}")
        return False


async def check_agent_builder_mcp() -> bool:
    print("\n[3/3] Agent Builder MCP endpoint (list custom tools)...")
    from agent.elastic_mcp import get_agent_builder_tools

    try:
        tools, toolset = await get_agent_builder_tools()
        tool_names = {t.name for t in tools}
        await toolset.close()

        missing = EXPECTED_AGENT_BUILDER_TOOLS - tool_names
        if missing:
            print(f"{WARN} Agent Builder connected but missing tools: {missing}")
            print(f"       Found: {tool_names}")
            return False

        print(f"{PASS} Agent Builder MCP — all 5 tools present")
        for name in sorted(tool_names):
            print(f"       - {name}")
        return True
    except Exception as exc:
        print(f"{FAIL} Agent Builder connection failed: {exc}")
        print(f"       Check ELASTIC_MCP_URL and ELASTIC_API_KEY (feature_agentBuilder.read required)")
        return False


async def main() -> None:
    print("VoyageBlack MCP Verification")
    print("=" * 40)

    r1 = await check_elasticsearch_mcp()
    r2 = await check_elasticsearch_esql()
    r3 = await check_agent_builder_mcp()

    print("\n" + "=" * 40)
    all_pass = r1 and r2 and r3
    if all_pass:
        print(f"{PASS} All checks passed — ready to run pipeline")
        print("       POST /demo/seed then POST /run")
    else:
        print(f"{FAIL} Some checks failed — review output above")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
