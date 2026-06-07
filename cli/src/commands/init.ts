import * as readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { execSync } from "node:child_process";

interface InitOptions {
  project?: string;
  region: string;
}

const REQUIRED_SECRETS = [
  { name: "ELASTIC_CLOUD_URL", prompt: "Elastic Cloud Serverless URL (https://...elastic.cloud): " },
  { name: "ELASTIC_API_KEY", prompt: "Elastic API Key (with feature_agentBuilder.read): " },
  { name: "ELASTIC_MCP_URL", prompt: "Kibana Agent Builder MCP URL (from Manage MCP): " },
];

async function promptSecretValue(rl: readline.Interface, label: string): Promise<string> {
  return rl.question(label);
}

function storeSecret(name: string, value: string, project: string): void {
  try {
    execSync(`gcloud secrets create ${name} --project ${project} --replication-policy automatic 2>/dev/null`, { stdio: "pipe" });
  } catch {
    // Already exists — proceed
  }
  const escaped = value.replace(/'/g, "'\\''");
  execSync(`echo -n '${escaped}' | gcloud secrets versions add ${name} --project ${project} --data-file -`, { stdio: ["pipe", "inherit", "inherit"] });
}

function verifyGcloud(): boolean {
  try {
    execSync("gcloud version", { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

export async function initCommand(opts: InitOptions): Promise<void> {
  console.log("\nVoyageBlack — init\n");

  if (!verifyGcloud()) {
    console.error("Error: gcloud CLI not found. Install from https://cloud.google.com/sdk/docs/install");
    process.exit(1);
  }

  const rl = readline.createInterface({ input, output });

  let project = opts.project;
  if (!project) {
    project = await rl.question("GCP project ID: ");
  }
  const region = opts.region;
  console.log(`\nProject: ${project}  Region: ${region}\n`);

  console.log("Storing secrets in GCP Secret Manager...\n");
  for (const secret of REQUIRED_SECRETS) {
    const value = await promptSecretValue(rl, secret.prompt);
    if (!value.trim()) {
      console.log(`Skipping ${secret.name} (empty)`);
      continue;
    }
    try {
      storeSecret(secret.name, value.trim(), project);
      console.log(`  ✓ ${secret.name}`);
    } catch (e) {
      console.error(`  ✗ ${secret.name}: ${e}`);
    }
  }

  rl.close();

  console.log("\nSecrets stored. Run `voyageblack connect` to verify MCP endpoints.\n");
}
