#!/bin/sh
set -eu

python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:7860/health", timeout=3) as response:
    payload = json.load(response)
if payload.get("status") != "ok":
    raise SystemExit("backend health response is not ok")
PY

supervisor_status="$(
  /usr/bin/supervisorctl -c /srv/deploy/supervisord.conf status 2>/dev/null
)"
for process_name in redis backend ai-worker render-worker; do
  if ! printf '%s\n' "${supervisor_status}" \
    | grep -Eq "^${process_name}[[:space:]]+RUNNING([[:space:]]|$)"; then
    echo "required Supervisor process is not RUNNING: ${process_name}" >&2
    exit 1
  fi
done
