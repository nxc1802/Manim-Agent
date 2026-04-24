import os
from backend.core.config import Settings
from pydantic import ValidationError

def test_production_guardrail():
    print("Testing production guardrail...")
    # Set production env but auth off
    os.environ["APP_ENV"] = "production"
    os.environ["AUTH_MODE"] = "off"
    
    try:
        # We need to re-instantiate Settings to trigger validation
        # Settings() will read from os.environ
        s = Settings()
        print("FAIL: Settings initialized with AUTH_MODE=off in production!")
    except ValidationError as e:
        print(f"SUCCESS: Caught expected validation error: {e}")
    except Exception as e:
        print(f"Caught unexpected exception: {e}")

if __name__ == "__main__":
    test_production_guardrail()
