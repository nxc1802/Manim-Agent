import requests
import time
import json
import os
import sys

# Configuration
API_BASE = "https://Cuong2004-Manim-Agent.hf.space"
PROJECT_TITLE = "Cloud E2E Test"
PROMPT = "Explain the relationship between Pi and a circle using a simple animation."

def log(msg):
    print(f"[*] {msg}", flush=True)

def check(resp, expected_code=200):
    if resp.status_code != expected_code:
        print(f"[!] Error: {resp.status_code}")
        print(resp.text)
        sys.exit(1)
    return resp.json()

def run_test():
    log(f"--- Starting Cloud E2E Test on {API_BASE} ---")
    
    # 1. Create Project
    log("Creating project...")
    p_data = check(requests.post(f"{API_BASE}/v1/projects", json={
        "title": PROJECT_TITLE,
        "description": PROMPT
    }), 201)
    project_id = p_data["id"]
    log(f"Project created: {project_id}")

    # 2. Create Scene
    log("Creating scene...")
    s_data = check(requests.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json={
        "scene_order": 0,
        "storyboard_text": PROMPT
    }), 201)
    scene_id = s_data["id"]
    log(f"Scene created: {scene_id}")

    # 3. Generate Storyboard
    log("Generating storyboard...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200)
    
    # 4. Approve Storyboard
    log("Approving storyboard...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-storyboard"), 200)

    # 5. Plan
    log("Generating plan...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)

    # 6. Approve Plan
    log("Approving plan...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-plan"), 200)

    # 7. Approve Voice Script
    log("Approving voice script...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-voice-script"), 200)

    # 8. Synthesize Voice
    log("Synthesizing voice...")
    v_data = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/voice"), 202)
    voice_job_id = v_data["voice_job_id"]
    
    log("Polling voice job...")
    while True:
        v_job = check(requests.get(f"{API_BASE}/v1/voice-jobs/{voice_job_id}"), 200)
        if v_job["status"] == "completed":
            log("Voice synthesis completed.")
            break
        if v_job["status"] == "failed":
            log("[!] Voice synthesis failed.")
            return
        time.sleep(5)

    # 9. Start Review Loop (Auto mode)
    log("Starting Builder Review Loop (Auto mode)...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/builder-review-loop", params={"mode": "auto"}), 200)

    log("Polling scene for completion...")
    while True:
        scenes = check(requests.get(f"{API_BASE}/v1/projects/{project_id}/scenes"), 200)
        scene = next((s for s in scenes if s["id"] == scene_id), None)
        if not scene:
            log("[!] Scene not found in project scenes list.")
            break
            
        status = scene["review_loop_status"]
        log(f"Current status: {status}")
        
        if status == "completed":
            log("SUCCESS: Pipeline completed!")
            # Note: Final video URL is usually on the render job or a separate asset mapping.
            # For now, let's look for any 'audio_url' or similar as a proxy if 'video_url' is missing in schema.
            # In our schema, we don't have a direct 'video_url' in Scene, it's usually in the render job.
            log("Checking for final video...")
            # We'll just print the scene for inspection
            print(json.dumps(scene, indent=2))
            break
        
        if status == "failed":
            log("[!] Pipeline failed.")
            break
            
        time.sleep(15)

if __name__ == "__main__":
    run_test()
