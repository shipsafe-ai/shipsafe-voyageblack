"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ApprovalGate from "@/components/approval-gate";
import TimelineView from "@/components/timeline-view";
import ServiceCorrelation from "@/components/service-correlation";
import SimilarIncidents from "@/components/similar-incidents";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type Entry = {
  timestamp: string;
  service: string;
  level: string;
  message: string;
  error_code?: string;
  event_id?: string;
};

type Correlation = {
  service: string;
  error_count: number;
  cascade_depth: number;
  error_codes: string[];
};

type BlastRadius = {
  total_errors: number;
  services_affected: number;
  estimated_duration_minutes: number;
  cascade_chain: string[];
  error_rate_per_service: Record<string, number>;
};

type RootCause = {
  primary_cause: string;
  contributing_factors: string[];
  confidence: number;
  evidence: string[];
};

type SimilarIncident = {
  id: string;
  title: string;
  similarity_score: number;
  root_cause: string;
  resolution: string;
};

type Draft = {
  incident_id: string;
  title: string;
  severity: string;
  status: string;
  timeline: { entries: Entry[]; services_involved: string[]; start_time: string; end_time: string; correlation_id: string };
  correlations: Correlation[];
  blast_radius: BlastRadius;
  root_cause: RootCause;
  similar_incidents: SimilarIncident[];
  recommendations: string[];
};

type Verdict = {
  approved: boolean;
  injection_detected: boolean;
  requires_human_review: boolean;
  risk_level: string;
  reasoning: string;
};

type Result = { draft: Draft; verdict: Verdict; approved: boolean; requires_human_review: boolean };

export default function PostmortemPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;

  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approveState, setApproveState] = useState<"idle" | "approving" | "approved" | "rejected">("idle");

  useEffect(() => {
    if (!id) return;
    // Check sessionStorage for result from streaming run
    const cached = sessionStorage.getItem(`voyageblack:result:${id}`);
    if (cached) {
      setResult(JSON.parse(cached));
      setLoading(false);
    } else {
      // Fetch from API
      fetch(`${API}/postmortems/${id}`)
        .then(r => r.json())
        .then(data => { setResult(data); setLoading(false); })
        .catch(e => { setError(String(e)); setLoading(false); });
    }
  }, [id]);

  async function handleApprove() {
    if (!result) return;
    setApproveState("approving");
    try {
      const res = await fetch(`${API}/approve/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result.draft),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setApproveState("approved");
      // Update local state
      setResult(prev => prev ? {
        ...prev,
        draft: { ...prev.draft, status: "written" }
      } : prev);
    } catch (e) {
      setError(String(e));
      setApproveState("idle");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-3 py-20 justify-center">
        <span className="inline-block w-2 h-2 bg-accent animate-pulse" />
        <span className="text-sm text-text-secondary font-mono">Loading postmortem…</span>
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="border border-signal-block bg-bg-surface p-6 rounded">
        <span className="text-signal-block font-mono text-sm">{error ?? "Postmortem not found"}</span>
      </div>
    );
  }

  const { draft, verdict } = result;
  const severityColor: Record<string, string> = {
    CRITICAL: "text-signal-block",
    HIGH: "text-signal-warn",
    MEDIUM: "text-signal-info",
    LOW: "text-text-tertiary",
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-border-subtle pb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-xs font-mono uppercase tracking-widest ${severityColor[draft.severity] ?? "text-text-secondary"}`}>
            {draft.severity}
          </span>
          <span className="text-text-tertiary">·</span>
          <span className="text-xs font-mono text-text-tertiary">{draft.incident_id}</span>
          <span className="text-text-tertiary">·</span>
          <span className={`text-xs font-mono ${draft.status === "written" ? "text-signal-approve" : "text-signal-warn"}`}>
            {draft.status.toUpperCase()}
          </span>
        </div>
        <h1 className="text-xl font-mono font-medium text-text-primary leading-tight">
          {draft.title || draft.incident_id}
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          {new Date(draft.timeline.start_time).toUTCString()} →{" "}
          {new Date(draft.timeline.end_time).toUTCString()}
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatBox label="Total Errors" value={String(draft.blast_radius.total_errors)} />
        <StatBox label="Services Affected" value={String(draft.blast_radius.services_affected)} />
        <StatBox label="Duration" value={`${draft.blast_radius.estimated_duration_minutes}m`} />
        <StatBox label="RC Confidence" value={`${Math.round(draft.root_cause.confidence * 100)}%`} color={draft.root_cause.confidence > 0.7 ? "text-signal-approve" : "text-signal-warn"} />
      </div>

      {/* Root cause */}
      <section className="border border-border-subtle bg-bg-surface p-6 rounded">
        <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-4">Root Cause</div>
        <p className="text-sm text-text-primary font-medium">{draft.root_cause.primary_cause}</p>
        {draft.root_cause.contributing_factors.length > 0 && (
          <ul className="mt-3 space-y-1">
            {draft.root_cause.contributing_factors.map((f, i) => (
              <li key={i} className="text-sm text-text-secondary flex gap-2">
                <span className="text-text-disabled">–</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        )}
        {draft.root_cause.evidence.length > 0 && (
          <div className="mt-4 space-y-1">
            {draft.root_cause.evidence.map((e, i) => (
              <div key={i} className="text-xs font-mono text-accent">{e}</div>
            ))}
          </div>
        )}
      </section>

      {/* Cascade chain */}
      <ServiceCorrelation
        correlations={draft.correlations}
        cascadeChain={draft.blast_radius.cascade_chain}
      />

      {/* Timeline */}
      <TimelineView entries={draft.timeline.entries} />

      {/* Similar incidents */}
      <SimilarIncidents incidents={draft.similar_incidents} />

      {/* Recommendations */}
      {draft.recommendations.length > 0 && (
        <section className="border border-border-subtle bg-bg-surface p-6 rounded">
          <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-4">Recommendations</div>
          <ol className="space-y-2">
            {draft.recommendations.map((r, i) => (
              <li key={i} className="flex gap-3 text-sm text-text-secondary">
                <span className="font-mono text-text-disabled">{String(i + 1).padStart(2, "0")}</span>
                <span>{r}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Approval gate */}
      <ApprovalGate
        verdict={verdict}
        status={draft.status}
        approveState={approveState}
        onApprove={handleApprove}
        onReject={() => { setApproveState("rejected"); router.push("/"); }}
      />
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="border border-border-subtle bg-bg-surface p-4 rounded">
      <div className="text-xs text-text-tertiary mb-1">{label}</div>
      <div className={`text-xl font-mono font-medium tabular-nums ${color ?? "text-text-primary"}`}>
        {value}
      </div>
    </div>
  );
}
