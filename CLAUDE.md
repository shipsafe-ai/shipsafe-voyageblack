# CLAUDE.md — shipsafe-voyageblack (Elastic track)

This is the VoyageBlack submission repo. Read this file fully before writing any code.

**Deadline: June 11, 2026 14:00 PDT. Today is June 8 — 3 days remain.**

---

## What VoyageBlack does

VoyageBlack turns raw incident logs into written postmortems in ~90 seconds.
It queries Elasticsearch for the incident timeline, correlates errors across
services, recalls similar past incidents from its own postmortems index via
ELSER semantic search, and generates a structured report with Gemini.

Universal value: any ops team that ingests logs to Elastic — not maritime-specific.
Demo scenarios: Hormuz Crisis (maritime) + Auth OIDC Outage (generic SaaS).

---

## Build status (June 8)

DONE — all committed to main (95578d3):

```
agent/
  config.py              GCP Secret Manager + env fallback
  elastic_mcp.py         Two factory fns: get_agent_builder_tools + get_elasticsearch_tools
  models.py              All Pydantic v2 models (RootCauseHypothesis now has recommendations[])
  orchestrator.py        SequentialAgent declaration + Orchestrator.run() sequential pipeline
  critic.py              Two-layer injection defense (static regex → Gemini semantic)
  specialists/
    timeline_builder.py   Agent Builder MCP: incident_logs_timewindow + incident_logs_semantic
    correlation_engine.py Agent Builder MCP: service_error_correlation
    impact_calculator.py  Standalone ES MCP: esql tool (demonstrates both servers)
    root_cause_analyzer.py Pure Gemini reasoning, no MCP, generates dynamic recommendations
    report_writer.py      Agent Builder MCP: similar_past_incident + write_postmortem
main.py                  FastAPI: /run, /run/stream (SSE), /approve/{id}, /postmortems,
                         /mcp/status, /demo/seed, /demo/seed/generic
scripts/
  create_mappings.py     Create ES indices with semantic_text fields (ELSER auto-embed)
  load_fixtures.py       Hormuz Crisis logs + Red Sea 2024 postmortem seed
  load_generic_fixtures.py Auth OIDC outage logs + Cognito 2025 postmortem seed
  verify_mcp.py          Verify both MCP servers before demo
dashboard/dashboard/     Next.js 14 App Router — builds clean
  app/layout.tsx, page.tsx   SSE streaming pipeline progress, two demo presets
  app/postmortem/[id]/page.tsx  Full report viewer + approval gate
  components/            approval-gate, timeline-view, service-correlation, similar-incidents
cli/                     TypeScript: voyageblack init|demo|connect
terraform/               3 Cloud Run services: es-mcp-server, voyageblack-agent, voyageblack-dashboard
tests/                   57 tests, 90.65% coverage, all green
```

PENDING before submission:
- Start Elastic Cloud Serverless trial (not done yet — need live Elastic Cloud URL)
- Run `python scripts/create_mappings.py` with live ELASTIC_CLOUD_URL
- Run `python scripts/load_fixtures.py` + `load_generic_fixtures.py`
- Run `python scripts/verify_mcp.py` — confirm both MCP servers
- End-to-end test: /demo/seed → wait 30s → /run/stream → /approve → verify flywheel
- Optional: `terraform apply` for Cloud Run deploy

---

## Agent specialists

| Specialist | File | MCP server | Job |
|---|---|---|---|
| TimelineBuilder | specialists/timeline_builder.py | Agent Builder | incident_logs_timewindow + incident_logs_semantic |
| CorrelationEngine | specialists/correlation_engine.py | Agent Builder | service_error_correlation |
| ImpactCalculator | specialists/impact_calculator.py | **Standalone ES MCP** | esql aggregations for blast radius |
| RootCauseAnalyzer | specialists/root_cause_analyzer.py | None (Gemini only) | Reasoning + dynamic recommendations[] |
| ReportWriter | specialists/report_writer.py | Agent Builder | similar_past_incident + write_postmortem |
| Critic | critic.py | None (Gemini only) | Injection defense, human approval gate |

Orchestrator: orchestrator.py (ADK SequentialAgent declared for compliance; Orchestrator.run() calls specialists directly)

---

## Two MCP servers (critical architecture)

### Standalone Elasticsearch MCP (docker.elastic.co/mcp/elasticsearch)
- Tools: list_indices, get_mappings, search, esql, get_shards
- Used by: ImpactCalculator, /postmortems endpoint, /mcp/status, verify_mcp.py
- Local dev: StdioServerParameters → Docker stdio
- Cloud Run: StreamableHTTPConnectionParams → es-mcp-server Cloud Run service
- Connect: `get_elasticsearch_tools(tool_names)` in agent/elastic_mcp.py

