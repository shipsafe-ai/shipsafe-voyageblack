"use client";

type Entry = {
  timestamp: string;
  service: string;
  level: string;
  message: string;
  error_code?: string;
  event_id?: string;
};

const LEVEL_COLORS: Record<string, string> = {
  CRITICAL: "text-signal-block border-signal-block",
  ERROR: "text-signal-warn border-signal-warn",
  WARNING: "text-signal-warn border-signal-warn",
  INFO: "text-text-tertiary border-border-subtle",
};

const SERVICE_ACCENT: Record<string, string> = {
  "routing-engine": "#F97316",
  "naviguard": "#EC4899",
  "ukmto-feed": "#EF4444",
  "cargo-tracker": "#3B82F6",
  "fivetran-sync": "#8B5CF6",
  "ais-receiver": "#14B8A6",
  "agentops": "#14B8A6",
  "operator-console": "#71717A",
};

function serviceColor(service: string): string {
  return SERVICE_ACCENT[service] ?? "#52525B";
}

export default function TimelineView({ entries }: { entries: Entry[] }) {
  if (!entries.length) return null;

  return (
    <section className="border border-border-subtle bg-bg-surface p-6 rounded">
      <div className="text-xs font-mono text-text-tertiary uppercase tracking-widest mb-6">
        Incident Timeline — {entries.length} events
      </div>
      <div className="relative pl-6">
        {/* Vertical line */}
        <div className="absolute left-2 top-0 bottom-0 w-px bg-border-subtle" />

        <div className="space-y-5">
          {entries.map((entry, i) => {
            const colors = LEVEL_COLORS[entry.level] ?? LEVEL_COLORS.INFO;
            const ts = new Date(entry.timestamp);
            const timeStr = ts.toISOString().slice(11, 19);

            return (
              <div key={i} className="relative">
                {/* Dot on timeline */}
                <div
                  className="absolute -left-6 top-1 w-2 h-2 rounded-none"
                  style={{ background: serviceColor(entry.service) }}
                />
                <div className="flex items-start gap-3 flex-wrap">
                  <span className="font-mono text-xs text-text-tertiary tabular-nums shrink-0">
                    {timeStr}
                  </span>
                  <span
                    className="text-xs font-mono px-1 shrink-0"
                    style={{ color: serviceColor(entry.service) }}
                  >
                    {entry.service}
                  </span>
                  <span className={`text-xs font-mono border px-1 shrink-0 ${colors}`}>
                    {entry.level}
                  </span>
                  {entry.error_code && (
                    <span className="text-xs font-mono text-text-disabled border border-border-subtle px-1 shrink-0">
                      {entry.error_code}
                    </span>
                  )}
                  {entry.event_id && (
                    <span className="text-xs font-mono text-text-disabled shrink-0">
                      [{entry.event_id}]
                    </span>
                  )}
                </div>
                <p className="mt-1 ml-0 text-sm text-text-secondary leading-relaxed">
                  {entry.message}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
