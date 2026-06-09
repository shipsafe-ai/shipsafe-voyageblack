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
        action = {"create": {"_index": LOGS_INDEX}}
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


LOG_ENTRIES = [
    {
        "timestamp": "2026-06-01T14:55:00Z",
        "service": "ukmto-feed",
        "level": "CRITICAL",
        "message": "UKMTO advisory UKMTO-2026-0601-004: Strait of Hormuz transit restriction in effect. "
                   "Mariners advised exercise extreme caution. Contact UKMTO on VHF Ch16.",
        "event_id": "EVT-001",
        "error_code": "UKMTO-ADVISORY",
    },
    {
        "timestamp": "2026-06-01T14:55:42Z",
        "service": "ais-receiver",
        "level": "WARNING",
        "message": "AIS signal loss for 3 vessels in grid 26.5N/56.4E. Possible jamming.",
        "event_id": "EVT-002",
        "error_code": "AIS-SIGNAL-LOSS",
    },
    {
        "timestamp": "2026-06-01T14:56:11Z",
        "service": "routing-engine",
        "level": "ERROR",
        "message": "Route recalculation failed for IMO 9811000 (Ever Given): "
                   "primary waypoint WP-HORMUZ-07 marked restricted. Fallback route unavailable.",
        "event_id": "EVT-003",
        "error_code": "ROUTE-RECALC-FAILED",
    },
    {
        "timestamp": "2026-06-01T14:57:03Z",
        "service": "cargo-tracker",
        "level": "ERROR",
        "message": "Manifest conflict: container MSCU1847392 scheduled for Jebel Ali offload "
                   "but vessel transit now blocked. Destination port SLA breach imminent.",
        "event_id": "EVT-004",
        "error_code": "SLA-BREACH-IMMINENT",
    },
    {
        "timestamp": "2026-06-01T14:58:29Z",
        "service": "routing-engine",
        "level": "WARNING",
        "message": "Algorithm change MR !447 merged. New Hormuz crisis avoidance logic active. "
                   "Scenario tests bypassed in merge. Rollback candidate.",
        "event_id": "EVT-005",
        "error_code": "UNSAFE-MERGE",
    },
    {
        "timestamp": "2026-06-01T14:59:01Z",
        "service": "fivetran-sync",
        "level": "ERROR",
        "message": "Jebel Ali port arrival feed: last record timestamp 2026-06-01T04:33:00Z. "
                   "Expected freshness < 1h. Current lag: 4h 26m. SLA breached.",
        "event_id": "EVT-006",
        "error_code": "FEED-STALENESS",
    },
    {
        "timestamp": "2026-06-01T15:00:17Z",
        "service": "naviguard",
        "level": "CRITICAL",
        "message": "AI routing model regression detected. Crisis avoidance score: 31% "
                   "(baseline: 72%). Delta: -41%. Confidence: 94. BLOCK verdict issued.",
        "event_id": "EVT-007",
        "error_code": "MODEL-REGRESSION",
    },
    {
        "timestamp": "2026-06-01T15:01:08Z",
        "service": "agentops",
        "level": "WARNING",
        "message": "CargoDB latency spike: p99 8830ms (baseline 1002ms, 8.8x). "
                   "Cascade source: AIS feed timeout propagating to memory recall.",
        "event_id": "EVT-008",
        "error_code": "LATENCY-SPIKE",
    },
    {
        "timestamp": "2026-06-01T15:02:00Z",
        "service": "operator-console",
        "level": "INFO",
        "message": "Operator decision requested. 23 conflicts active, 1 AI regression, "
                   "3 stale reports. All agent verdicts pending human approval.",
        "event_id": "EVT-009",
    },
]


def main() -> None:
    if not config.ELASTIC_CLOUD_URL or not config.ELASTIC_API_KEY:
        print("ERROR: ELASTIC_CLOUD_URL and ELASTIC_API_KEY must be set.")
        sys.exit(1)

    headers = {
        "Authorization": f"ApiKey {config.ELASTIC_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(headers=headers, timeout=300.0) as client:
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
        errors = [i for i in result.get("items", []) if i.get("create", {}).get("error")]
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
