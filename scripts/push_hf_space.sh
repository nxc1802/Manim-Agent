#!/usr/bin/env bash
# Staging directory + git push --force to a Hugging Face Space repo (thin Docker bundle).
# Bundle layout: Dockerfile.in, README.template.md (placeholders __GHCR_IMAGE__, __GITHUB_REPOSITORY__).
#
# Required env: HF_TOKEN, HF_SPACE_REPO (e.g. org/space-name), HF_BUNDLE (relative to repo root),
#              GHCR_IMAGE, GITHUB_REPOSITORY
# Optional:     COMMIT_MESSAGE

set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_SPACE_REPO:?HF_SPACE_REPO is required}"
: "${HF_BUNDLE:?HF_BUNDLE is required}"
: "${GHCR_IMAGE:?GHCR_IMAGE is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

COMMIT_MESSAGE="${COMMIT_MESSAGE:-Deploy Hugging Face Space}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUNDLE_ABS="${REPO_ROOT}/${HF_BUNDLE}"

if [[ ! -d "${BUNDLE_ABS}" ]]; then
  echo "ERROR: bundle not found: ${BUNDLE_ABS}" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
cleanup() { rm -rf "${STAGE}"; }
trap cleanup EXIT

cp -a "${BUNDLE_ABS}/." "${STAGE}/"

if [[ ! -f "${STAGE}/Dockerfile.in" || ! -f "${STAGE}/README.template.md" ]]; then
  echo "ERROR: bundle must contain Dockerfile.in and README.template.md" >&2
  exit 1
fi

sed -e "s|__GHCR_IMAGE__|${GHCR_IMAGE}|g" \
  -e "s|__GITHUB_REPOSITORY__|${GITHUB_REPOSITORY}|g" \
  "${STAGE}/Dockerfile.in" >"${STAGE}/Dockerfile"
rm -f "${STAGE}/Dockerfile.in"

sed -e "s|__GHCR_IMAGE__|${GHCR_IMAGE}|g" \
  -e "s|__GITHUB_REPOSITORY__|${GITHUB_REPOSITORY}|g" \
  "${STAGE}/README.template.md" >"${STAGE}/README.md"
rm -f "${STAGE}/README.template.md"

cd "${STAGE}"
git init -q
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git config user.name "github-actions[bot]"
git add Dockerfile README.md
git commit -q -m "${COMMIT_MESSAGE}"

REMOTE="https://oauth2:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE_REPO}.git"
git remote add origin "${REMOTE}"
git branch -M main
git push --force origin main

echo "OK: pushed to https://huggingface.co/spaces/${HF_SPACE_REPO}"
