#!/usr/bin/env python3
"""
Endpoint verification script for Manim Agent API.
Usage:
    python scripts/test_endpoints.py [--url https://cuong2004-manim-agent.hf.space]
"""

import argparse
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(env_path: Path) -> dict[str, str]:
    env_vars = {}
    if not env_path.is_file():
        return env_vars
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_vars[key.strip()] = value.strip().strip("'\"")
    return env_vars


def request_endpoint(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 10.0,
) -> tuple[int, str]:
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("User-Agent", "Manim-Agent-EndpointTester/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace") if err.fp else ""
        return err.code, body
    except Exception as err:
        return 0, str(err)


def test_all_endpoints(base_url: str) -> bool:
    base_url = base_url.rstrip("/")
    print(f"\n==========================================")
    print(f"Testing Endpoints on: {base_url}")
    print(f"==========================================\n")

    env_vars = load_env_file(PROJECT_ROOT / ".env.github.local")
    env_vars.update(load_env_file(PROJECT_ROOT / ".env"))

    dummy_id = "00000000-0000-0000-0000-000000000000"

    # Test cases: (name, path, method, headers, expected_status_codes)
    test_cases = [
        # Health / System
        ("Health Check", "/health", "GET", {}, [200]),
        ("Readiness Check", "/ready", "GET", {}, [200, 503]),
        
        # User API
        ("User Settings Get (Unauth)", "/v1/users/me/settings", "GET", {}, [401]),
        
        # Projects API
        ("Projects List (Unauth)", "/v1/projects", "GET", {}, [401]),
        ("Project Get (Unauth)", f"/v1/projects/{dummy_id}", "GET", {}, [401]),
        ("Project Scenes List (Unauth)", f"/v1/projects/{dummy_id}/scenes", "GET", {}, [401]),
        
        # Render API
        ("Render Project (Unauth)", f"/v1/projects/{dummy_id}/render", "POST", {}, [401]),
        
        # HITL Generation API
        ("Generate Scenes (Unauth)", f"/v1/projects/{dummy_id}/generate-scenes", "POST", {}, [401]),
        ("Start AI Run (Unauth)", f"/v1/projects/{dummy_id}/ai-runs", "POST", {}, [401]),
        ("List AI Runs (Unauth)", f"/v1/projects/{dummy_id}/ai-runs", "GET", {}, [401]),
        ("List AI Steps (Unauth)", f"/v1/projects/{dummy_id}/ai-runs/{dummy_id}/steps", "GET", {}, [401]),
        
        # Jobs API
        ("Jobs Get (Unauth)", f"/v1/jobs/{dummy_id}", "GET", {}, [401]),
        
        # Internal Service APIs (Internal Service Token Required)
        ("Internal Step Claim (Unauth)", f"/internal/hitl-steps/{dummy_id}/claim", "POST", {}, [401]),
        ("Internal Step Stream (Unauth)", f"/internal/hitl-steps/{dummy_id}/stream", "POST", {}, [401]),
        ("Internal Step Complete (Unauth)", f"/internal/hitl-steps/{dummy_id}/complete", "POST", {}, [401]),
        ("Internal Step Fail (Unauth)", f"/internal/hitl-steps/{dummy_id}/fail", "POST", {}, [401]),
        ("Internal Render Claim (Unauth)", f"/internal/render-jobs/{dummy_id}/claim", "POST", {}, [401]),
        ("Internal Render Complete (Unauth)", f"/internal/render-jobs/{dummy_id}/complete", "POST", {}, [401]),
        ("Internal Render Fail (Unauth)", f"/internal/render-jobs/{dummy_id}/fail", "POST", {}, [401]),
    ]

    all_passed = True
    for name, path, method, headers, expected_codes in test_cases:
        url = f"{base_url}{path}"
        code, body = request_endpoint(url, method=method, headers=headers)
        passed = code in expected_codes
        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"[{status_str}] {name:38s} {method:4s} {path:58s} -> HTTP {code} (Expected: {expected_codes})")
        if not passed:
            print(f"       Response snippet: {body[:200]}")

    print("\n------------------------------------------")
    if all_passed:
        print("ALL ENDPOINT VERIFICATIONS PASSED SUCCESSFULLY!")
    else:
        print("SOME ENDPOINT VERIFICATIONS FAILED!")
    print("------------------------------------------\n")
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Test Manim Agent server endpoints.")
    parser.add_argument(
        "--url",
        type=str,
        default="https://cuong2004-manim-agent.hf.space",
        help="Base URL of the target server",
    )
    args = parser.parse_args()

    success = test_all_endpoints(args.url)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
