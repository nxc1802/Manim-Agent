import asyncio
import websockets
import json
import uuid

async def test_ws():
    scene_id = str(uuid.uuid4())
    uri = f"ws://localhost:8000/v1/ws/{scene_id}"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            # Send a ping
            await websocket.send("ping")
            response = await websocket.recv()
            print(f"Received from server: {response}")
            
            print("Waiting for pipeline events (timeout 10s)...")
            try:
                # We expect no events yet unless we trigger them, but we verify we can listen.
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received event: {message}")
            except asyncio.TimeoutError:
                print("No events received (as expected).")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
