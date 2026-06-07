output "agent_url" {
  description = "VoyageBlack agent service URL"
  value       = google_cloud_run_v2_service.agent.uri
}

output "dashboard_url" {
  description = "VoyageBlack dashboard URL"
  value       = google_cloud_run_v2_service.dashboard.uri
}

output "es_mcp_url" {
  description = "Standalone Elasticsearch MCP server URL (internal)"
  value       = "${google_cloud_run_v2_service.es_mcp.uri}/mcp"
}

output "set_es_mcp_secret_cmd" {
  description = "Command to store the deployed ES MCP URL as a secret"
  value       = "echo -n '${google_cloud_run_v2_service.es_mcp.uri}/mcp' | gcloud secrets versions add ELASTIC_ES_MCP_URL --project ${var.project} --data-file -"
}
