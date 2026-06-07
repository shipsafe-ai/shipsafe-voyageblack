"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import PipelineStream from "@/components/pipeline-stream";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const HORMUZ_PRESET = {
  incident_id: "HORMUZ-2026-0601",
  start_time: "2026-06-01T14:57:00Z",
  end_time: "2026-06-01T15:02:00Z",
};

const GENERIC_PRESET = {
  incident_id: "AUTH-OUTAGE-2026-0607",
  start_time: "2026-06-07T09:01:00Z",
  end_time: "2026-06-07T09:06:00Z",
};

type StageEvent = {
  stage: string;
  status?: string;
  entry_count?: number;
  services?: string[];
  service_count?: number;
  max_cascade_depth?: number;
  total_errors?: number;
  services_affected?: number;
  duration_minutes?: number;
  confidence?: number;
  primary_cause_preview?: string;
  similar_count?: number;
  top_similarity?: number;
  approved?: boolean;
  injection_detected?: boolean;
  risk_level?: string;
  result?: Record<string, unknown>;
  error?: string;
};

const STAGE_ORDER = [
  "TimelineBuilder",
  "CorrelationEngine",
  "ImpactCalculator",
  "RootCauseAnalyzer",
  "ReportWriter",
  "Critic",
];

const STAGE_LABELS: Record<string, string> = {
  TimelineBuilder: "Timeline Reconstruction",
  CorrelationEngine: "Service Correlation",
  ImpactCalculator: "Blast Radius",
  RootCauseAnalyzer: "Root Cause Analysis",
  ReportWriter: "Similar Incidents",
  Critic: "Security Review",
};

