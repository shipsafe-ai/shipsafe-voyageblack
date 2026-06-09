"""Create Elasticsearch index mappings with semantic_text for ELSER auto-embedding.

On Elastic Serverless, logs-* indices must be data streams (built-in template enforces this).
We create a component template + index template to define the mapping, then data streams
are auto-created on first write.

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

COMPONENT_TEMPLATE = "voyageblack-logs-mappings"
INDEX_TEMPLATE = "voyageblack-logs"
POSTMORTEMS_INDEX = "postmortems-shipsafe"

LOGS_PROPERTIES = {
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


def put(client: httpx.Client, path: str, body: dict) -> httpx.Response:
    return client.put(f"{config.ELASTIC_CLOUD_URL}{path}", json=body)


def create_component_template(client: httpx.Client) -> None:
    resp = put(client, f"/_component_template/{COMPONENT_TEMPLATE}", {
        "template": {"mappings": {"properties": LOGS_PROPERTIES}}
    })
    if resp.status_code in (200, 201):
        print(f"  ✓ Component template: {COMPONENT_TEMPLATE}")
    else:
        print(f"  ✗ Component template failed ({resp.status_code}): {resp.text[:200]}")
        sys.exit(1)


def create_index_template(client: httpx.Client) -> None:
    resp = put(client, f"/_index_template/{INDEX_TEMPLATE}", {
        "index_patterns": ["logs-hormuz-*", "logs-generic-*", "logs-auth-*"],
        "data_stream": {},
        "composed_of": [COMPONENT_TEMPLATE],
        "priority": 500,
    })
    if resp.status_code in (200, 201):
        print(f"  ✓ Index template: {INDEX_TEMPLATE} (matches logs-hormuz-*, logs-generic-*, logs-auth-*)")
    else:
        print(f"  ✗ Index template failed ({resp.status_code}): {resp.text[:200]}")
        sys.exit(1)


def create_postmortems_index(client: httpx.Client) -> None:
    resp = put(client, f"/{POSTMORTEMS_INDEX}", POSTMORTEMS_MAPPING)
    if resp.status_code in (200, 201):
        print(f"  ✓ Created: {POSTMORTEMS_INDEX}")
    elif resp.status_code == 400 and "resource_already_exists_exception" in resp.text:
        print(f"  ~ Exists:  {POSTMORTEMS_INDEX} (skipped)")
    else:
        print(f"  ✗ Failed:  {POSTMORTEMS_INDEX} ({resp.status_code}): {resp.text[:200]}")
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
        create_component_template(client)
        create_index_template(client)
        create_postmortems_index(client)

    print("\nDone. Data streams auto-create on first write via index template.")
    print("ELSER will auto-embed semantic_content on ingest.")
    print(f"Next: python scripts/load_fixtures.py")


if __name__ == "__main__":
    main()
