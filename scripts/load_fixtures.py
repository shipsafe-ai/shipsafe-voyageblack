"""Load Hormuz crisis log fixtures + seed past postmortem to Elasticsearch.

Run after create_mappings.py:
    python scripts/load_fixtures.py

Loads:
  - 9 Hormuz crisis log entries → logs-hormuz-2026.06.01
  - 1 seeded past postmortem (Red Sea 2024) → postmortems-shipsafe

After loading, wait ~30s for ELSER to embed semantic_content fields before querying.
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from agent import config

LOGS_INDEX = "logs-hormuz-2026.06.01"
POSTMORTEMS_INDEX = "postmortems-shipsafe"

# Seeded past postmortem — gives similar_past_incident something to return on first demo
RED_SEA_POSTMORTEM = {
    "incident_id": "REDSEA-2024-1210",
    "title": "Red Sea shipping disruption — Houthi threat response",
    "root_cause": (
        "Regional security advisory triggered mass rerouting without validated fallback routes. "
        "AI routing model had not been tested against Bab-el-Mandeb closure scenario."
    ),
    "timeline_summary": (
        "2024-12-10 09:00Z: UKMTO advisory issued for Red Sea transit risk. "
        "2024-12-10 09:15Z: Routing engine failover triggered for 47 vessels. "
        "2024-12-10 09:30Z: Cape of Good Hope diversions activated."
    ),
    "services_affected": ["routing-engine", "naviguard", "cargo-tracker"],
    "severity": "CRITICAL",
    "status": "written",
    "recommendations": [
        "Pre-validate Cape of Good Hope diversion routes quarterly.",
        "Add UKMTO advisory feed as high-priority routing signal.",
    ],
    "created_at": "2024-12-10T12:00:00Z",
}


def build_bulk_body(entries: list[dict]) -> str:
    lines = []
    for entry in entries:
        action = {"index": {"_index": LOGS_INDEX}}
        doc = {
            "@timestamp": entry["timestamp"],
            "service": entry["service"],
            "level": entry["level"],
            "message": entry["message"],
            "correlation_id": "HORMUZ-2026-0601",
            "event_id": entry.get("event_id"),
            "error_code": entry.get("error_code"),
        }
        lines.append(json.dumps(action))
        lines.append(json.dumps(doc))
    return "\n".join(lines) + "\n"


def main() -> None:
    if not config.ELASTIC_CLOUD_URL or not config.ELASTIC_API_KEY:
        print("ERROR: ELASTIC_CLOUD_URL and ELASTIC_API_KEY must be set.")
        sys.exit(1)

    try:
        from shipsafe_shared.demo_data.hormuz_crisis import LOG_ENTRIES
    except ImportError:
        shipsafe_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "shipsafe-shared"
        )
        sys.path.insert(0, shipsafe_path)
        from shipsafe_shared.demo_data.hormuz_crisis import LOG_ENTRIES

    headers = {
        "Authorization": f"ApiKey {config.ELASTIC_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(headers=headers, timeout=60.0) as client:
        # Bulk ingest log entries
        print(f"Loading {len(LOG_ENTRIES)} log entries → {LOGS_INDEX}...")
        bulk_body = build_bulk_body(LOG_ENTRIES)
        resp = client.post(
            f"{config.ELASTIC_CLOUD_URL}/_bulk",
            content=bulk_body,
            headers={**headers, "Content-Type": "application/x-ndjson"},
        )
        if resp.status_code >= 400:
            print(f"  ✗ Bulk failed ({resp.status_code}): {resp.text[:300]}")
            sys.exit(1)
        result = resp.json()
        errors = [i for i in result.get("items", []) if i.get("index", {}).get("error")]
        if errors:
            print(f"  ✗ {len(errors)} bulk errors: {errors[0]}")
            sys.exit(1)
        print(f"  ✓ Indexed {len(LOG_ENTRIES)} documents")

        # Seed past postmortem
        print(f"Seeding past postmortem → {POSTMORTEMS_INDEX}...")
        resp = client.post(
            f"{config.ELASTIC_CLOUD_URL}/{POSTMORTEMS_INDEX}/_doc/REDSEA-2024-1210",
            json=RED_SEA_POSTMORTEM,
        )
        if resp.status_code in (200, 201):
            print("  ✓ Seeded: REDSEA-2024-1210")
        else:
            print(f"  ✗ Seed failed ({resp.status_code}): {resp.text[:200]}")

    # Parseable summary line for /demo/seed endpoint
    print(f"SEEDED_COUNT:{len(LOG_ENTRIES)}")
    print("\nDone. Wait ~30s for ELSER to embed semantic_content fields.")
    print("Then: python scripts/verify_mcp.py")


if __name__ == "__main__":
    main()
