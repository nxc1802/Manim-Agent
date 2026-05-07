import asyncio
import uuid

import httpx

API_BASE = "http://localhost:8000"

CASE = {
    "title": "Giải thích đạo hàm (Local Test)",
    "description": "Giải thích đạo hàm bằng đồ thị và tiếp tuyến cho học sinh.",
}


async def check_async(resp, expected_code):
    if isinstance(expected_code, int):
        expected_code = [expected_code]
    if resp.status_code not in expected_code:
        print(f"[!] Error: {resp.status_code}")
        print(resp.text)
        return None
    return resp.json()


async def run_local_test():
    async with httpx.AsyncClient(timeout=600.0) as client:
        test_id = str(uuid.uuid4())[:8]
        print(f"=== Starting Local Test: {CASE['title']} (ID: {test_id}) ===")

        # 1. Create Project
        p_data = {
            "title": f"{CASE['title']} - {test_id}",
            "description": CASE["description"],
            "source_language": "vi",
        }
        project = await check_async(await client.post(f"{API_BASE}/v1/projects", json=p_data), 201)
        if not project:
            return
        project_id = project["id"]

        # 2. Create Scene
        s_data = {"scene_order": 0, "storyboard_text": f"Kế hoạch cho: {CASE['title']}"}
        scene = await check_async(
            await client.post(f"{API_BASE}/v1/projects/{project_id}/scenes", json=s_data), 201
        )
        if not scene:
            return
        scene_id = scene["id"]

        # 3. Generate Storyboard
        print(f"[{test_id}] Generating storyboard...")
        await check_async(
            await client.post(f"{API_BASE}/v1/scenes/{scene_id}/generate-storyboard"), 200
        )

        # 4. Approve Storyboard
        print(f"[{test_id}] Approving storyboard...")
        await check_async(
            await client.post(f"{API_BASE}/v1/projects/{project_id}/approve-storyboard"), 200
        )

        # 5. Generate Plan
        print(f"[{test_id}] Generating plan...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/plan"), 200)

        # 6. Approve Plan
        print(f"[{test_id}] Approving plan...")
        await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-plan"), 200)

        # 7. Approve Voice Script
        print(f"[{test_id}] Approving voice script...")
        await check_async(
            await client.post(f"{API_BASE}/v1/scenes/{scene_id}/approve-voice-script"), 200
        )

        # 8. Synthesize Voice
        print(f"[{test_id}] Synthesizing voice...")
        v_data = await check_async(await client.post(f"{API_BASE}/v1/scenes/{scene_id}/voice"), 202)
        if not v_data:
            return
        voice_job_id = v_data["voice_job_id"]

        print(f"[{test_id}] Polling voice job...")
        while True:
            v_job = await check_async(
                await client.get(f"{API_BASE}/v1/voice-jobs/{voice_job_id}"), 200
            )
            if not v_job:
                return
            if v_job["status"] == "completed":
                print(f"[{test_id}] Voice synthesis completed.")
                break
            if v_job["status"] == "failed":
                print(f"[{test_id}] Voice synthesis failed.")
                return
            await asyncio.sleep(5)

        # 9. Start Review Loop
        print(f"[{test_id}] Starting Builder Review Loop (Auto mode)...")
        await check_async(
            await client.post(
                f"{API_BASE}/v1/scenes/{scene_id}/builder-review-loop", json={"mode": "auto"}
            ),
            200,
        )

        print(f"[{test_id}] Polling scene for completion...")
        while True:
            scenes = await check_async(
                await client.get(f"{API_BASE}/v1/projects/{project_id}/scenes"), 200
            )
            if not scenes:
                return
            scene = next((s for s in scenes if s["id"] == scene_id), None)
            status = scene["review_loop_status"]
            print(f"[{test_id}] Current status: {status}")

            if status == "completed":
                print(f"[{test_id}] SUCCESS: Pipeline completed!")
                break
            if status == "failed":
                print(f"[{test_id}] FAILED: Review loop failed.")
                break
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(run_local_test())
