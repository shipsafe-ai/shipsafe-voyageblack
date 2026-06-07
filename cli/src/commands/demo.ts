interface DemoOptions {
  api: string;
  wait: string;
}

const HORMUZ_INCIDENT = {
  incident_id: "HORMUZ-2026-0601",
  start_time: "2026-06-01T14:57:00Z",
  end_time: "2026-06-01T15:02:00Z",
};

async function seedFixtures(api: string): Promise<void> {
  console.log("Seeding Hormuz Crisis fixtures...");
  const res = await fetch(`${api}/demo/seed`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Seed failed: HTTP ${res.status} ${await res.text()}`);
  }
  const body = await res.json() as { seeded: number };
  console.log(`  ✓ Seeded ${body.seeded ?? "?"} log entries to logs-hormuz-2026.06.01`);
  console.log("  ✓ Seeded Red Sea 2024 postmortem to postmortems-shipsafe (flywheel seed)\n");
}

async function waitForELSER(waitSecs: number): Promise<void> {
  console.log(`Waiting ${waitSecs}s for ELSER to embed ingested logs...`);
  for (let i = waitSecs; i > 0; i -= 5) {
    process.stdout.write(`\r  ${i}s remaining...`);
    await new Promise(r => setTimeout(r, Math.min(5000, i * 1000)));
  }
  process.stdout.write("\r  ✓ ELSER embedding window complete\n\n");
}

async function runPipeline(api: string): Promise<string | null> {
  const params = new URLSearchParams(HORMUZ_INCIDENT);
  console.log(`Running postmortem pipeline for ${HORMUZ_INCIDENT.incident_id}...`);
  console.log("  Streaming SSE events from /run/stream\n");

  const res = await fetch(`${api}/run/stream?${params}`, {
    headers: { Accept: "text/event-stream" },
  });

  if (!res.ok) throw new Error(`Pipeline failed: HTTP ${res.status}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let incidentId: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value, { stream: true });
    for (const line of text.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const ev = JSON.parse(line.slice(6)) as {
        stage: string;
        status?: string;
        error?: string;
        result?: { draft?: { incident_id?: string; status?: string }; verdict?: { risk_level?: string; approved?: boolean } };
      };

      if (ev.stage === "__error__") {
        throw new Error(ev.error ?? "Pipeline error");
      } else if (ev.stage === "__result__") {
        incidentId = ev.result?.draft?.incident_id ?? null;
        const verdict = ev.result?.verdict;
        console.log(`  ✓ Pipeline complete`);
        console.log(`    status:      ${ev.result?.draft?.status ?? "draft"}`);
        console.log(`    risk:        ${verdict?.risk_level ?? "unknown"}`);
        console.log(`    auto-approved: ${verdict?.approved ? "yes" : "no (human review required)"}`);
      } else {
        const badge = ev.stage === "ImpactCalculator" ? " [ES MCP]" :
          ["TimelineBuilder", "CorrelationEngine", "ReportWriter"].includes(ev.stage) ? " [Agent Builder]" : "";
        console.log(`  ✓ ${ev.stage}${badge}`);
      }
    }
  }

  return incidentId;
}

export async function demoCommand(opts: DemoOptions): Promise<void> {
  const waitSecs = parseInt(opts.wait, 10);
  console.log(`\nVoyageBlack — demo  (API: ${opts.api})\n`);

  try {
    await seedFixtures(opts.api);
    await waitForELSER(waitSecs);
    const id = await runPipeline(opts.api);

    if (id) {
      console.log(`\nPostmortem ready: ${opts.api.replace(":8080", ":3001")}/postmortem/${id}`);
      console.log("Review in dashboard → Approve to trigger write_postmortem MCP call");
      console.log("Then run again — similar_past_incident will surface this postmortem.\n");
    }
  } catch (e) {
    console.error(`\nError: ${e}`);
    process.exit(1);
  }
}
