#!/usr/bin/env python3
"""Replace each Hugging Face Space repo with a thin Docker bundle (README + Dockerfile).

Requires:
  HF_TOKEN (secret)
  HF_SPACE_API_REPO, HF_SPACE_MANIM_WORKER_REPO, HF_SPACE_TTS_WORKER_REPO (repo variables)
  GITHUB_REPOSITORY_OWNER (lowercase owner for ghcr.io image names)

Optional:
  HF_IMAGE_TAG — image tag on GHCR (default: latest)
"""

from __future__ import annotations

import os
import sys

from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi
from huggingface_hub.hf_api import RepoFile


def _readme(title: str, *, app_port: int | None) -> bytes:
    gh = os.environ.get("GITHUB_REPOSITORY", "owner/repo")
    header = f"---\ntitle: {title}\nsdk: docker\n"
    if app_port is not None:
        header += f"app_port: {app_port}\n"
    header += "---\n\n"
    body = (
        "Image from GHCR (build and push images separately). "
        f"Source: https://github.com/{gh}\n"
    )
    return (header + body).encode()


def _dockerfile(suffix: str) -> bytes:
    owner = os.environ["GITHUB_REPOSITORY_OWNER"].lower()
    tag = (os.environ.get("HF_IMAGE_TAG") or "latest").strip()
    return f"FROM ghcr.io/{owner}/manim-agent-{suffix}:{tag}\n".encode()


def _sync_one(
    api: HfApi,
    *,
    repo_id: str,
    image_suffix: str,
    title: str,
    readme_port: int | None,
) -> None:
    existing_paths: list[str] = []
    for item in api.list_repo_tree(
        repo_id=repo_id,
        repo_type="space",
        recursive=True,
        expand=True,
    ):
        if isinstance(item, RepoFile):
            existing_paths.append(item.path)

    operations: list = [CommitOperationDelete(path_in_repo=p) for p in existing_paths]
    operations.append(
        CommitOperationAdd(
            path_in_repo="README.md",
            path_or_fileobj=_readme(title, app_port=readme_port),
        )
    )
    operations.append(
        CommitOperationAdd(
            path_in_repo="Dockerfile",
            path_or_fileobj=_dockerfile(image_suffix),
        )
    )

    api.create_commit(
        repo_id=repo_id,
        repo_type="space",
        operations=operations,
        commit_message="Sync Space from Manim-Agent (Dockerfile + README)",
    )
    print(f"Pushed to Space {repo_id} (image manim-agent-{image_suffix})")


def main() -> int:
    token = (os.environ.get("HF_TOKEN") or "").strip()
    if not token:
        print("ERROR: HF_TOKEN is required", file=sys.stderr)
        return 1
    owner = (os.environ.get("GITHUB_REPOSITORY_OWNER") or "").strip()
    if not owner:
        print("ERROR: GITHUB_REPOSITORY_OWNER is required", file=sys.stderr)
        return 1

    specs: list[tuple[str, str, str, int | None]] = [
        ("HF_SPACE_API_REPO", "api", "Manim Agent API", 7860),
        ("HF_SPACE_MANIM_WORKER_REPO", "worker", "Manim Agent Worker (Render)", None),
        ("HF_SPACE_TTS_WORKER_REPO", "tts-worker", "Manim Agent Worker (TTS)", None),
    ]

    api = HfApi(token=token)
    for env_key, suffix, title, port in specs:
        repo_id = (os.environ.get(env_key) or "").strip()
        if not repo_id:
            print(f"ERROR: {env_key} is required", file=sys.stderr)
            return 1
        try:
            _sync_one(api, repo_id=repo_id, image_suffix=suffix, title=title, readme_port=port)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {repo_id}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
