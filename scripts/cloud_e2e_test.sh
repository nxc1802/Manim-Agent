#!/usr/bin/env bash
set -euo pipefail

API_BASE="https://cuong2004-manim-agent.hf.space"
VOICE_TIMEOUT=120
RENDER_TIMEOUT=300

log() { echo "[*] $1"; }

req() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -s -X "$method" "$API_BASE$path" -H "Content-Type: application/json" -d "$data"
  else
    curl -s -X "$method" "$API_BASE$path"
  fi
}

# 1. Create Project
log "Step 1: Creating Project..."
project=$(req POST "/v1/projects" '{"title": "E2E Curl Test", "source_language": "vi"}')
project_id=$(echo "$project" | jq -r '.id')
log "Project created: $project_id"

# 2. Create Scene
log "Step 2: Creating Scene..."
scene=$(req POST "/v1/projects/$project_id/scenes" '{"scene_order": 0, "storyboard_text": "Hello world circle"}')
scene_id=$(echo "$scene" | jq -r '.id')
log "Scene created: $scene_id"

# 3. Director
log "Step 3: Generating Storyboard..."
req POST "/v1/scenes/$scene_id/generate-storyboard" > /dev/null
log "Storyboard generated."

# 4. Approve
log "Step 4: Approving Storyboard..."
req POST "/v1/scenes/$scene_id/approve-storyboard" > /dev/null
log "Storyboard approved."

# 5. Plan
log "Step 5: Planning..."
req POST "/v1/scenes/$scene_id/plan" > /dev/null
log "Plan generated."

# 6. Build
log "Step 6: Generating Code..."
req POST "/v1/scenes/$scene_id/generate-code" '{"enqueue_preview": false}' > /dev/null
log "Code generated."

# 7. Voice
log "Step 7: Enqueueing Voice..."
voice=$(req POST "/v1/scenes/$scene_id/voice" '{"language": "vi"}')
voice_job_id=$(echo "$voice" | jq -r '.voice_job_id')
log "Voice job: $voice_job_id"

start=$(date +%s)
while true; do
  current=$(date +%s)
  if (( current - start > VOICE_TIMEOUT )); then echo "FAILED: Voice timeout"; exit 1; fi
  status_resp=$(req GET "/v1/voice-jobs/$voice_job_id")
  status=$(echo "$status_resp" | jq -r '.status')
  log "Voice Status: $status"
  [[ "$status" == "completed" ]] && break
  [[ "$status" == "failed" ]] && { echo "FAILED: Voice job failed"; exit 1; }
  sleep 5
done

# 8. Sync
log "Step 8: Syncing Timeline..."
req POST "/v1/scenes/$scene_id/sync-timeline" > /dev/null
log "Timeline synced."

# 9. Render
log "Step 9: Enqueueing Render..."
render=$(req POST "/v1/projects/$project_id/render" "{\"render_type\": \"preview\", \"quality\": \"720p\", \"scene_id\": \"$scene_id\"}")
render_job_id=$(echo "$render" | jq -r '.job_id')
log "Render job: $render_job_id"

start=$(date +%s)
while true; do
  current=$(date +%s)
  if (( current - start > RENDER_TIMEOUT )); then echo "FAILED: Render timeout"; exit 1; fi
  status_resp=$(req GET "/v1/jobs/$render_job_id")
  status=$(echo "$status_resp" | jq -r '.status')
  prog=$(echo "$status_resp" | jq -r '.progress')
  log "Render Status: $status ($prog%)"
  [[ "$status" == "completed" ]] && { echo "SUCCESS! URL: $(echo "$status_resp" | jq -r '.asset_url')"; break; }
  [[ "$status" == "failed" ]] && { echo "FAILED: Render job failed"; echo "$status_resp" | jq -r '.logs'; exit 1; }
  sleep 10
done
