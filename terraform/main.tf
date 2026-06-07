terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

# Artifact Registry repository for container images
resource "google_artifact_registry_repository" "voyageblack" {
  location      = var.region
  repository_id = "voyageblack"
  format        = "DOCKER"
  description   = "VoyageBlack container images"
}

# Service account for Cloud Run services
resource "google_service_account" "voyageblack" {
  account_id   = "voyageblack-agent"
  display_name = "VoyageBlack Agent Service Account"
}

resource "google_project_iam_member" "secretmanager_access" {
  project = var.project
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.voyageblack.email}"
}

resource "google_project_iam_member" "vertex_user" {
  project = var.project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.voyageblack.email}"
}
