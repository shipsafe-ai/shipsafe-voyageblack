"""MCP toolset factories for VoyageBlack.

Two MCP servers:
  1. Agent Builder MCP (SseConnectionParams) — 5 custom domain tools defined in Kibana UI
  2. Standalone ES MCP (StdioServerParameters locally, StreamableHTTPConnectionParams in Cloud Run)
     Tools: list_indices, get_mappings, search, esql, get_shards
"""

from __future__ import annotations

import os
import urllib.request

from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    SseConnectionParams,
    StdioServerParameters,
    StreamableHTTPConnectionParams,
)

from agent import config


def _cloud_run_id_token(audience: str) -> str:
    """Fetch Google OIDC identity token from GCE metadata server for Cloud Run auth."""
    url = (
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        f"service-accounts/default/identity?audience={audience}"
    )
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode()


async def get_agent_builder_tools(
    tool_names: list[str] | None = None,
) -> tuple[list, McpToolset]:
    """Connect to Elastic Agent Builder MCP endpoint, return (tools, toolset).

    Agent Builder MCP uses streamable HTTP (POST), not SSE.
    Caller MUST call toolset.close() when done.
    Tools available: incident_logs_timewindow, incident_logs_semantic,
    service_error_correlation, similar_past_incident, write_postmortem.
    """
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=config.ELASTIC_MCP_URL,
            headers={"Authorization": f"ApiKey {config.ELASTIC_API_KEY}"},
            timeout=30.0,
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
        # Cloud Run service-to-service auth requires Google OIDC identity token.
        # Audience is the base service URL (strip /mcp path).
        audience = config.ELASTIC_ES_MCP_URL.removesuffix("/mcp").removesuffix("/")
        try:
            token = _cloud_run_id_token(audience)
            auth_headers = {"Authorization": f"Bearer {token}"}
        except Exception as e:
            import logging
            logging.warning("OIDC token fetch failed for %s: %s", audience, e)
            auth_headers = {}
        params = StreamableHTTPConnectionParams(
            url=config.ELASTIC_ES_MCP_URL,
            headers=auth_headers,
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
