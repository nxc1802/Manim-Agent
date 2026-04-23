import asyncio
import httpx
import json

API_BASE = "https://Cuong2004-Manim-Agent.hf.space"

async def debug():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Find the project
        projects = (await client.get(f"{API_BASE}/v1/projects")).json()
        target_p = next((p for p in projects if "98ac455c" in p["title"]), None)
        if not target_p:
            print("Project not found")
            return
        
        p_id = target_p["id"]
        print(f"Project ID: {p_id}")
        
        # 2. Get scenes
        scenes = (await client.get(f"{API_BASE}/v1/projects/{p_id}/scenes")).json()
        if not scenes:
            print("No scenes found")
            return
        
        s_id = scenes[0]["id"]
        print(f"Scene ID: {s_id}")
        print(f"Review Loop Status: {scenes[0]['review_loop_status']}")
        
        # 3. Get pipeline runs
        resp = await client.get(f"{API_BASE}/v1/projects/{p_id}/pipeline-runs")
        print(f"Status Code: {resp.status_code}")
        runs = resp.json()
        print("Raw Runs Response:")
        print(json.dumps(runs, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(debug())
