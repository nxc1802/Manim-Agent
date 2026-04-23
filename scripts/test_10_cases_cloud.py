import asyncio
import websockets
import json
import uuid
import httpx
import time
import sys
from datetime import datetime

# API_BASE = "http://localhost:8000"
API_BASE = "https://Cuong2004-Manim-Agent.hf.space"
WS_BASE = API_BASE.replace("https://", "wss://").replace("http://", "ws://")

TEST_CASES = [
    {
        "title": "Giải thích đạo hàm",
        "description": "Giải thích đạo hàm bằng đồ thị và tiếp tuyến cho học sinh.",
    },
    {
        "title": "Giải thích giới hạn",
        "description": "Video 30–45s giải thích giới hạn (phù hợp TikTok/Reels).",
    },
    {
        "title": "Tăng trưởng tuyến tính vs mũ",
        "description": "So sánh tăng trưởng tuyến tính vs tăng trưởng mũ trực quan.",
    },
    {
        "title": "Linear Regression",
        "description": "Giải thích linear regression không dùng công thức phức tạp.",
    },
    {
        "title": "Dữ liệu & Mô hình",
        "description": "Animation cho thuyết trình: 'vì sao dữ liệu nhiều giúp mô hình tốt hơn'.",
    },
    {
        "title": "Định thức ma trận 3x3",
        "description": "Minh họa từng bước tính định thức ma trận 3x3.",
    },
    {
        "title": "Dân số tăng theo thời gian",
        "description": "Kể chuyện bằng dữ liệu: dân số tăng theo thời gian.",
    },
    {
        "title": "Giải thích vector",
        "description": "Giải thích vector bằng ví dụ đời thực (chuyển động).",
    },
    {
        "title": "Dạy phân số cho trẻ em",
        "description": "Dạy phân số bằng animation đơn giản cho trẻ em.",
    },
    {
        "title": "Hàm số -> Đồ thị -> Ứng dụng",
        "description": "Chuỗi 3 scene: hàm số → đồ thị → ứng dụng thực tế.",
    },
]

def log(msg):
    print(f"[*] {msg}", flush=True)

async def check_async(resp, expected_code):
    if isinstance(expected_code, int):
        expected_code = [expected_code]
    if resp.status_code not in expected_code:
        log(f"[!] Error: {resp.status_code}")
        print(resp.text)
        return None
    return resp.json()

async def listen_ws(scene_id):
    uri = f"{WS_BASE}/v1/ws/{scene_id}"
    try:
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                event = json.loads(message)
                component = event.get("component", "unknown")
                phase = event.get("phase", "unknown")
                msg = event.get("message", "")
                print(f"  [WS][{scene_id[:8]}] >> [{component}][{phase}] {msg}", flush=True)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log(f"WebSocket Error ({scene_id[:8]}): {e}")

