"""Load generic (non-maritime) incident fixtures to Elasticsearch.

Demonstrates VoyageBlack works for ANY ops team — not just maritime.
Scenario: OIDC token validation bug in auth-service cascades to payment-service
and notification-service during a Black Friday traffic spike.

Run after create_mappings.py (uses same index pattern):
    python scripts/load_generic_fixtures.py

This creates:
  - 11 log entries → logs-generic-2026.06.07
  - 1 seeded past postmortem (2025 AWS Cognito outage) → postmortems-shipsafe
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from agent import config

LOGS_INDEX = "logs-generic-2026.06.07"
POSTMORTEMS_INDEX = "postmortems-shipsafe"
CORRELATION_ID = "AUTH-OUTAGE-2026-0607"

# Cascade: auth-service OIDC bug → payment-service JWT rejects → notification queue backup
LOG_ENTRIES = [
    {
        "timestamp": "2026-06-07T09:01:00Z",
        "service": "auth-service",
        "level": "WARNING",
        "message": "OIDC token validation latency spike: p99=1840ms (threshold: 500ms)",
        "error_code": "OIDC_LATENCY_HIGH",
        "event_id": "AUTH-001",
    },
    {
        "timestamp": "2026-06-07T09:01:45Z",
        "service": "auth-service",
        "level": "ERROR",
        "message": "Token introspection endpoint returning 502 from identity provider — JWT signing key rotation in progress",
        "error_code": "OIDC_INTROSPECT_FAIL",
        "event_id": "AUTH-002",
    },
    {
        "timestamp": "2026-06-07T09:02:10Z",
        "service": "auth-service",
        "level": "CRITICAL",
        "message": "Token validation failure rate 34% — circuit breaker OPEN — new sessions rejected",
        "error_code": "AUTH_CIRCUIT_OPEN",
        "event_id": "AUTH-003",
    },
    {
        "timestamp": "2026-06-07T09:02:30Z",
        "service": "payment-service",
        "level": "ERROR",
        "message": "JWT verification failed: unable to fetch JWKS from auth-service — falling back to cached keys (age: 47min)",
        "error_code": "JWT_JWKS_FETCH_FAIL",
        "event_id": "PAY-001",
    },
    {
        "timestamp": "2026-06-07T09:02:50Z",
        "service": "payment-service",
        "level": "ERROR",
        "message": "Cached JWKS expired — all new payment requests returning HTTP 401 Unauthorized",
        "error_code": "JWKS_CACHE_EXPIRED",
        "event_id": "PAY-002",
    },
    {
        "timestamp": "2026-06-07T09:03:05Z",
        "service": "payment-service",
        "level": "CRITICAL",
        "message": "Payment processing halted — 0 transactions authorized in last 60s — checkout flow broken",
        "error_code": "PAYMENT_HALTED",
        "event_id": "PAY-003",
        "duration_ms": 60000,
    },
    {
        "timestamp": "2026-06-07T09:03:20Z",
        "service": "notification-service",
        "level": "ERROR",
        "message": "Order confirmation emails backed up — auth token for SMTP relay rejected — queue depth 4,200",
        "error_code": "SMTP_AUTH_FAIL",
        "event_id": "NOTIF-001",
    },
    {
        "timestamp": "2026-06-07T09:03:45Z",
        "service": "notification-service",
        "level": "ERROR",
        "message": "SQS consumer stalled — cannot dequeue without valid service token — DLQ growing at 180/min",
        "error_code": "SQS_CONSUMER_STALLED",
        "event_id": "NOTIF-002",
    },
    {
        "timestamp": "2026-06-07T09:04:00Z",
        "service": "api-gateway",
        "level": "ERROR",
        "message": "HTTP 401 rate spiking: 2,300/min — downstream services cannot validate bearer tokens",
        "error_code": "GATEWAY_AUTH_FLOOD",
        "event_id": "GW-001",
    },
    {
        "timestamp": "2026-06-07T09:05:00Z",
        "service": "auth-service",
        "level": "INFO",
        "message": "Identity provider key rotation complete — JWKS endpoint healthy — circuit breaker HALF-OPEN",
        "event_id": "AUTH-004",
    },
    {
        "timestamp": "2026-06-07T09:06:00Z",
        "service": "auth-service",
        "level": "INFO",
        "message": "Circuit breaker CLOSED — token validation success rate 99.8% — all services recovering",
        "event_id": "AUTH-005",
    },
]

# Past postmortem to seed — gives similar_past_incident something to return
COGNITO_OUTAGE_POSTMORTEM = {
    "incident_id": "COGNITO-2025-1121",
    "title": "AWS Cognito JWKS rotation caused cascading auth failures across checkout",
    "root_cause": (
        "AWS Cognito automatic key rotation (every 24h) was not coordinated with downstream "
        "services. Payment and notification services cached JWKS with no TTL refresh — "
        "when the old key was revoked, cached JWT verification failed across all services."
    ),
    "timeline_summary": (
        "2025-11-21 23:00Z: Cognito rotated signing keys. "
        "2025-11-21 23:01Z: payment-service JWKS cache expired, auth failures began. "
        "2025-11-21 23:04Z: 0 transactions authorized — checkout dead for 4 minutes."
    ),
    "services_affected": ["auth-service", "payment-service", "notification-service", "api-gateway"],
    "severity": "CRITICAL",
    "status": "written",
    "recommendations": [
        "Set JWKS cache TTL to 50% of key rotation interval (12h max).",
        "Implement proactive JWKS refresh 30 minutes before key expiry.",
        "Add circuit breaker in payment-service to fall back to auth-service sidecar during JWKS fetch failures.",
    ],
    "created_at": "2025-11-21T23:30:00Z",
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
            "correlation_id": CORRELATION_ID,
            "event_id": entry.get("event_id"),
            "error_code": entry.get("error_code"),
            "duration_ms": entry.get("duration_ms"),
        }
        lines.append(json.dumps(action))
        lines.append(json.dumps(doc))
    return "\n".join(lines) + "\n"


def create_index_if_missing(client: httpx.Client, headers: dict) -> None:
    resp = client.head(f"{config.ELASTIC_CLOUD_URL}/{LOGS_INDEX}")
    if resp.status_code == 404:
        mapping = {
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
        r = client.put(
            f"{config.ELASTIC_CLOUD_URL}/{LOGS_INDEX}",
            json=mapping,
            headers={**headers, "Content-Type": "application/json"},
        )
        if r.status_code not in (200, 201):
            print(f"  ✗ Index creation failed ({r.status_code}): {r.text[:200]}")
            sys.exit(1)
        print(f"  ✓ Created index {LOGS_INDEX}")


def main() -> None:
    if not config.ELASTIC_CLOUD_URL or not config.ELASTIC_API_KEY:
        print("ERROR: ELASTIC_CLOUD_URL and ELASTIC_API_KEY must be set.")
        sys.exit(1)

    headers = {
        "Authorization": f"ApiKey {config.ELASTIC_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(headers=headers, timeout=60.0) as client:
        # Create index if missing (self-contained — no need to run create_mappings.py first)
        create_index_if_missing(client, headers)

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

        # Seed past postmortem for flywheel
        print(f"Seeding Cognito outage postmortem → {POSTMORTEMS_INDEX}...")
        resp = client.post(
            f"{config.ELASTIC_CLOUD_URL}/{POSTMORTEMS_INDEX}/_doc/COGNITO-2025-1121",
            json=COGNITO_OUTAGE_POSTMORTEM,
            headers={**headers, "Content-Type": "application/json"},
        )
        if resp.status_code in (200, 201):
            print("  ✓ Seeded: COGNITO-2025-1121")
        else:
            print(f"  ✗ Seed failed ({resp.status_code}): {resp.text[:200]}")

    print(f"SEEDED_COUNT:{len(LOG_ENTRIES)}")
    print(f"\nGeneric fixture incident ID: {CORRELATION_ID}")
    print("Window: 2026-06-07T09:01:00Z → 2026-06-07T09:06:00Z")
    print("\nDone. Wait ~30s for ELSER to embed semantic_content fields.")
    print("Then POST /run with:")
    print(f'  incident_id: {CORRELATION_ID}')
    print(f'  start_time: 2026-06-07T09:01:00Z')
    print(f'  end_time: 2026-06-07T09:06:00Z')


if __name__ == "__main__":
    main()
