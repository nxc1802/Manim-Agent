#!/usr/bin/env python3
"""Verify Hugging Face Spaces repos are reachable with HF_TOKEN (used by GitHub Actions)."""

from __future__ import annotations

import os
import sys


def main() -> int:
    token = (os.environ.get("HF_TOKEN") or "").strip()
    repos = [
        (os.environ.get("HF_SPACE_API_REPO") or "").strip(),
        (os.environ.get("HF_SPACE_MANIM_WORKER_REPO") or "").strip(),
        (os.environ.get("HF_SPACE_TTS_WORKER_REPO") or "").strip(),
    ]
    repos = [r for r in repos if r]
    if not token:
        print("HF_TOKEN not set; skipping HF Space verification.")
        return 0
    if not repos:
        print("No HF_SPACE_*_REPO set; skipping (configure three repo ids, e.g. org/space-api).")
        return 0

    from huggingface_hub import HfApi
    from huggingface_hub.errors import HfHubHTTPError

    api = HfApi(token=token)
    for rid in repos:
        try:
            api.repo_info(repo_id=rid, repo_type="space")
        except HfHubHTTPError as exc:
            print(f"ERROR: cannot access Space {rid}: {exc}", file=sys.stderr)
            return 1
        print(f"OK: {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
