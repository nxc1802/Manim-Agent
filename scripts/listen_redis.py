import redis
import os
import json

def listen():
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    print(f"Connecting to Redis: {url}")
    r = redis.from_url(url, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe("manim_agent:events")
    print("Subscribed to manim_agent:events. Waiting...")
    for message in pubsub.listen():
        if message["type"] == "message":
            print(f"Received: {message['data']}")

if __name__ == "__main__":
    listen()
