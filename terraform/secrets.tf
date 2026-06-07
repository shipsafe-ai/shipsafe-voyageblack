# Secrets in GCP Secret Manager — values set by `voyageblack init` or manually
# Terraform creates the secret shells; actual values set via gcloud CLI

resource "google_secret_manager_secret" "elastic_cloud_url" {
  secret_id = "ELASTIC_CLOUD_URL"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "elastic_api_key" {
  secret_id = "ELASTIC_API_KEY"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "elastic_mcp_url" {
  secret_id = "ELASTIC_MCP_URL"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "elastic_es_mcp_url" {
  secret_id = "ELASTIC_ES_MCP_URL"
  replication {
    auto {}
  }
}
