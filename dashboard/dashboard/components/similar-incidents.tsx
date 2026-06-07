"use client";

type SimilarIncident = {
  id: string;
  title: string;
  similarity_score: number;
  root_cause: string;
  resolution: string;
};

export default function SimilarIncidents({ incidents }: { incidents: SimilarIncident[] }) {
  if (!incidents.length) {
    return (
      <section className="border border-border-subtle bg-bg-surface p-6 rounded">
        <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-3">
          Similar Past Incidents
        </div>
        <p className="text-sm text-text-tertiary">No similar incidents found in postmortems-shipsafe index.</p>
      </section>
    );
  }

  return (
    <section className="border border-border-subtle bg-bg-surface p-6 rounded">
      <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-6">
        Similar Past Incidents — ELSER semantic search
      </div>
      <div className="space-y-4">
        {incidents.map(inc => {
          const pct = Math.round(inc.similarity_score * 100);
          const barColor = pct >= 80 ? "#22C55E" : pct >= 60 ? "#F59E0B" : "#3B82F6";
          return (
            <div key={inc.id} className="border border-border-subtle rounded p-4">
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="text-sm font-medium text-text-primary">{inc.title}</div>
                  <div className="text-xs font-mono text-text-tertiary mt-0.5">{inc.id}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-mono text-lg tabular-nums" style={{ color: barColor }}>
                    {pct}%
                  </div>
                  <div className="text-xs text-text-tertiary">match</div>
                </div>
              </div>
              {/* Similarity bar */}
              <div className="w-full h-1 bg-bg-elevated rounded mb-3">
                <div
                  className="h-1 rounded transition-all"
                  style={{ width: `${pct}%`, background: barColor }}
                />
              </div>
              <div className="text-xs text-text-secondary mb-2">
                <span className="text-text-tertiary font-mono">Root cause: </span>
                {inc.root_cause}
              </div>
              <div className="text-xs text-text-secondary">
                <span className="text-text-tertiary font-mono">Resolution: </span>
                {inc.resolution}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 text-xs text-text-tertiary font-mono">
        Source: postmortems-shipsafe · ELSER semantic_text field · similar_past_incident MCP tool
      </div>
    </section>
  );
}
