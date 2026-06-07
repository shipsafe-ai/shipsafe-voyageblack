variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run services"
  type        = string
  default     = "us-central1"
}

variable "gemini_model" {
  description = "Gemini model name (loaded from env, not hardcoded)"
  type        = string
  default     = "gemini-2.5-flash"
}

variable "image_tag" {
  description = "Container image tag to deploy"
  type        = string
  default     = "latest"
}
