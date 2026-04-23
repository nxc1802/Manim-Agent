import asyncio
import websockets
import json
import uuid
import httpx
import time
import sys

# API_BASE = "http://localhost:8000"
API_BASE = "https://Cuong2004-Manim-Agent.hf.space"
WS_BASE = API_BASE.replace("https://", "wss://").replace("http://", "ws://")

def log(msg):
    print(f"[*] {msg}", flush=True)

async def check_async(resp, expected_code):
    if isinstance(expected_code, int):
        expected_code = [expected_code]
    if resp.status_code not in expected_code:
        log(f"[!] Error: {resp.status_code}")
        print(resp.text)
        sys.exit(1)
    return resp.json()

async def listen_ws(scene_id):
    uri = f"{WS_BASE}/v1/ws/{scene_id}"
    log(f"Connecting to WebSocket: {uri}")
    try:
        # Note: HF Spaces might need subprotocols or headers, but usually it works directly.
        async with websockets.connect(uri) as websocket:
            log("WebSocket Connected!")
            while True:
                message = await websocket.recv()
                event = json.loads(message)
                component = event.get("component", "unknown")
                phase = event.get("phase", "unknown")
                msg = event.get("message", "")
                print(f"  [WS] >> [{component}][{phase}] {msg}", flush=True)
    except Exception as e:
        log(f"WebSocket Error: {e}")

async def run_complex_test():
    test_id = str(uuid.uuid4())[:8]
    log(f"--- Starting Complex E2E Test (ID: {test_id}) ---")

    async with httpx.AsyncClient(timeout=300.0) as client:
        # 1. Create Project
        log("Creating project...")
        p_data = {
            "title": f"Simple Circle - {test_id}",
            "description": "Draw a blue circle on a white background. Then, transform it into a red square.",
            "source_language": "en"
        }
        project = await check_async(await client.post(f"{API_BASE}/v1/projects", json=p_data), 201)
        project_id = project["id"]
        log(f"Project created: {project_id}")

        # 2. Create Scene
        log("Creating scene...")
        s_data = {
            "scene_order": 0,
            "storyboard_text": "Scene 1: Introduction to derivatives."
        }
        scene = await check_async(await client.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json=s_data), 201)
        scene_id = scene["id"]
        log(f"Scene created: {scene_id}")

        # Start WS listener
        ws_task = asyncio.create_task(listen_ws(scene_id))
        await asyncio.sleep(1) # Give it a moment to connect

        # 3. Generate Storyboard
        log("Generating storyboard...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200)

        # 4. Approve Storyboard
        log("Approving storyboard...")
        await check_async(await client.post(f"{API_BASE}/v1/projects/{project_id}/approve-storyboard"), 200)

        # 5. Generate Plan
        log("Generating plan...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)

        # 6. Approve Plan
        log("Approving plan...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-plan"), 200)

        # 7. Approve Voice Script
        log("Approving voice script...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-voice-script"), 200)

        # 8. Synthesize Voice
        log("Synthesizing voice...")
        v_data = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/voice"), 202)
        voice_job_id = v_data["voice_job_id"]
        
        log("Polling voice job...")
        while True:
            v_job = await check_async(await client.get(f"{API_BASE}/v1/voice-jobs/{voice_job_id}"), 200)
            if v_job["status"] == "completed":
                log("Voice synthesis completed.")
                break
            if v_job["status"] == "failed":
                log("[!] Voice synthesis failed.")
                return
            await asyncio.sleep(5)

        # 9. Start Review Loop
        log("Starting Builder Review Loop (Auto mode)...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/builder-review-loop", params={"mode": "auto"}), 200)

        log("Polling scene for completion...")
        while True:
            scenes = await check_async(await client.get(f"{API_BASE}/v1/projects/{project_id}/scenes"), 200)
            scene = next((s for s in scenes if s["id"] == scene_id), None)
            status = scene["review_loop_status"]
            log(f"Current status: {status}")
            
            if status == "completed":
                log("SUCCESS: Pipeline completed!")
                print(json.dumps(scene, indent=2))
                break
            if status == "failed":
                log("[!] Pipeline failed.")
                break
            await asyncio.sleep(15)
        
        ws_task.cancel()

if __name__ == "__main__":
    asyncio.run(run_complex_test())
