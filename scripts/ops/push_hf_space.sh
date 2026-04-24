#!/usr/bin/env bash
# Stage a monorepo *slice* matching what each Dockerfile COPYs, pick the right Dockerfile
# (same idea as Dockerfile.worker → Dockerfile per Space), then git push --force to HF.
#
# Required env:
#   HF_TOKEN, HF_SPACE_REPO, GITHUB_REPOSITORY, HF_DEPLOY_FLAVOR (api | render | tts)
# Optional:
#   COMMIT_MESSAGE

set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_SPACE_REPO:?HF_SPACE_REPO is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${HF_DEPLOY_FLAVOR:?HF_DEPLOY_FLAVOR is required (api, render, or tts)}"

COMMIT_MESSAGE="${COMMIT_MESSAGE:-Deploy Hugging Face Space}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STAGE="$(mktemp -d)"
cleanup() { rm -rf "${STAGE}"; }
trap cleanup EXIT

# Shared by all Spaces (worker code imports backend/shared/ai_engine).
mkdir -p "${STAGE}"
cp -a "${REPO_ROOT}/backend" "${STAGE}/"
cp -a "${REPO_ROOT}/shared" "${STAGE}/"
cp -a "${REPO_ROOT}/worker" "${STAGE}/"
cp -a "${REPO_ROOT}/ai_engine" "${STAGE}/"
cp "${REPO_ROOT}/pyproject.toml" "${STAGE}/"
cp "${REPO_ROOT}/README.md" "${STAGE}/"
cp "${REPO_ROOT}/requirements.txt" "${STAGE}/"

case "${HF_DEPLOY_FLAVOR}" in
  api)
    cp -a "${REPO_ROOT}/primitives" "${STAGE}/"
    cp "${REPO_ROOT}/docker/api/Dockerfile" "${STAGE}/Dockerfile"
    readme_template="${REPO_ROOT}/deploy/huggingface/api/README.template.md"
    ;;
  render)
    cp -a "${REPO_ROOT}/primitives" "${STAGE}/"
    cp -a "${REPO_ROOT}/examples" "${STAGE}/"
    cp -a "${REPO_ROOT}/docs" "${STAGE}/"
    cp "${REPO_ROOT}/docker/worker/Dockerfile" "${STAGE}/Dockerfile"
    readme_template="${REPO_ROOT}/deploy/huggingface/render-worker/README.template.md"
    ;;
  tts)
    mkdir -p "${STAGE}/docker/tts-worker"
    cp "${REPO_ROOT}/docker/tts-worker/piper.docker.yaml" "${STAGE}/docker/tts-worker/piper.docker.yaml"
    cp "${REPO_ROOT}/docker/tts-worker/Dockerfile" "${STAGE}/Dockerfile"
    readme_template="${REPO_ROOT}/deploy/huggingface/tts-worker/README.template.md"
    ;;
  *)
    echo "ERROR: HF_DEPLOY_FLAVOR must be api, render, or tts (got: ${HF_DEPLOY_FLAVOR})" >&2
    exit 1
    ;;
esac

sed -e "s|__GITHUB_REPOSITORY__|${GITHUB_REPOSITORY}|g" \
  "${readme_template}" >"${STAGE}/README.md"

cd "${STAGE}"
git init -q
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git config user.name "github-actions[bot]"
git add -A
git commit -q -m "${COMMIT_MESSAGE}"

REMOTE="https://oauth2:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE_REPO}.git"
git remote add origin "${REMOTE}"
git branch -M main
git push --force origin main

echo "OK: pushed to https://huggingface.co/spaces/${HF_SPACE_REPO}"
