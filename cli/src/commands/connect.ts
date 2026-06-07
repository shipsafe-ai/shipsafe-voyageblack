interface ConnectOptions {
  api: string;
}

async function checkHealth(api: string): Promise<boolean> {
  try {
    const res = await fetch(`${api}/health`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

async function checkMcpStatus(api: string): Promise<{
  standaloneOk: boolean;
  agentBuilderOk: boolean;
  indices: string[];
  agentBuilderTools: string[];
}> {
  const res = await fetch(`${api}/mcp/status`, { signal: AbortSignal.timeout(30000) });
  if (!res.ok) throw new Error(`MCP status check failed: HTTP ${res.status}`);
  return res.json() as Promise<{ standaloneOk: boolean; agentBuilderOk: boolean; indices: string[]; agentBuilderTools: string[] }>;
}

export async function connectCommand(opts: ConnectOptions): Promise<void> {
  console.log(`\nVoyageBlack — connect  (API: ${opts.api})\n`);

  // 1. API health
  process.stdout.write("Checking API health... ");
  const healthy = await checkHealth(opts.api);
  if (!healthy) {
    console.log("FAIL");
    console.error(`Cannot reach ${opts.api}/health. Is the agent running?`);
    console.error("Start with: uvicorn main:app --port 8080");
    process.exit(1);
  }
  console.log("OK");

  // 2. MCP status via API endpoint
  process.stdout.write("Checking MCP endpoints... ");
  try {
    const status = await checkMcpStatus(opts.api);

    console.log("\n");
    console.log("Standalone Elasticsearch MCP (docker.elastic.co/mcp/elasticsearch):");
    console.log(`  Status:  ${status.standaloneOk ? "✓ connected" : "✗ failed"}`);
    if (status.indices.length > 0) {
      console.log(`  Indices: ${status.indices.join(", ")}`);
    }

    console.log("\nAgent Builder MCP (Kibana Manage MCP endpoint):");
    console.log(`  Status:  ${status.agentBuilderOk ? "✓ connected" : "✗ failed"}`);
    if (status.agentBuilderTools.length > 0) {
      console.log(`  Tools:   ${status.agentBuilderTools.join(", ")}`);
    }

    const allOk = status.standaloneOk && status.agentBuilderOk;
    console.log(`\n${allOk ? "✓ Both MCP servers connected. Ready for demo." : "✗ One or more MCP servers failed. Check credentials."}\n`);

    if (!allOk) process.exit(1);
  } catch (e) {
    console.log("FAIL");
    console.error(`MCP status check error: ${e}`);
    console.error("Ensure ELASTIC_CLOUD_URL, ELASTIC_API_KEY, ELASTIC_MCP_URL are set.");
    process.exit(1);
  }
}
