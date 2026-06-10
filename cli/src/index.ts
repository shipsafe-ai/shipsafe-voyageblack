#!/usr/bin/env node
import { Command } from "commander";
import { initCommand } from "./commands/init.js";
import { demoCommand } from "./commands/demo.js";
import { connectCommand } from "./commands/connect.js";

const program = new Command();

const DEFAULT_API = "https://voyageblack-agent-o34wppiwiq-uc.a.run.app";

program
  .name("voyageblack")
  .description("VoyageBlack — incident postmortem engine powered by Elastic + Gemini")
  .version("0.2.0");

program
  .command("init")
  .description("Configure GCP secrets and verify MCP connectivity")
  .option("--project <project>", "GCP project ID")
  .option("--region <region>", "GCP region", "us-central1")
  .action(initCommand);

program
  .command("demo")
  .description("Seed Hormuz Crisis fixtures and run full postmortem pipeline")
  .option("--api <url>", "VoyageBlack API URL", DEFAULT_API)
  .option("--wait <seconds>", "Wait for ELSER ingestion", "30")
  .action(demoCommand);

program
  .command("connect")
  .description("Test both MCP endpoints (Agent Builder + standalone Elasticsearch)")
  .option("--api <url>", "VoyageBlack API URL", DEFAULT_API)
  .action(connectCommand);

program.parse();
