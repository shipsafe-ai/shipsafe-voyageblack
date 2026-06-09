#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-shipsafe-ai}"
REGION="${GCP_REGION:-us-central1}"
TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/voyageblack"

echo "Building VoyageBlack images → ${REGISTRY}"

# Ensure Artifact Registry repo exists
gcloud artifacts repositories create voyageblack \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT}" 2>/dev/null || true

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Build and push agent
echo "→ agent"
docker build -t "${REGISTRY}/agent:${TAG}" .
docker push "${REGISTRY}/agent:${TAG}"

# Build and push dashboard
echo "→ dashboard"
docker build -t "${REGISTRY}/dashboard:${TAG}" dashboard/dashboard/
docker push "${REGISTRY}/dashboard:${TAG}"

echo "Images pushed. Running terraform apply..."
cd terraform
terraform init -upgrade -input=false
terraform apply \
  -var="project=${PROJECT}" \
  -var="region=${REGION}" \
  -var="image_tag=${TAG}" \
  -auto-approve

echo ""
echo "Done. Services:"
gcloud run services list --region="${REGION}" --project="${PROJECT}" \
  --filter="name~voyageblack OR name~es-mcp" \
  --format="table(name,status.url)"
