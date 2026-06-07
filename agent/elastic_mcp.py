"""MCP toolset factories for VoyageBlack.

Two MCP servers:
  1. Agent Builder MCP (SseConnectionParams) — 5 custom domain tools defined in Kibana UI
  2. Standalone ES MCP (StdioServerParameters locally, StreamableHTTPConnectionParams in Cloud Run)
     Tools: list_indices, get_mappings, search, esql, get_shards
"""

from __future__ import annotations

import os

from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    SseConnectionParams,
    StdioServerParameters,
    StreamableHTTPConnectionParams,
)

from agent import config


async def get_agent_builder_tools(
    tool_names: list[str] | None = None,
) -> tuple[list, McpToolset]:
    """Connect to Elastic Agent Builder MCP endpoint, return (tools, toolset).

    Caller MUST call toolset.close() when done.
    Tools available: incident_logs_timewindow, incident_logs_semantic,
    service_error_correlation, similar_past_incident, write_postmortem.
    """
    toolset = McpToolset(
        connection_params=SseConnectionParams(
            url=config.ELASTIC_MCP_URL,
            headers={"Authorization": f"ApiKey {config.ELASTIC_API_KEY}"},
            timeout=30.0,
            sse_read_timeout=120.0,
        )
    )
    tools = await toolset.get_tools()
    if tool_names:
        tools = [t for t in tools if t.name in tool_names]
    return tools, toolset


async def get_elasticsearch_tools(
    tool_names: list[str] | None = None,
) -> tuple[list, McpToolset]:
    """Connect to standalone Elasticsearch MCP server, return (tools, toolset).

    Local dev: spawns docker.elastic.co/mcp/elasticsearch via Docker stdio.
    Cloud Run: connects to es-mcp-server Cloud Run service via streamable-HTTP.

    Caller MUST call toolset.close() when done.
    Tools available: list_indices, get_mappings, search, esql, get_shards.
    """
    if config.ELASTIC_ES_MCP_URL:
        params = StreamableHTTPConnectionParams(
            url=config.ELASTIC_ES_MCP_URL,
            headers={"Authorization": f"ApiKey {config.ELASTIC_API_KEY}"},
            timeout=30.0,
        )
    else:
        params = StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "ES_URL",
                "-e", "ES_API_KEY",
                "docker.elastic.co/mcp/elasticsearch",
                "stdio",
            ],
            env={
                **os.environ,
                "ES_URL": config.ELASTIC_CLOUD_URL,
                "ES_API_KEY": config.ELASTIC_API_KEY,
            },
        )

    toolset = McpToolset(connection_params=params)
    tools = await toolset.get_tools()
    if tool_names:
        tools = [t for t in tools if t.name in tool_names]
    return tools, toolset
