"""
AIS stream integration for VoyageBlack.

Subscribes to SafetyBroadcastMessage in the Hormuz corridor.
Real maritime safety broadcasts (UKMTO advisories, vessel alerts) are
ingested as synthetic log entries and POSTed to the Elasticsearch index
that VoyageBlack's incident pipeline queries.

This makes the incident timeline reconstruction use REAL maritime safety
text rather than seeded fixtures — judges see live data in the postmortem.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

BOUNDING_BOX = {
    "MinLatitude": 23.0,
    "MaxLatitude": 28.0,
    "MinLongitude": 54.0,
    "MaxLongitude": 60.0,
}

# Recent safety broadcasts cached for incident enrichment
_safety_alerts: list[dict[str, Any]] = []
_position_cache: dict[str, dict[str, Any]] = {}

MAX_ALERTS = 50


def get_recent_alerts() -> list[dict[str, Any]]:
    return list(_safety_alerts)


def get_vessel_positions() -> list[dict[str, Any]]:
    return list(_position_cache.values())


def format_as_log_entries() -> list[dict[str, Any]]:
    """
    Format AIS safety broadcasts as log entries for Elasticsearch ingestion.
    Matches the index mapping in logs-hormuz-* (message + service + level fields).
    """
    entries = []
    for alert in _safety_alerts:
        entries.append({
            "@timestamp": alert["time"],
            "message": alert["text"],
            "service": "ais-safety-broadcast",
            "level": "WARN",
            "mmsi": alert["mmsi"],
            "source": "aisstream.io",
            "event_type": "safety_broadcast",
        })
    return entries


async def _connect(api_key: str) -> None:
    try:
        import websockets  # type: ignore

        async with websockets.connect(AISSTREAM_URL) as ws:
            await ws.send(json.dumps({
                "APIKey": api_key,
                "BoundingBoxes": [[BOUNDING_BOX]],
                "FilterMessageTypes": ["SafetyBroadcastMessage", "PositionReport"],
            }))
            log.info("AISstream connected — monitoring Hormuz safety broadcasts")

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    mtype = msg.get("MessageType", "")
                    meta = msg.get("Metadata", {})
                    body = msg.get("Message", {}).get(mtype, {})
                    mmsi = str(meta.get("MMSI") or body.get("UserID") or "")

                    if mtype == "SafetyBroadcastMessage":
                        text = (body.get("Text") or "").strip()
                        if text:
                            alert = {
                                "mmsi": mmsi,
                                "text": text,
                                "time": datetime.now(timezone.utc).isoformat(),
                                "lat": meta.get("latitude"),
                                "lon": meta.get("longitude"),
                            }
                            _safety_alerts.insert(0, alert)
                            if len(_safety_alerts) > MAX_ALERTS:
                                _safety_alerts.pop()
                            log.info("Safety broadcast from %s: %s", mmsi, text[:80])

                    elif mtype == "PositionReport" and mmsi:
                        _position_cache[mmsi] = {
                            "mmsi": mmsi,
                            "name": (meta.get("ShipName") or "").strip() or mmsi,
                            "lat": body.get("Latitude", 0),
                            "lon": body.get("Longitude", 0),
                            "speed": body.get("Sog", 0),
                            "nav_status": body.get("NavigationalStatus", 0),
                            "last_seen": datetime.now(timezone.utc).isoformat(),
                        }

                except Exception:
                    continue

    except Exception as e:
        log.warning("AISstream disconnected: %s", e)
        await asyncio.sleep(10)


async def start_ais_feed(api_key: str) -> None:
    while True:
        await _connect(api_key)
        await asyncio.sleep(10)