async def run_single_case(client, case, case_idx):
    test_id = str(uuid.uuid4())[:8]
    log(f"--- Case {case_idx+1}: {case['title']} (ID: {test_id}) ---")
    start_time = time.time()
    
    details = {
        "case": case["title"],
        "start_time": datetime.now().isoformat(),
        "phases": {}
    }

    # 1. Create Project
    p_data = {
        "title": f"{case['title']} - {test_id}",
        "description": case['description'],
        "source_language": "vi"
    }
    project = await check_async(await client.post(f"{API_BASE}/v1/projects", json=p_data), 201)
    if not project: return False, None
    project_id = project["id"]

    # 2. Create Scene
    s_data = {
        "scene_order": 0,
        "storyboard_text": f"Kế hoạch cho: {case['title']}"
    }
    scene = await check_async(await client.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json=s_data), 201)
    if not scene: return False, None
    scene_id = scene["id"]

    # Start WS listener
    ws_task = asyncio.create_task(listen_ws(scene_id))
    await asyncio.sleep(1)

    try:
        # 3. Generate Storyboard
        t0 = time.time()
        log(f"[{test_id}] Generating storyboard...")
        res = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200)
        if res is None: return False, details
        details["phases"]["storyboard"] = {
            "duration": time.time() - t0,
            "output": res.get("storyboard_text")
        }

        # 4. Approve Storyboard
        log(f"[{test_id}] Approving storyboard...")
        res = await check_async(await client.post(f"{API_BASE}/v1/projects/{project_id}/approve-storyboard"), 200)
        if res is None: return False, details

        # 5. Generate Plan
        t0 = time.time()
        log(f"[{test_id}] Generating plan...")
        res = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)
        if res is None: return False, details
        details["phases"]["plan"] = {
            "duration": time.time() - t0,
            "output": res.get("planner_output")
        }

        # 6. Approve Plan
        log(f"[{test_id}] Approving plan...")
        res = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-plan"), 200)
        if res is None: return False, details

        # 7. Approve Voice Script
        log(f"[{test_id}] Approving voice script...")
        res = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-voice-script"), 200)
        if res is None: return False, details

        # 8. Synthesize Voice
        t0 = time.time()
        log(f"[{test_id}] Synthesizing voice...")
        v_data = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/voice"), 202)
        if not v_data: return False, details
        voice_job_id = v_data["voice_job_id"]
        
        log(f"[{test_id}] Polling voice job...")
        while True:
            v_job = await check_async(await client.get(f"{API_BASE}/v1/voice-jobs/{voice_job_id}"), 200)
            if not v_job: return False, details
            if v_job["status"] == "completed":
                log(f"[{test_id}] Voice synthesis completed.")
                details["phases"]["voice"] = {
                    "duration": time.time() - t0,
                    "audio_url": v_job.get("asset_url")
                }
                break
            if v_job["status"] == "failed":
                log(f"[{test_id}] Voice synthesis failed.")
                return False, details
            await asyncio.sleep(5)

        # 9. Start Review Loop
        log(f"[{test_id}] Starting Builder Review Loop (Auto mode)...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/builder-review-loop", json={"mode": "auto"}), 200)

        log(f"[{test_id}] Polling scene for completion...")
        while True:
            scenes = await check_async(await client.get(f"{API_BASE}/v1/projects/{project_id}/scenes"), 200)
            if not scenes: return False, details
            scene = next((s for s in scenes if s["id"] == scene_id), None)
            status = scene["review_loop_status"]
            log(f"[{test_id}] Current status: {status}")
            
            if status == "completed":
                log(f"[{test_id}] SUCCESS: Pipeline completed!")
                # Get the report
                pipeline_runs = await check_async(await client.get(f"{API_BASE}/v1/projects/{project_id}/pipeline-runs"), 200)
                details["phases"]["builder_loop"] = {
                    "status": status,
                    "report": pipeline_runs[0]["report"] if pipeline_runs else "N/A"
                }
                # Get final asset
                details["final_asset"] = scene.get("preview_asset_url")
                return True, details
            if status in ("failed", "hitl_pending"):
                log(f"[{test_id}] Finished with status: {status}")
                return False, details
            await asyncio.sleep(10)
    finally:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

async def main():
    log(f"=== Starting 10-Case E2E Test on Cloud ===")
    results = []
    full_details = []
    async with httpx.AsyncClient(timeout=600.0) as client:
        for i, case in enumerate(TEST_CASES):
            success, details = await run_single_case(client, case, i)
            results.append({"title": case["title"], "success": success})
            full_details.append(details)
            log(f"Case {i+1} result: {'SUCCESS' if success else 'FAILED'}")
            
            if not success:
                log(f"!!! CRITICAL FAILURE on Case {i+1}. Stopping all tests to avoid token waste.")
                break
            
            print("-" * 40)
    
    log("=== Final Results ===")
    for i, res in enumerate(results):
        print(f"{i+1}. {res['title']}: {'✅' if res['success'] else '❌'}")
    
    # Save details to a file for the agent to report
    with open("scripts/cloud_test_report.json", "w", encoding="utf-8") as f:
        json.dump(full_details, f, indent=2, ensure_ascii=False)
    log("Report saved to scripts/cloud_test_report.json")

if __name__ == "__main__":
    asyncio.run(main())