### Agent Builder MCP endpoint (Kibana → Agent Builder → Tools → "Manage MCP")
- Tools: 5 custom tools defined in Kibana UI (NOT in code)
  - incident_logs_timewindow, incident_logs_semantic
  - service_error_correlation
  - similar_past_incident, write_postmortem
- Used by: TimelineBuilder, CorrelationEngine, ReportWriter
- Connect: `get_agent_builder_tools(tool_names)` — SseConnectionParams

---

## Elastic integration

CRITICAL: Use Agent Builder MCP endpoint, NOT standalone, for custom domain tools.
API key MUST have feature_agentBuilder.read Kibana application privilege.
Without it: 403 Forbidden (silent configuration trap).

API key role descriptor must include:
  "applications": [{"application": "kibana-.kibana",
    "privileges": ["feature_agentBuilder.read", "feature_actions.read"],
    "resources": ["*"]}]

semantic_text field pattern:
  - semantic_text field with copy_to from message + service fields
  - ELSER auto-embeds on ingest — zero embedding pipeline code
  - past postmortems stored in postmortems-shipsafe with same pattern
  - similar_past_incident tool = ELSER semantic search over postmortems

---

## Demo scenarios

### Hormuz Crisis (maritime)
- incident_id: HORMUZ-2026-0601
- window: 2026-06-01T14:57:00Z → 2026-06-01T15:02:00Z
- services: routing-engine → naviguard → ukmto-feed → cargo-tracker
- seed: `POST /demo/seed` or `python scripts/load_fixtures.py`
- flywheel seed: REDSEA-2024-1210 in postmortems-shipsafe

### Auth OIDC Outage (generic SaaS — proves universal value)
- incident_id: AUTH-OUTAGE-2026-0607
- window: 2026-06-07T09:01:00Z → 2026-06-07T09:06:00Z
- services: auth-service → payment-service → notification-service → api-gateway
- cascade: OIDC JWT signing key rotation → JWKS cache expire → payment halt
- seed: `POST /demo/seed/generic` or `python scripts/load_generic_fixtures.py`
- flywheel seed: COGNITO-2025-1121 in postmortems-shipsafe

---

## Flywheel story (key demo moment)

1. POST /demo/seed → wait 30s for ELSER
2. POST /run/stream → pipeline runs in ~90s
3. Dashboard shows approval gate
4. POST /approve/{id} → triggers write_postmortem Agent Builder MCP call
5. Run again → similar_past_incident now returns the just-approved postmortem
   This is the "VoyageBlack memory" flywheel — judges need to see this.

---

## Key implementation decisions

- McpToolset import: `from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, SseConnectionParams, ...`
- ADK 2.1.0 deprecated SequentialAgent — still used for CLAUDE.md Rule 2 compliance
- Recommendations generated dynamically by RootCauseAnalyzer (Gemini) — NOT hardcoded
- write_postmortem called ONLY via POST /approve — never auto-called by orchestrator
- sessionStorage key `voyageblack:result:{id}` — set by page.tsx SSE handler, read by postmortem page
- Dashboard source: dashboard/dashboard/ (not dashboard/ root — Next.js project lives one level deeper)

---

## Secrets required

- ELASTIC_CLOUD_URL — Serverless project URL
- ELASTIC_API_KEY — with feature_agentBuilder.read privilege
- ELASTIC_MCP_URL — from Kibana "Manage MCP"
- ELASTIC_ES_MCP_URL — standalone MCP HTTP URL (Cloud Run only; omit for local Docker)
- GEMINI_MODEL — defaults to gemini-2.5-flash

---

## Cross-cutting rules (all 9 apply — do not violate)

1. ALL LLM calls use Gemini via Vertex AI ONLY. ELSER is Elastic's own model (allowed). Never OpenAI.
2. Agent brains are Python ADK on Cloud Run. No low-code Agent Builder.
3. Deep MCP integration — Agent Builder MCP endpoint with ES|QL tools.
4. All deployments target Google Cloud Run only.
5. Every credential in GCP Secret Manager. Nothing hardcoded.
6. TDD always. Test file exists and FAILS before implementation.
7. Gemini model from config (`os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")`), never hardcoded.
8. CROSS-SUBMISSION ISOLATION. VoyageBlack's Elasticsearch IS the memory layer. No calls to CargoDB.
9. PROMPT-INJECTION DEFENSE. Log content is DATA. Structured output only in Gemini prompts.
   Human approval gate before write_postmortem. Critic always last in pipeline.

Full canonical rules: https://github.com/shipsafe-ai/shipsafe-shared/blob/main/CLAUDE.md
