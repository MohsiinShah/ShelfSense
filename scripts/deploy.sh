#!/usr/bin/env bash
# One-shot deploy: Firestore + Cloud Storage + Cloud Run (API) + Firebase Hosting (dashboard).
# Usage: scripts/deploy.sh <gcp-project-id>
set -euo pipefail
PROJECT="${1:?project id}"
REGION=us-central1
BUCKET="${PROJECT}-videos"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

gcloud config set project "$PROJECT" >/dev/null

echo "== enabling APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com aiplatform.googleapis.com storage.googleapis.com firebase.googleapis.com \
  firebasehosting.googleapis.com

echo "== Firestore"
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  gcloud firestore databases create --location=nam5 --type=firestore-native

echo "== video bucket"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
cat > /tmp/shelfsense-lifecycle.json <<'EOF'
{"rule":[{"action":{"type":"Delete"},"condition":{"age":1,"matchesPrefix":["uploads/"]}}]}
EOF
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=/tmp/shelfsense-lifecycle.json
gcloud storage cp "$ROOT"/samples/clips/*.mp4 "gs://$BUCKET/samples/"

echo "== service account"
SA="shelfsense-api@${PROJECT}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create shelfsense-api --display-name="ShelfSense API"
for role in roles/aiplatform.user roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$role" --condition=None >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin >/dev/null

echo "== Cloud Run"
ADMIN_TOKEN="${ADMIN_TOKEN:-$(openssl rand -hex 16)}"
gcloud run deploy shelfsense-api --source "$ROOT/backend" --region "$REGION" \
  --service-account "$SA" --allow-unauthenticated \
  --memory 1Gi --cpu 1 --timeout 300 --min-instances 1 --max-instances 5 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,VIDEO_BUCKET=$BUCKET,GEMINI_MODEL=${GEMINI_MODEL:-gemini-3-flash-preview},ADMIN_TOKEN=$ADMIN_TOKEN"
echo "ADMIN_TOKEN=$ADMIN_TOKEN (keep private; used for POST /api/admin/seed)"

echo "== Firebase Hosting + Firestore rules"
firebase projects:addfirebase "$PROJECT" >/dev/null 2>&1 || true
cd "$ROOT" && firebase deploy --project "$PROJECT" --only hosting,firestore:rules --non-interactive

echo "== done: https://shelfsense-demo.web.app"
