"""Create Elasticsearch index mappings with semantic_text for ELSER auto-embedding.

Run ONCE before loading fixtures:
    python scripts/create_mappings.py

Requires: ELASTIC_CLOUD_URL, ELASTIC_API_KEY in env or GCP Secret Manager.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from agent import config

LOGS_INDEX = "logs-hormuz-2026.06.01"
POSTMORTEMS_INDEX = "postmortems-shipsafe"

LOGS_MAPPING = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "service": {"type": "keyword"},
            "level": {"type": "keyword"},
            "message": {"type": "text", "copy_to": "semantic_content"},
            "correlation_id": {"type": "keyword"},
            "error_code": {"type": "keyword"},
            "duration_ms": {"type": "long"},
            "event_id": {"type": "keyword"},
            "semantic_content": {
                "type": "semantic_text",
                "inference_id": ".elser-2-elasticsearch",
            },
        }
    }
}

POSTMORTEMS_MAPPING = {
    "mappings": {
        "properties": {
            "incident_id": {"type": "keyword"},
            "title": {"type": "text", "copy_to": "semantic_content"},
            "root_cause": {"type": "text", "copy_to": "semantic_content"},
            "timeline_summary": {"type": "text", "copy_to": "semantic_content"},
            "services_affected": {"type": "keyword"},
            "created_at": {"type": "date"},
            "severity": {"type": "keyword"},
            "status": {"type": "keyword"},
            "recommendations": {"type": "text", "copy_to": "semantic_content"},
            "semantic_content": {
                "type": "semantic_text",
                "inference_id": ".elser-2-elasticsearch",
            },
        }
    }
}


def create_index(client: httpx.Client, index: str, mapping: dict) -> None:
    url = f"{config.ELASTIC_CLOUD_URL}/{index}"
    resp = client.put(url, json=mapping)
    if resp.status_code == 200:
        print(f"  ✓ Created: {index}")
    elif resp.status_code == 400 and "resource_already_exists_exception" in resp.text:
        print(f"  ~ Exists:  {index} (skipped)")
    else:
        print(f"  ✗ Failed:  {index} ({resp.status_code}): {resp.text[:200]}")
        sys.exit(1)


def main() -> None:
    if not config.ELASTIC_CLOUD_URL or not config.ELASTIC_API_KEY:
        print("ERROR: ELASTIC_CLOUD_URL and ELASTIC_API_KEY must be set.")
        sys.exit(1)

    headers = {
        "Authorization": f"ApiKey {config.ELASTIC_API_KEY}",
        "Content-Type": "application/json",
    }

    print("Creating Elasticsearch index mappings...")
    with httpx.Client(headers=headers, timeout=30.0) as client:
        create_index(client, LOGS_INDEX, LOGS_MAPPING)
        create_index(client, POSTMORTEMS_INDEX, POSTMORTEMS_MAPPING)

    print("\nDone. ELSER will auto-embed semantic_content on first ingest.")
    print(f"Next: python scripts/load_fixtures.py")


if __name__ == "__main__":
    main()