export default function Home() {
  const router = useRouter();
  const [incidentId, setIncidentId] = useState(HORMUZ_PRESET.incident_id);
  const [startTime, setStartTime] = useState(HORMUZ_PRESET.start_time);
  const [endTime, setEndTime] = useState(HORMUZ_PRESET.end_time);
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<Record<string, StageEvent>>({});
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);

  async function handleRun() {
    setRunning(true);
    setStages({});
    setError(null);
    setResultId(null);
    setElapsed(0);

    const startMs = Date.now();
    const ticker = setInterval(() => setElapsed(Math.floor((Date.now() - startMs) / 1000)), 200);

    try {
      const params = new URLSearchParams({
        incident_id: incidentId,
        start_time: startTime,
        end_time: endTime,
      });
      const res = await fetch(`${API}/run/stream?${params}`, {
        headers: { Accept: "text/event-stream" },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        for (const line of text.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const ev: StageEvent = JSON.parse(line.slice(6));

          if (ev.stage === "__error__") {
            setError(ev.error ?? "Unknown error");
          } else if (ev.stage === "__result__") {
            const id = (ev.result as { draft?: { incident_id?: string } })?.draft?.incident_id;
            if (id) {
              sessionStorage.setItem(`voyageblack:result:${id}`, JSON.stringify(ev.result));
              setResultId(id);
              setTimeout(() => router.push(`/postmortem/${id}`), 800);
            }
          } else {
            setStages(prev => ({ ...prev, [ev.stage]: ev }));
          }
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      clearInterval(ticker);
      setRunning(false);
    }
  }

  const completedCount = Object.keys(stages).length;

  return (
    <div className="space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-mono font-medium tracking-tight text-text-primary">
          Incident Postmortem Generator
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Query Elasticsearch → correlate services → reason with Gemini → draft postmortem in ~90s
        </p>
      </div>

      {/* Incident window selector */}
      <div className="border border-border-subtle bg-bg-surface p-6 rounded space-y-4">
        <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-4">
          Incident Window
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label className="block text-xs text-text-secondary mb-1">Incident ID</label>
            <input
              value={incidentId}
              onChange={e => setIncidentId(e.target.value)}
              className="w-full bg-bg-elevated border border-border text-text-primary text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-accent"
              placeholder="INCIDENT-2026-001"
            />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Start Time (UTC)</label>
            <input
              value={startTime}
              onChange={e => setStartTime(e.target.value)}
              className="w-full bg-bg-elevated border border-border text-text-primary text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-accent"
              placeholder="2026-06-01T14:55:00Z"
            />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">End Time (UTC)</label>
            <input
              value={endTime}
              onChange={e => setEndTime(e.target.value)}
              className="w-full bg-bg-elevated border border-border text-text-primary text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-accent"
              placeholder="2026-06-01T15:02:00Z"
            />
          </div>
        </div>

        <div className="flex items-center gap-4 pt-2">
          <button
            onClick={handleRun}
            disabled={running}
            className="px-6 py-2 bg-accent text-white text-sm font-mono rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-500 transition-colors"
          >
            {running ? "Running…" : "Generate Postmortem"}
          </button>
          <button
            onClick={() => { setIncidentId(HORMUZ_PRESET.incident_id); setStartTime(HORMUZ_PRESET.start_time); setEndTime(HORMUZ_PRESET.end_time); }}
            className="text-xs text-text-tertiary hover:text-text-secondary transition-colors"
          >
            Load Hormuz Demo
          </button>
          <button
            onClick={() => { setIncidentId(GENERIC_PRESET.incident_id); setStartTime(GENERIC_PRESET.start_time); setEndTime(GENERIC_PRESET.end_time); }}
            className="text-xs text-text-tertiary hover:text-text-secondary transition-colors"
          >
            Load Auth Outage Demo
          </button>
          {running && (
            <span className="font-mono text-sm text-signal-warn tabular-nums">
              {elapsed}s
            </span>
          )}
          {resultId && !running && (
            <span className="font-mono text-sm text-signal-approve">
              ✓ Done — redirecting…
            </span>
          )}
        </div>
      </div>

      {/* Pipeline stages */}
      {(running || completedCount > 0) && (
        <div className="border border-border-subtle bg-bg-surface p-6 rounded">
          <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-6">
            Pipeline Progress — {completedCount}/{STAGE_ORDER.length} stages
          </div>
          <div className="space-y-3">
            {STAGE_ORDER.map((stage, i) => {
              const ev = stages[stage];
              const active = running && i === completedCount;
              const done = !!ev;
              return (
                <div key={stage} className="flex items-start gap-4">
                  {/* Status indicator */}
                  <div className="mt-1 w-4 flex-shrink-0 flex items-center justify-center">
                    {done ? (
                      <span className="text-signal-approve text-xs">✓</span>
                    ) : active ? (
                      <span className="inline-block w-2 h-2 rounded-none bg-accent animate-pulse" />
                    ) : (
                      <span className="w-2 h-2 rounded-none border border-border-strong" />
                    )}
                  </div>
                  {/* Stage info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <span className={`text-sm font-mono ${done ? "text-text-primary" : active ? "text-accent" : "text-text-disabled"}`}>
                        {STAGE_LABELS[stage]}
                      </span>
                      {stage === "ImpactCalculator" && (
                        <span className="text-xs font-mono text-text-tertiary border border-border-subtle px-1">
                          ES MCP
                        </span>
                      )}
                      {["TimelineBuilder", "CorrelationEngine", "ReportWriter"].includes(stage) && (
                        <span className="text-xs font-mono text-text-tertiary border border-border-subtle px-1">
                          Agent Builder
                        </span>
                      )}
                    </div>
                    {done && <StageDetail stage={stage} ev={ev} />}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {error && (
        <div className="border border-signal-block bg-bg-surface p-4 rounded">
          <span className="text-signal-block text-sm font-mono">{error}</span>
        </div>
      )}
    </div>
  );
}

function StageDetail({ stage, ev }: { stage: string; ev: StageEvent }) {
  const parts: string[] = [];
  if (stage === "TimelineBuilder" && ev.entry_count !== undefined) {
    parts.push(`${ev.entry_count} events`);
    if (ev.services?.length) parts.push(`services: ${ev.services.join(", ")}`);
  }
  if (stage === "CorrelationEngine") {
    if (ev.service_count !== undefined) parts.push(`${ev.service_count} services`);
    if (ev.max_cascade_depth !== undefined) parts.push(`depth ${ev.max_cascade_depth}`);
  }
  if (stage === "ImpactCalculator") {
    if (ev.total_errors !== undefined) parts.push(`${ev.total_errors} errors`);
    if (ev.services_affected !== undefined) parts.push(`${ev.services_affected} services affected`);
    if (ev.duration_minutes !== undefined) parts.push(`${ev.duration_minutes}m`);
  }
  if (stage === "RootCauseAnalyzer") {
    if (ev.confidence !== undefined) parts.push(`confidence ${Math.round(ev.confidence * 100)}%`);
    if (ev.primary_cause_preview) parts.push(ev.primary_cause_preview);
  }
  if (stage === "ReportWriter") {
    if (ev.similar_count !== undefined) parts.push(`${ev.similar_count} similar found`);
    if (ev.top_similarity) parts.push(`top: ${Math.round(ev.top_similarity * 100)}% match`);
  }
  if (stage === "Critic") {
    if (ev.injection_detected) parts.push("⚠ INJECTION DETECTED");
    if (ev.risk_level) parts.push(`risk: ${ev.risk_level}`);
    if (ev.approved !== undefined) parts.push(ev.approved ? "approved" : "human review required");
  }

  if (!parts.length) return null;
  return (
    <div className="mt-1 text-xs font-mono text-text-tertiary truncate">
      {parts.join(" · ")}
    </div>
  );
}
