#!/usr/bin/env python3
"""Integration test: end-to-end AI pipeline with hitl_enabled=False (auto-pass all).

Usage:
    PYTHONPATH=.:.. python tests/test_integration_e2e.py

Requires: Backend running at localhost:8000, AI Core + Worker running.
"""
from __future__ import annotations

import json
import os
import sys
import time
from uuid import UUID

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
TIMEOUT = 600  # 10 minutes max for full pipeline
POLL_INTERVAL = 5  # seconds between polls

client = httpx.Client(base_url=BACKEND_URL, timeout=60.0)


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def create_project(title: str, description: str) -> dict:
    r = client.post("/v1/projects", json={"title": title, "description": description})
    r.raise_for_status()
    project = r.json()
    log(f"✅ Project created: {project['id']}")
    return project


def create_scene(project_id: str) -> dict:
    r = client.post(f"/v1/projects/{project_id}/scenes", json={"scene_order": 0})
    r.raise_for_status()
    scene = r.json()
    log(f"✅ Scene created: {scene['id']}")
    return scene


def start_ai_run(project_id: str, scene_id: str, hitl_enabled: bool = False) -> dict:
    r = client.post(
        f"/v1/projects/{project_id}/ai-runs",
        json={"scene_id": scene_id, "hitl_enabled": hitl_enabled},
    )
    r.raise_for_status()
    data = r.json()
    log(f"✅ AI Run started: {data['run']['id']} (hitl_enabled={hitl_enabled})")
    log(f"   First step: {data['first_step']['kind']} ({data['first_step']['id']})")
    return data


def poll_run_completion(project_id: str, run_id: str) -> list[dict]:
    """Poll until run is completed or failed."""
    start_time = time.time()
    last_status = ""
    last_step_count = 0

    while time.time() - start_time < TIMEOUT:
        # Get run status
        r = client.get(f"/v1/projects/{project_id}/ai-runs")
        r.raise_for_status()
        runs = r.json()
        run = next((run for run in runs if run["id"] == run_id), None)
        if run is None:
            log("❌ Run not found!")
            sys.exit(1)

        # Get steps
        r2 = client.get(f"/v1/projects/{project_id}/ai-runs/{run_id}/steps")
        r2.raise_for_status()
        steps = r2.json()

        current_status = run["status"]
        if current_status != last_status or len(steps) != last_step_count:
            last_status = current_status
            last_step_count = len(steps)
            log(f"📊 Run status: {current_status} | Steps: {len(steps)}")
            for step in steps:
                status_icon = {
                    "queued": "⏳", "generating": "🔄", "pending_review": "👀",
                    "approved": "✅", "rejected": "❌", "failed": "💥",
                }.get(step["status"], "❓")
                extra = ""
                if step.get("draft_output"):
                    output = step["draft_output"]
                    if "manim_code" in output:
                        extra = f" (code: {len(output['manim_code'])} chars)"
                    elif "passed" in output:
                        extra = f" (passed={output['passed']}, attempts={output.get('total_attempts', '?')})"
                    elif "storyboard" in output:
                        extra = f" (storyboard: {len(output['storyboard'])} chars)"
                    elif "text" in output:
                        extra = f" (text: {len(output['text'])} chars)"
                log(f"   {status_icon} [{step['sequence']}] {step['kind']}: {step['status']}{extra}")

        if current_status == "completed":
            log("🎉 Pipeline completed successfully!")
            return steps
        if current_status == "failed":
            log("💥 Pipeline FAILED!")
            # Print error details
            for step in steps:
                if step.get("error"):
                    log(f"   Error in {step['kind']}: {step['error'][:500]}")
            return steps

        time.sleep(POLL_INTERVAL)

    log(f"⏰ Timeout after {TIMEOUT}s!")
    return []


def print_results(project: dict, scene_id: str, steps: list[dict]) -> None:
    log("\n" + "=" * 70)
    log("PIPELINE RESULTS")
    log("=" * 70)

    # Get scene to see final manim_code
    r = client.get(f"/v1/scenes/{scene_id}")
    scene = r.json() if r.status_code == 200 else {}

    log(f"\n📋 Project: {project['title']}")
    log(f"   Description: {project.get('description', 'N/A')}")
    log(f"   Total steps: {len(steps)}")
    log(f"   Step kinds: {[s['kind'] for s in steps]}")

    for step in steps:
        log(f"\n--- Step [{step['sequence']}] {step['kind']} ({step['status']}) ---")
        output = step.get("final_output") or step.get("draft_output") or {}

        if step["kind"] == "director":
            storyboard = output.get("storyboard", output.get("text", "N/A"))
            log(f"   Storyboard ({len(storyboard)} chars):")
            for line in storyboard[:500].splitlines()[:10]:
                log(f"   | {line}")
            if len(storyboard) > 500:
                log(f"   | ... ({len(storyboard) - 500} more chars)")

        elif step["kind"] in ("planner", "scene_designer"):
            text = output.get("text", str(output)[:500])
            log(f"   Plan/Design ({len(text)} chars):")
            for line in text[:400].splitlines()[:8]:
                log(f"   | {line}")

        elif step["kind"] == "builder":
            code = output.get("manim_code", "N/A")
            log(f"   Manim code ({len(code)} chars):")
            for line in code[:600].splitlines()[:15]:
                log(f"   | {line}")

        elif step["kind"] in ("code_reviewer", "visual_reviewer"):
            passed = output.get("passed", "N/A")
            attempts = output.get("total_attempts", "N/A")
            iterations = output.get("iterations", [])
            final_err = output.get("final_error")
            log(f"   Passed: {passed}")
            log(f"   Total attempts: {attempts}")
            log(f"   Iterations: {len(iterations)}")
            for it in iterations:
                log(f"     [{it.get('iteration')}] model={it.get('model')} escalated={it.get('escalated')} same_error={it.get('same_error')}")
                if it.get("error_summary"):
                    log(f"         error: {it['error_summary'][:200]}")
                if it.get("fix_applied"):
                    log(f"         fix: {it['fix_applied'][:200]}")
            if final_err:
                log(f"   Final error: {final_err[:300]}")

    log(f"\n📝 Final scene manim_code ({len(scene.get('manim_code', '') or '')} chars)")
    if scene.get("manim_code"):
        log("   --- Code ---")
        for line in scene["manim_code"].splitlines():
            log(f"   | {line}")
        log("   --- End ---")

    log("\n" + "=" * 70)


def main() -> None:
    prompt = "Detailed explanation of derivatives, antiderivatives, integrals."
    log(f"🚀 Starting integration test with prompt: '{prompt}'")
    log(f"   Backend: {BACKEND_URL}")

    # 1. Create project
    project = create_project(
        title="Calculus Fundamentals",
        description=prompt,
    )

    # 2. Create scene
    scene = create_scene(project["id"])

    # 3. Start AI run with hitl_enabled=False (auto-pass everything)
    run_data = start_ai_run(project["id"], scene["id"], hitl_enabled=False)
    run_id = run_data["run"]["id"]

    # 4. Poll until completion
    log("\n⏳ Waiting for pipeline to complete...")
    steps = poll_run_completion(project["id"], run_id)

    # 5. Print results
    if steps:
        print_results(project, scene["id"], steps)
    else:
        log("❌ No steps returned!")
        sys.exit(1)


if __name__ == "__main__":
    main()
