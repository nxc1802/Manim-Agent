import asyncio
import websockets
import json
import uuid
import requests
import time

async def test_ws_with_event():
    scene_id = str(uuid.uuid4())
    uri = f"ws://localhost:8000/v1/ws/{scene_id}"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            
            # We trigger an event via the API (assuming there's an endpoint that logs)
            # Or we can just use the shared library if we were in the same process,
            # but here we'll use a trick: start a separate task to hit an API endpoint.
            
            async def trigger_event():
                await asyncio.sleep(2)
                print("Triggering storyboard generation (which emits events)...")
                # We need a project and scene for this.
                # Simplified: let's just use a dummy POST to a valid endpoint.
                # Actually, the 'pipeline_event' is called in many places.
                # We'll create a scene and generate storyboard.
                try:
                    p = requests.post("http://localhost:8000/v1/projects", json={"title": "WS Test"}).json()
                    pid = p["id"]
                    s = requests.post(f"http://localhost:8000/v1/projects/{pid}/scenes", json={"scene_order": 0, "storyboard_text": "test"}).json()
                    sid = s["id"]
                    # We need to listen to THIS sid
                    return sid
                except Exception as e:
                    print(f"Trigger error: {e}")
                    return None

            # For real test, we should connect to the sid we just created.
            sid = await trigger_event()
            if not sid: return
            
            new_uri = f"ws://localhost:8000/v1/ws/{sid}"
            print(f"Reconnecting to {new_uri}...")
            
            async with websockets.connect(new_uri) as ws2:
                print("Connected to specific scene WS!")
                # Trigger the storyboard generation
                requests.post(f"http://localhost:8000/v1/scenes/{sid}/generate-storyboard")
                
                print("Waiting for events...")
                # Expecting something like "Director: storyboard draft"
                for _ in range(5):
                    message = await asyncio.wait_for(ws2.recv(), timeout=10.0)
                    payload = json.loads(message)
                    print(f"Received event: {payload.get('component')} | {payload.get('phase')} | {payload.get('message')}")
                    if "storyboard" in payload.get("message", "").lower():
                        print("SUCCESS: Received expected event!")
                        break
                        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws_with_event())
