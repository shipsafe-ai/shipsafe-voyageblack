# CLAUDE.md — shipsafe-voyageblack (Elastic track)

This is the VoyageBlack submission repo. Read this file fully
before writing any code. Then read PARTNER-INTEGRATION.md §3.

---

## What VoyageBlack does

VoyageBlack turns raw incident logs into written postmortems in
minutes. It queries Elasticsearch for the incident timeline,
correlates errors across services, recalls similar past incidents
from its own postmortems index, and generates a structured report.

Universal value: any ops team that ingests logs to Elastic.

---

## Agent specialists

| Specialist | File | Job |
|---|---|---|
| TimelineBuilder | specialists/timeline_builder.py | ES|QL incident_logs_timewindow + incident_logs_semantic |
| CorrelationEngine | specialists/correlation_engine.py | ES|QL service_error_correlation |
| ImpactCalculator | specialists/impact_calculator.py | ES|QL aggregations for blast radius |
| RootCauseAnalyzer | specialists/root_cause_analyzer.py | Gemini reasoning over timeline + correlation |
| ReportWriter | specialists/report_writer.py | similar_past_incident + write_postmortem MCP tools |
| Critic | critic.py | Challenges above + prompt-injection check |

Orchestrator: orchestrator.py (ADK SequentialAgent)

---

## Elastic integration (see PARTNER-INTEGRATION.md §3)

CRITICAL GAP — Use Agent Builder MCP endpoint, NOT standalone:
The standalone elastic/mcp-server-elasticsearch is DEPRECATED.
Use the Agent Builder MCP endpoint (Elasticsearch 9.2+ / Serverless).

MCP endpoint: from Kibana → Agent Builder → Tools → "Manage MCP"
API key MUST have feature_agentBuilder.read Kibana application
privilege. Without it: 403 Forbidden (silent configuration trap).

API key role descriptor must include:
  "applications": [{"application": "kibana-.kibana",
    "privileges": ["feature_agentBuilder.read", "feature_actions.read"],
    "resources": ["*"]}]

semantic_text field pattern (the key insight):
  - Add semantic_text field to log indices with copy_to from
    message + service fields
  - ELSER auto-embeds on ingest — zero embedding pipeline code
  - past postmortems stored in postmortems-* with same pattern
  - similar_past_incident tool = semantic search over postmortems

Tools to define in Kibana Agent Builder UI (not in code):
  incident_logs_timewindow, incident_logs_semantic,
  service_error_correlation, similar_past_incident, write_postmortem

GAP — Reference architecture is non-compliant:
Elastic's reference uses LangChain + LangGraph + OpenAI GPT-5.2.
Translate data/MCP wiring only. Use ADK + Gemini for orchestration.

---

## Secrets required

- ELASTIC_CLOUD_URL — Serverless project URL
- ELASTIC_API_KEY — with feature_agentBuilder.read privilege
- ELASTIC_MCP_URL — from "Manage MCP" in Kibana

Start Elastic Cloud Serverless trial on Day 6 morning.

---

## Build day: Day 6 (June 3)

Fetch three prep docs before coding:
1. elastic.co/docs/solutions/search/agent-builder/get-started
2. elastic.co/docs/solutions/search/agent-builder/tools
3. elastic.co/docs/solutions/search/agent-builder/mcp-server

---

## Cross-cutting rules (from shipsafe-shared/CLAUDE.md — all 9 apply here)

1. ALL LLM calls use Gemini via Vertex AI ONLY. ELSER is Elastic's
   own model (allowed on this track). Never OpenAI embeddings.

2. Agent brains are Python ADK on Cloud Run. No low-code Agent Builder.

3. Deep MCP integration — Agent Builder MCP endpoint with ES|QL tools.

4. All deployments target Google Cloud Run only.

5. Every credential in GCP Secret Manager. Nothing hardcoded.

6. TDD always. Test file exists and FAILS before implementation.

7. Gemini model from config, never hardcoded.

8. CROSS-SUBMISSION ISOLATION. VoyageBlack's Elasticsearch IS the
   memory layer. No calls to CargoDB or other submissions.

9. PROMPT-INJECTION DEFENSE. Log content is DATA. Structured output.
   Human approval gate before writing postmortem externally.

Full canonical rules: https://github.com/shipsafe-ai/shipsafe-shared/blob/main/CLAUDE.md
Full partner spec: https://github.com/shipsafe-ai/shipsafe-shared/blob/main/docs/PARTNER-INTEGRATION.md
