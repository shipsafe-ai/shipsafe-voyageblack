"""Configuration — reads from env vars, falls back to GCP Secret Manager."""

from __future__ import annotations

import os


def _get_secret(name: str) -> str:
    """Read from env first, then GCP Secret Manager."""
    val = os.environ.get(name, "")
    if val:
        return val
    try:
        from google.cloud import secretmanager
        project = os.environ.get("GCP_PROJECT", "shipsafe-ai")
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{project}/secrets/{name}/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        return response.payload.data.decode("utf-8").strip()
    except Exception:
        return ""


ELASTIC_CLOUD_URL: str = _get_secret("ELASTIC_CLOUD_URL")
ELASTIC_API_KEY: str = _get_secret("ELASTIC_API_KEY")
ELASTIC_MCP_URL: str = _get_secret("ELASTIC_MCP_URL")           # Agent Builder SSE endpoint
ELASTIC_ES_MCP_URL: str = _get_secret("ELASTIC_ES_MCP_URL")     # Standalone ES MCP HTTP (Cloud Run)

GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GCP_PROJECT: str = os.environ.get("GCP_PROJECT", "shipsafe-ai")
GCP_REGION: str = os.environ.get("GCP_REGION", "us-central1")
