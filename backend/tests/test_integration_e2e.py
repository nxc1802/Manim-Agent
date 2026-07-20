#!/usr/bin/env python3
"""Manual no-HITL smoke for the current Master -> Builder pipeline.

This script intentionally is not collected by pytest because it spends real
provider quota. It requires Backend, Redis, AI worker and Supabase to be ready.

Usage:
    BACKEND_URL=http://localhost:8000 backend/.venv/bin/python \
      backend/tests/test_integration_e2e.py
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
TIMEOUT_SECONDS = int(os.getenv("E2E_TIMEOUT_SECONDS", "900"))
POLL_INTERVAL_SECONDS = float(os.getenv("E2E_POLL_INTERVAL_SECONDS", "3"))

headers: dict[str, str] = {}
if token := os.getenv("BACKEND_TOKEN"):
    headers["Authorization"] = f"Bearer {token}"
client = httpx.Client(base_url=BACKEND_URL, headers=headers, timeout=60.0)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def get_runs(project_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/v1/projects/{project_id}/ai-runs")
    response.raise_for_status()
    return list(response.json())


def get_steps(project_id: str, run_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/v1/projects/{project_id}/ai-runs/{run_id}/steps")
    response.raise_for_status()
    return list(response.json())


def get_scenes(project_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/v1/projects/{project_id}/scenes?page=1&limit=100")
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("items", payload))


def wait_for_run(project_id: str, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_status: str | None = None
    while time.monotonic() < deadline:
        run = next((item for item in get_runs(project_id) if item["id"] == run_id), None)
        if run is None:
            raise RuntimeError(f"Run {run_id} disappeared")
        if run["status"] != last_status:
            last_status = str(run["status"])
            log(f"Run {run_id}: {last_status}")
        if run["status"] == "completed":
            return run
        if run["status"] in {"failed", "cancelled"}:
            errors = [step.get("error") for step in get_steps(project_id, run_id) if step.get("error")]
            raise RuntimeError(f"Run {run_id} ended as {run['status']}: {errors}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Timed out waiting for run {run_id}")


def wait_for_scene_runs(project_id: str, scene_ids: set[str]) -> list[dict[str, Any]]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        runs = get_runs(project_id)
        latest_by_scene: dict[str, dict[str, Any]] = {}
        for run in reversed(runs):
            scene_id = run.get("scene_id")
            if scene_id in scene_ids:
                latest_by_scene[scene_id] = run
        if scene_ids.issubset(latest_by_scene):
            return [wait_for_run(project_id, latest_by_scene[scene_id]["id"]) for scene_id in scene_ids]
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError("Timed out waiting for auto-dispatched Builder runs")


def main() -> None:
    prompt = "Explain the derivative as slope with two short visual scenes."
    response = client.post(
        "/v1/projects",
        json={"title": "No-HITL Runtime Smoke", "description": prompt, "source_language": "en"},
    )
    response.raise_for_status()
    project = response.json()
    project_id = project["id"]
    log(f"Created project {project_id}")

    response = client.post(
        f"/v1/projects/{project_id}/generate-scenes",
        json={"prompt": prompt, "hitl_enabled": False},
    )
    response.raise_for_status()
    master = response.json()["run"]
    wait_for_run(project_id, master["id"])

    scenes = get_scenes(project_id)
    if not scenes or any(int(scene["scene_order"]) < 1 for scene in scenes):
        raise AssertionError("Master did not persist a non-empty 1-based storyboard")
    child_runs = wait_for_scene_runs(project_id, {scene["id"] for scene in scenes})

    refreshed_scenes = get_scenes(project_id)
    if any(
        scene.get("generation_status") != "completed" or not scene.get("manim_code")
        for scene in refreshed_scenes
    ):
        raise AssertionError("At least one Builder did not persist approved Manim code")

    for run in child_runs:
        builder = next(step for step in get_steps(project_id, run["id"]) if step["kind"] == "builder")
        output = builder.get("final_output") or builder.get("draft_output") or {}
        review = output.get("auto_review") or {}
        if not (
            review.get("passed") is True
            and (review.get("code") or {}).get("passed") is True
            and (review.get("visual") or {}).get("passed") is True
        ):
            raise AssertionError(f"Builder {builder['id']} lacks a fully passing auto-review")

    log(
        f"PASS: Master + {len(child_runs)} auto-dispatched Builder run(s); "
        "code and visual review both passed"
    )


if __name__ == "__main__":
    main()
