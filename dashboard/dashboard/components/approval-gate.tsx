"use client";

type ApproveState = "idle" | "approving" | "approved" | "rejected";

type Verdict = {
  approved: boolean;
  injection_detected: boolean;
  requires_human_review: boolean;
  risk_level: string;
  reasoning: string;
};

interface Props {
  verdict: Verdict;
  status: string;
  approveState: ApproveState;
  onApprove: () => void;
  onReject: () => void;
}

export default function ApprovalGate({ verdict, status, approveState, onApprove, onReject }: Props) {
  if (status === "written" || approveState === "approved") {
    return (
      <div className="border border-signal-approve bg-bg-surface p-6 rounded">
        <div className="flex items-center gap-3">
          <span className="text-signal-approve text-lg">✓</span>
          <div>
            <div className="text-sm font-mono font-medium text-signal-approve">
              Postmortem written to Elasticsearch
            </div>
            <div className="text-xs text-text-tertiary mt-1">
              Available in postmortems-shipsafe index. Will appear in future similar_past_incident queries.
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (approveState === "rejected") {
    return (
      <div className="border border-border-subtle bg-bg-surface p-6 rounded">
        <div className="text-sm text-text-secondary font-mono">Postmortem rejected — not written.</div>
      </div>
    );
  }

  const riskColors: Record<string, string> = {
    none: "text-signal-approve",
    low: "text-signal-approve",
    medium: "text-signal-warn",
    high: "text-signal-block",
    critical: "text-signal-block",
  };

  return (
    <div className={`border p-6 rounded ${verdict.injection_detected ? "border-signal-block" : "border-signal-warn"} bg-bg-surface`}>
      <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-4">
        Human Review Required
      </div>

      {verdict.injection_detected && (
        <div className="mb-4 border border-signal-block bg-bg-elevated p-3 rounded">
          <span className="text-signal-block text-sm font-mono font-medium">
            ⚠ Prompt injection detected in log content — approval blocked
          </span>
          <p className="text-xs text-text-secondary mt-1">{verdict.reasoning}</p>
        </div>
      )}

      {!verdict.injection_detected && (
        <div className="mb-4 space-y-2">
          <div className="flex gap-4 text-sm">
            <span className="text-text-secondary">Risk level:</span>
            <span className={`font-mono ${riskColors[verdict.risk_level] ?? "text-text-primary"}`}>
              {verdict.risk_level.toUpperCase()}
            </span>
          </div>
          <p className="text-sm text-text-secondary">{verdict.reasoning}</p>
        </div>
      )}

      <div className="text-xs text-text-tertiary mb-6 border border-border-subtle rounded p-3 font-mono">
        Approving will write this postmortem to the postmortems-shipsafe Elasticsearch index.
        It will appear in future similar_past_incident queries — building VoyageBlack memory.
      </div>

      <div className="flex gap-3">
        <button
          onClick={onApprove}
          disabled={approveState === "approving" || verdict.injection_detected}
          className="px-6 py-2 bg-signal-approve text-bg-base text-sm font-mono font-medium rounded disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition-all"
        >
          {approveState === "approving" ? "Writing…" : "Approve & Write to Elastic"}
        </button>
        <button
          onClick={onReject}
          disabled={approveState === "approving"}
          className="px-6 py-2 border border-border text-text-secondary text-sm font-mono rounded hover:border-signal-block hover:text-signal-block transition-colors"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
