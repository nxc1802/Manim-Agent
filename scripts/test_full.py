#!/usr/bin/env python3
import sys
import json
import time
from pathlib import Path
import requests

API_BASE = "http://localhost:8000"
VOICE_TIMEOUT = 600
REVIEW_TIMEOUT = 1200

def log(msg):
    print(f"[*] {msg}")

def check(resp, expected=200):
    if isinstance(expected, int):
        expected = [expected]
    if resp.status_code not in expected:
        print(f"[!] FAILED: {resp.url} returned {resp.status_code}")
        print(resp.text)
        return None
    return resp.json()

def run_test_case(case, mode="auto"):
    test_id = case["id"]
    prompt = case["prompt"]
    log(f"--- Running Test Case: {test_id} ---")

    project = check(requests.post(f"{API_BASE}/v1/projects", json={
        "title": f"Full Test {test_id}",
        "description": prompt,
        "source_language": "vi"
    }), 201)
    if not project: return False
    project_id = project["id"]

    scene = check(requests.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json={
        "scene_order": 0,
        "storyboard_text": prompt
    }), 201)
    if not scene: return False
    scene_id = scene["id"]

    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200)
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-storyboard"), 200)
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-plan"), 200)
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-voice-script"), 200)

    voice_res = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/voice", json={"language": "vi"}), 202)
    if not voice_res: return False
    voice_job_id = voice_res["voice_job_id"]
    
    start_v = time.time()
    while True:
        if time.time() - start_v > VOICE_TIMEOUT:
            log("[!] Voice timeout")
            return False
        v_job = check(requests.get(f"{API_BASE}/v1/voice-jobs/{voice_job_id}"), 200)
        if v_job["status"] == "completed": break
        if v_job["status"] == "failed":
            log(f"[!] Voice failed: {v_job.get('error_code')}")
            return False
        time.sleep(2)

    log(f"Starting Review Loop...")
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/builder-review-loop", json={"mode": mode}), [200, 202])
    
    start_r = time.time()
    while True:
        if time.time() - start_r > REVIEW_TIMEOUT:
            log("[!] Review loop timeout")
            return False
        scene_status = check(requests.get(f"{API_BASE}/v1/projects/{project_id}/scenes"), 200)
        curr_scene = next(s for s in scene_status if s["id"] == scene_id)
        status = curr_scene["review_loop_status"]
        
        if status == "completed":
            log(f"SUCCESS: {test_id} finished.")
            return True
        if status in ["failed", "hitl_pending"]:
            log(f"FAILURE: {test_id} ended with {status}")
            return False
        time.sleep(10)

def main():
    cases_path = Path(__file__).parent / "data" / "local_e2e_cases.json"
    with open(cases_path) as f:
        cases = json.load(f)

    results = []
    for case in cases:
        success = run_test_case(case)
        results.append({"id": case["id"], "success": success})
        log(f"Result for {case['id']}: {'PASS' if success else 'FAIL'}")
        log("="*40)

    log("--- FINAL RESULTS ---")
    all_pass = True
    for r in results:
        print(f"{r['id']}: {'[PASS]' if r['success'] else '[FAIL]'}")
        if not r["success"]: all_pass = False
    
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()
