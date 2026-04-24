#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import requests

# Configuration
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
    log(f"--- Running Test Case: {test_id} (mode={mode}) ---")

    # 1. Create Project
    project = check(requests.post(f"{API_BASE}/v1/projects", json={
        "title": f"E2E {test_id}",
        "description": prompt,
        "source_language": "vi"
    }), 201)
    if not project: return False
    project_id = project["id"]

    # 2. Create Scene
    scene = check(requests.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json={
        "scene_order": 0,
        "storyboard_text": prompt
    }), 201)
    if not scene: return False
    scene_id = scene["id"]

    # 3. Director
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200)
    
    # 4. Approve Storyboard
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-storyboard"), 200)
    
    # 5. Plan
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)

    # 5.1 Approve Plan (NEW)
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-plan"), 200)

    # 5.2 Approve Voice Script (NEW)
    check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-voice-script"), 200)

    # 6. Voice (TTS)
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

    # 7. Review Loop (Build + Render + Review)
    log(f"Starting Review Loop in {mode} mode...")
    loop_res = check(requests.post(f"{API_BASE}/v1/scenes/{scene_id}/builder-review-loop", json={"mode": mode}), [200, 202])
    
    start_r = time.time()
    while True:
        if time.time() - start_r > REVIEW_TIMEOUT:
            log("[!] Review loop timeout")
            return False
        
        # Check scene status for review loop
        scene_status = check(requests.get(f"{API_BASE}/v1/projects/{project_id}/scenes"), 200)
        curr_scene = next(s for s in scene_status if s["id"] == scene_id)
        status = curr_scene["review_loop_status"]
        log(f"Review Status: {status}")
        
        if status == "completed":
            log(f"SUCCESS: {test_id} finished.")
            return True
        if status in ["failed", "hitl_pending"]:
            log(f"FAILURE/HITL: {test_id} ended with {status}")
            return False
        time.sleep(10)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "hitl"], default="auto")
    parser.add_argument("--case", help="Specific case ID to run")
    args = parser.parse_args()

    cases_path = Path(__file__).parent / "local_e2e_cases.json"
    with open(cases_path) as f:
        cases = json.load(f)

    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            log(f"[!] Case not found: {args.case}")
            sys.exit(1)

    results = []
    for case in cases:
        success = run_test_case(case, mode=args.mode)
        results.append({"id": case["id"], "success": success})
        log(f"Result for {case['id']}: {'PASS' if success else 'FAIL'}")
        log("="*40)

    log("--- FINAL RESULTS ---")
    for r in results:
        print(f"{r['id']}: {'[PASS]' if r['success'] else '[FAIL]'}")

if __name__ == "__main__":
    main()
