#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: $0 <tested-git-ref> <new-destination-directory>" >&2
  exit 2
fi

tested_ref="$1"
destination="$2"
script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(git -C "${script_dir}" rev-parse --show-toplevel)"
tested_sha="$(git -C "${repository_root}" rev-parse --verify "${tested_ref}^{commit}")"

if [[ -e "${destination}" ]]; then
  echo "Hugging Face payload destination must not already exist: ${destination}" >&2
  exit 1
fi
mkdir -p -- "${destination}"
destination="$(CDPATH= cd -- "${destination}" && pwd)"

case "${destination}/" in
  "${repository_root}/"|"${repository_root}/.git/"*)
    echo "refusing to create a payload inside the repository root or .git" >&2
    exit 1
    ;;
esac

# Keep this list synchronized with Dockerfile COPY instructions. git archive is
# deliberate: an untracked local file, test artifact or secret can never leak
# into the Space payload.
payload_paths=(
  .dockerignore
  Dockerfile
  backend/requirements.lock
  backend/app
  ai_core/requirements.lock
  ai_core/app
  ai_core/config
  shared
  deploy/huggingface/README.md
  deploy/huggingface/entrypoint.sh
  deploy/huggingface/healthcheck.sh
  deploy/huggingface/redis.conf
  deploy/huggingface/service-entrypoint.sh
  deploy/huggingface/supervisord.conf
)

git -C "${repository_root}" archive --format=tar "${tested_sha}" -- "${payload_paths[@]}" \
  | tar -xf - -C "${destination}"

# The Space-specific README owns the required Hugging Face metadata. Project
# documentation and the staging script itself are intentionally not mirrored.
cp -p -- \
  "${destination}/deploy/huggingface/README.md" \
  "${destination}/README.md"
rm -- "${destination}/deploy/huggingface/README.md"

while IFS= read -r -d '' marker; do
  rm -- "${marker}"
done < <(find "${destination}" -type f -name .gitkeep -print0)

printf '%s\n' "${tested_sha}" >"${destination}/SOURCE_REVISION"

required_files=(
  .dockerignore
  Dockerfile
  README.md
  SOURCE_REVISION
  backend/requirements.lock
  backend/app/main.py
  ai_core/requirements.lock
  ai_core/app/worker.py
  ai_core/config/agent_models.yaml
  ai_core/config/manim_compatibility.yaml
  shared/schemas/project.py
  deploy/huggingface/entrypoint.sh
  deploy/huggingface/healthcheck.sh
  deploy/huggingface/redis.conf
  deploy/huggingface/service-entrypoint.sh
  deploy/huggingface/supervisord.conf
)
for required_file in "${required_files[@]}"; do
  if [[ ! -f "${destination}/${required_file}" ]]; then
    echo "required Hugging Face payload file is missing: ${required_file}" >&2
    exit 1
  fi
done

if [[ ! -x "${destination}/deploy/huggingface/entrypoint.sh" ]] \
  || [[ ! -x "${destination}/deploy/huggingface/healthcheck.sh" ]] \
  || [[ ! -x "${destination}/deploy/huggingface/service-entrypoint.sh" ]]; then
  echo "Hugging Face entrypoint scripts must retain executable mode" >&2
  exit 1
fi

if ! head -n 20 "${destination}/README.md" | grep -Fxq "sdk: docker" \
  || ! head -n 20 "${destination}/README.md" | grep -Fxq "app_port: 7860"; then
  echo "Space README is missing required Docker metadata" >&2
  exit 1
fi

if find "${destination}" -type l -print -quit | grep -q .; then
  echo "symlinks are not permitted in the Hugging Face payload" >&2
  exit 1
fi

for forbidden_path in \
  frontend \
  .github \
  docs \
  backend/tests \
  backend/supabase \
  ai_core/tests; do
  if [[ -e "${destination}/${forbidden_path}" ]]; then
    echo "forbidden path entered the Hugging Face payload: ${forbidden_path}" >&2
    exit 1
  fi
done

forbidden_file="$(
  find "${destination}" -type f \
    \( -name '.env' -o -name '.env.*' -o -name '*.pem' -o -name '*.key' \
       -o -name '*.pyc' -o -name '*.test.ts' -o -name '*.test.tsx' \) \
    -print -quit
)"
if [[ -n "${forbidden_file}" ]]; then
  echo "forbidden file entered the Hugging Face payload: ${forbidden_file}" >&2
  exit 1
fi

manifest_file="${destination}/PAYLOAD_MANIFEST.sha256"
if command -v sha256sum >/dev/null 2>&1; then
  (
    cd "${destination}"
    find . -type f ! -name PAYLOAD_MANIFEST.sha256 -print0 \
      | sort -z \
      | xargs -0 sha256sum
  ) >"${manifest_file}"
else
  (
    cd "${destination}"
    find . -type f ! -name PAYLOAD_MANIFEST.sha256 -print0 \
      | sort -z \
      | xargs -0 shasum -a 256
  ) >"${manifest_file}"
fi

file_count="$(find "${destination}" -type f | wc -l | tr -d '[:space:]')"
payload_bytes="$(du -sk "${destination}" | awk '{print $1 * 1024}')"
echo "Prepared Hugging Face payload from ${tested_sha}: ${file_count} files, ${payload_bytes} bytes"
