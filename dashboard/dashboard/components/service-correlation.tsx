"use client";

type Correlation = {
  service: string;
  error_count: number;
  cascade_depth: number;
  error_codes: string[];
};

interface Props {
  correlations: Correlation[];
  cascadeChain: string[];
}

export default function ServiceCorrelation({ correlations, cascadeChain }: Props) {
  if (!correlations.length) return null;

  const sorted = [...correlations].sort((a, b) => a.cascade_depth - b.cascade_depth);

  return (
    <section className="border border-border-subtle bg-bg-surface p-6 rounded">
      <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-6">
        Service Correlation — cascade depth {Math.max(...correlations.map(c => c.cascade_depth))}
      </div>

      {/* Cascade chain */}
      {cascadeChain.length > 0 && (
        <div className="mb-6 flex items-center gap-2 flex-wrap">
          {cascadeChain.map((svc, i) => (
            <span key={svc} className="flex items-center gap-2">
              <span className="text-xs font-mono border border-border-subtle text-text-secondary px-2 py-1 rounded">
                {svc}
              </span>
              {i < cascadeChain.length - 1 && (
                <span className="text-text-disabled text-xs">→</span>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Correlation table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs font-mono text-text-tertiary border-b border-border-subtle">
              <th className="text-left pb-2 pr-4">Service</th>
              <th className="text-right pb-2 pr-4">Errors</th>
              <th className="text-right pb-2 pr-4">Depth</th>
              <th className="text-left pb-2">Error Codes</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(c => (
              <tr key={c.service} className="border-b border-border-subtle last:border-0">
                <td className="py-2 pr-4 font-mono text-text-primary">{c.service}</td>
                <td className="py-2 pr-4 font-mono text-right tabular-nums text-signal-warn">
                  {c.error_count}
                </td>
                <td className="py-2 pr-4 font-mono text-right tabular-nums text-text-tertiary">
                  {c.cascade_depth}
                </td>
                <td className="py-2 text-xs text-text-tertiary font-mono">
                  {c.error_codes.join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
