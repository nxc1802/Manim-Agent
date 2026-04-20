#!/usr/bin/env bash
# Quick HTTP checks against deployed Hugging Face Spaces (no secrets required).
# Override defaults with MANIM_AGENT_API_HF, MANIM_AGENT_WORKER_RENDER_HF, MANIM_AGENT_WORKER_TTS_HF.
set -euo pipefail

API="${MANIM_AGENT_API_HF:-https://cuong2004-manim-agent.hf.space}"
RENDER="${MANIM_AGENT_WORKER_RENDER_HF:-https://cuong2004-manim-agent-worker-render.hf.space}"
TTS="${MANIM_AGENT_WORKER_TTS_HF:-https://cuong2004-manim-agent-worker-tts.hf.space}"

curl_json() {
  local url="$1"
  local want="$2"
  code=$(curl -sS -o /tmp/smoke_hf_body.json -w "%{http_code}" "$url")
  if [[ "$code" != "$want" ]]; then
    echo "FAIL $url expected HTTP $want got $code" >&2
    cat /tmp/smoke_hf_body.json >&2 || true
    exit 1
  fi
}

echo "API $API"
curl_json "$API/health" 200
curl_json "$API/ready" 200
python3 -c "import json; d=json.load(open('/tmp/smoke_hf_body.json')); assert d.get('status')=='ready' and d.get('redis') is True, d"

curl_json "$API/v1/primitives/catalog" 200
curl_json "$API/v1/projects" 200

echo "Render worker $RENDER"
curl_json "$RENDER/health" 200
curl_json "$RENDER/" 200

echo "TTS worker $TTS"
curl_json "$TTS/health" 200
curl_json "$TTS/" 200

echo "OK: all smoke checks passed"
