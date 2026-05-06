import os
import sys
from redis import Redis

def reset_connections():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        print("Error: REDIS_URL environment variable not set.")
        sys.exit(1)

    try:
        r = Redis.from_url(redis_url, decode_responses=True)
        print(f"Connecting to Redis at {redis_url.split('@')[-1]}...")
        
        # Get current client list
        clients = r.client_list()
        my_addr = r.client_info()['addr']
        
        count = 0
        for client in clients:
            addr = client['addr']
            if addr != my_addr:
                try:
                    # Kill other clients
                    r.client_kill(addr)
                    count += 1
                except Exception as e:
                    print(f"Could not kill {addr}: {e}")
        
        print(f"Successfully killed {count} other connections.")
        
        # Optional: CLIENT KILL TYPE normal
        try:
            r.execute_command("CLIENT", "KILL", "TYPE", "normal", "SKIPME", "yes")
            print("Killed all other normal clients.")
        except Exception as e:
            print(f"Alternative kill command failed (might be restricted): {e}")

    except Exception as e:
        print(f"Failed to reset connections: {e}")
        sys.exit(1)

if __name__ == "__main__":
    reset_connections()
