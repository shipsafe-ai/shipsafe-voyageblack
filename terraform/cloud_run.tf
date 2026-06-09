locals {
  agent_image     = "${var.region}-docker.pkg.dev/${var.project}/voyageblack/agent:${var.image_tag}"
  dashboard_image = "${var.region}-docker.pkg.dev/${var.project}/voyageblack/dashboard:${var.image_tag}"
  es_mcp_image    = "${var.region}-docker.pkg.dev/${var.project}/voyageblack/es-mcp:latest"
}

# ─────────────────────────────────────────────
# 1. Standalone Elasticsearch MCP Server
#    Runs docker.elastic.co/mcp/elasticsearch in HTTP mode
#    Used by ImpactCalculator and /postmortems endpoint
# ─────────────────────────────────────────────
resource "google_cloud_run_v2_service" "es_mcp" {
  name     = "es-mcp-server"
  location = var.region

  template {
    service_account = google_service_account.voyageblack.email

    containers {
      image = local.es_mcp_image

      args = ["http"]

      env {
        name = "ES_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.elastic_cloud_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ES_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.elastic_api_key.secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_secret_manager_secret.elastic_cloud_url,
    google_secret_manager_secret.elastic_api_key,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "es_mcp_invoker" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.es_mcp.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.voyageblack.email}"
}

# ─────────────────────────────────────────────
# 2. VoyageBlack Agent (FastAPI on port 8080)
#    Runs the orchestrator + all specialists
#    Connects to both MCP servers
# ─────────────────────────────────────────────
resource "google_cloud_run_v2_service" "agent" {
  name     = "voyageblack-agent"
  location = var.region

  template {
    service_account = google_service_account.voyageblack.email

    containers {
      image = local.agent_image

      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "1"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      # Standalone ES MCP URL — wired to the Cloud Run es-mcp-server service
      env {
        name  = "ELASTIC_ES_MCP_URL"
        value = "${google_cloud_run_v2_service.es_mcp.uri}/mcp"
      }
      env {
        name = "ELASTIC_CLOUD_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.elastic_cloud_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ELASTIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.elastic_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ELASTIC_MCP_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.elastic_mcp_url.secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  depends_on = [
    google_project_service.run,
    google_cloud_run_v2_service.es_mcp,
    google_secret_manager_secret.elastic_cloud_url,
    google_secret_manager_secret.elastic_api_key,
    google_secret_manager_secret.elastic_mcp_url,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "agent_public" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ─────────────────────────────────────────────
# 3. VoyageBlack Dashboard (Next.js)
# ─────────────────────────────────────────────
resource "google_cloud_run_v2_service" "dashboard" {
  name     = "voyageblack-dashboard"
  location = var.region

  template {
    service_account = google_service_account.voyageblack.email

    containers {
      image = local.dashboard_image

      env {
        name  = "NEXT_PUBLIC_API_URL"
        value = google_cloud_run_v2_service.agent.uri
      }

      ports {
        container_port = 3001
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  depends_on = [google_cloud_run_v2_service.agent]
}

resource "google_cloud_run_v2_service_iam_member" "dashboard_public" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.dashboard.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
