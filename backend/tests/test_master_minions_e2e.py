#!/usr/bin/env python3
"""Manual HITL smoke for the current Master -> auto-dispatched Builder flow.

The internal code/visual reviewers are recorded inside Builder ``auto_review``;
they are not durable approval steps. This script spends real provider quota and
therefore is not collected by pytest.
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


def wait_for_step(project_id: str, run_id: str, kind: str) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        step = next((item for item in get_steps(project_id, run_id) if item["kind"] == kind), None)
        if step and step["status"] == "pending_review":
            return step
        if step and step["status"] == "failed":
            raise RuntimeError(f"{kind} failed: {step.get('error')}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Timed out waiting for {kind}")


def approve(project_id: str, run_id: str, step: dict[str, Any]) -> None:
    response = client.post(
        f"/v1/projects/{project_id}/ai-runs/{run_id}/steps/{step['id']}/approve",
        json={"expected_revision": step["revision"]},
    )
    response.raise_for_status()
    log(f"Approved {step['kind']} {step['id']}")


def wait_for_auto_dispatched_builder(project_id: str, scene_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        candidates = [run for run in get_runs(project_id) if run.get("scene_id") == scene_id]
        if candidates:
            return candidates[0]
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError("Master approval did not dispatch a Builder run")


def main() -> None:
    prompt = "Vẽ một hình tròn xanh biến đổi mượt thành hình vuông đỏ trong một scene."
    response = client.post(
        "/v1/projects",
        json={"title": "HITL Runtime Smoke", "description": prompt, "source_language": "vi"},
    )
    response.raise_for_status()
    project_id = response.json()["id"]
    log(f"Created project {project_id}")

    response = client.post(
        f"/v1/projects/{project_id}/generate-scenes",
        json={"prompt": prompt, "hitl_enabled": True},
    )
    response.raise_for_status()
    master_run = response.json()["run"]
    storyboard = wait_for_step(project_id, master_run["id"], "storyboarder")
    approve(project_id, master_run["id"], storyboard)

    scenes = get_scenes(project_id)
    if not scenes or any(int(scene["scene_order"]) < 1 for scene in scenes):
        raise AssertionError("Storyboard approval did not persist valid 1-based scenes")
    target_scene = scenes[0]

    # Master approval already dispatches one Builder per scene. Starting a
    # second run here would be a contract bug and is intentionally forbidden.
    builder_run = wait_for_auto_dispatched_builder(project_id, target_scene["id"])
    builder = wait_for_step(project_id, builder_run["id"], "builder")
    output = builder.get("draft_output") or {}
    review = output.get("auto_review") or {}
    if not (
        review.get("passed") is True
        and (review.get("code") or {}).get("passed") is True
        and (review.get("visual") or {}).get("passed") is True
    ):
        raise AssertionError("Builder reached HITL without passing both internal reviewers")
    approve(project_id, builder_run["id"], builder)

    refreshed = next(scene for scene in get_scenes(project_id) if scene["id"] == target_scene["id"])
    if refreshed.get("generation_status") != "completed" or not refreshed.get("manim_code"):
        raise AssertionError("Builder approval did not persist the active Manim code")
    if any(step["kind"] not in {"storyboarder", "builder"} for step in get_steps(project_id, builder_run["id"])):
        raise AssertionError("Internal reviewers leaked into the public HITL step contract")

    log("PASS: Master approval auto-dispatched Builder; internal reviews passed; code persisted")


if __name__ == "__main__":
    main()
