#!/usr/bin/env python3
import time
import requests
import sys
import uuid

# Configuration
API_BASE = "https://cuong2004-manim-agent.hf.space"
VOICE_TIMEOUT = 120
RENDER_TIMEOUT = 300

def log(msg):
    print(f"[*] {msg}")

def check(resp, expected=200):
    if resp.status_code != expected:
        print(f"[!] FAILED: {resp.url} returned {resp.status_code}")
        print(resp.text)
        sys.exit(1)
    return resp.json()

def main():
    # 1. Create Project
    log("Step 1: Creating Project...")
    project_payload = {
        "title": "Cloud E2E Test " + str(uuid.uuid4())[:8],
        "description": "Verification of the full pipeline on Hugging Face Spaces.",
        "source_language": "vi"
    }
    project = check(requests.post(f"{API_BASE}/v1/projects", json=project_payload), 201)
    project_id = project["id"]
    log(f"Project created: {project_id}")

    # 2. Create Scene
    log("Step 2: Creating Scene...")
    scene_payload = {
        "scene_order": 0,
        "storyboard_text": "Một vòng tròn biến thành một hình vuông màu đỏ."
    }
    scene = check(requests.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json=scene_payload), 201)
    scene_id = scene["id"]
    log(f"Scene created: {scene_id}")

    # 3. Director (Optional if we already provided storyboard_text but let's test it anyway)
    log("Step 3: Generating Storyboard (Director)...")
    scene = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200)
    log("Storyboard generated.")

    # 4. Approve Storyboard
    log("Step 4: Approving Storyboard...")
    scene = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-storyboard"), 200)
    log("Storyboard approved.")

    # 5. Planner
    log("Step 5: Planning (Planner)...")
    scene = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)
    log("Plan generated.")

    # 6. Builder (Generate Code)
    log("Step 6: Generating Manim Code (Builder)...")
    res = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-code", json={"enqueue_preview": False}), 200)
    scene = res["scene"]
    log("Code generated.")

    # 7. Voice (TTS)
    log("Step 7: Enqueueing Voice Synthesis...")
    voice_res = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/voice", json={"language": "vi"}), 202)
    voice_job_id = voice_res["voice_job_id"]
    log(f"Voice job enqueued: {voice_job_id}")

    # Poll Voice Job
    start_time = time.time()
    while True:
        if time.time() - start_time > VOICE_TIMEOUT:
            print("[!] Voice job timed out")
            sys.exit(1)
        job_status = check(requests.get(f"{API_BASE}/v1/voice-jobs/{voice_job_id}"), 200)
        status = job_status["status"]
        log(f"Voice Job Status: {status}")
        if status == "completed":
            break
        elif status == "failed":
            print(f"[!] Voice job failed: {job_status.get('error_code')}")
            sys.exit(1)
        time.sleep(5)

    # 8. Sync Timeline
    log("Step 8: Syncing Timeline...")
    sync_res = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/sync-timeline"), 200)
    log("Timeline synced.")

    # 9. Render
    log("Step 9: Enqueueing Render...")
    render_payload = {
        "render_type": "preview",
        "quality": "720p",
        "scene_id": scene_id
    }
    render_res = check(requests.post(f"{API_BASE}/v1/projects/{project_id}/render", json=render_payload), 202)
    render_job_id = render_res["job_id"]
    log(f"Render job enqueued: {render_job_id}")

    # Poll Render Job
    start_time = time.time()
    while True:
        if time.time() - start_time > RENDER_TIMEOUT:
            print("[!] Render job timed out")
            sys.exit(1)
        job_status = check(requests.get(f"{API_BASE}/v1/jobs/{render_job_id}"), 200)
        status = job_status["status"]
        log(f"Render Job Status: {status} ({job_status.get('progress')}%)")
        if status == "completed":
            log(f"SUCCESS! Artifact URL: {job_status.get('asset_url')}")
            break
        elif status == "failed":
            print(f"[!] Render job failed: {job_status.get('error_code')}")
            print(f"Logs: {job_status.get('logs')}")
            sys.exit(1)
        time.sleep(5)

if __name__ == "__main__":
    main()
