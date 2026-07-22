#!/usr/bin/env python3
"""
Fetch Hugging Face Space runtime or build logs using credentials from local env.
Usage:
    python scripts/fetch_hf_logs.py [--type run|build|runtime] [--lines N] [--save]
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(env_path: Path) -> dict[str, str]:
    """Parse key-value pairs from a .env file."""
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


def get_config(env_file_arg: str | None = None) -> tuple[str, str]:
    """Resolve HF_SPACE_ID and HF_TOKEN from environment or local env files."""
    env_data = {}
    if env_file_arg:
        env_data.update(load_env_file(Path(env_file_arg)))
    else:
        # Priority order: .env.github.local, then .env
        env_data.update(load_env_file(PROJECT_ROOT / ".env.github.local"))
        if not env_data.get("HF_TOKEN"):
            env_data.update(load_env_file(PROJECT_ROOT / ".env"))

    space_id = os.environ.get("HF_SPACE_ID") or env_data.get("HF_SPACE_ID") or "Cuong2004/Manim-Agent"
    hf_token = os.environ.get("HF_TOKEN") or env_data.get("HF_TOKEN")

    if not hf_token:
        sys.stderr.write("Error: HF_TOKEN not found in environment or .env files.\n")
        sys.exit(1)

    return space_id, hf_token


def fetch_logs(space_id: str, token: str, log_type: str, read_timeout: float = 2.5) -> str:
    """Fetch log stream from Hugging Face Spaces API with a safety timeout for SSE streams."""
    url = f"https://huggingface.co/api/spaces/{space_id}/logs/{log_type}"
    if log_type == "runtime":
        url = f"https://huggingface.co/api/spaces/{space_id}/runtime"

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "Manim-Agent-LogFetcher/1.0"},
    )

    if log_type == "runtime":
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as err:
            sys.stderr.write(f"Error fetching runtime status: {err}\n")
            sys.exit(1)

    lines = []
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            try:
                # Set short socket timeout on SSE stream so reading ends when current logs finish
                if hasattr(resp, "fp") and hasattr(resp.fp, "raw") and hasattr(resp.fp.raw, "_sock"):
                    resp.fp.raw._sock.settimeout(read_timeout)
            except Exception:
                pass

            while time.time() - start_time < 10.0:
                try:
                    line = resp.readline()
                    if not line:
                        break
                    lines.append(line.decode("utf-8", errors="replace"))
                except Exception:
                    # Stream read timed out (no new log events)
                    break
    except Exception as err:
        if not lines:
            sys.stderr.write(f"Error connecting to HF API ({url}): {err}\n")
            sys.exit(1)

    return "".join(lines)


def parse_sse_logs(raw_text: str) -> list[str]:
    """Parse Server-Sent Events (SSE) format into clean log lines."""
    clean_lines = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            if line and not line.startswith("event:"):
                clean_lines.append(line)
            continue

        payload_str = line[5:].strip()
        if not payload_str:
            continue

        try:
            payload = json.loads(payload_str)
            if isinstance(payload, dict):
                log_data = payload.get("data") or payload.get("message") or ""
                timestamp = payload.get("timestamp")
                if log_data:
                    log_entry = log_data.rstrip("\r\n")
                    if timestamp and not log_entry.startswith(timestamp[:10]):
                        clean_lines.append(f"[{timestamp}] {log_entry}")
                    else:
                        clean_lines.append(log_entry)
        except json.JSONDecodeError:
            clean_lines.append(payload_str)

    return clean_lines


def main():
    parser = argparse.ArgumentParser(description="Fetch Hugging Face Space logs directly.")
    parser.add_argument(
        "--type", "-t",
        choices=["run", "build", "runtime"],
        default="run",
        help="Type of log to fetch: 'run' (container runtime, default), 'build' (Docker build), or 'runtime' (status)",
    )
    parser.add_argument(
        "--lines", "-n",
        type=int,
        default=100,
        help="Number of latest log lines to display (default: 100, 0 for all)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env file containing HF_TOKEN and HF_SPACE_ID",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save output log file to project directory",
    )

    args = parser.parse_args()

    space_id, token = get_config(args.env_file)
    print(f"Fetching '{args.type}' logs for HF Space: {space_id}...")

    raw_output = fetch_logs(space_id, token, args.type)

    if args.type == "runtime":
        try:
            formatted_json = json.dumps(json.loads(raw_output), indent=2)
            print(formatted_json)
        except Exception:
            print(raw_output)
        return

    clean_lines = parse_sse_logs(raw_output)

    if not clean_lines:
        print("No log lines retrieved.")
        return

    if args.lines > 0 and len(clean_lines) > args.lines:
        display_lines = clean_lines[-args.lines:]
        print(f"--- Showing last {args.lines} of {len(clean_lines)} log lines ---")
    else:
        display_lines = clean_lines
        print(f"--- Total {len(clean_lines)} log lines ---")

    print("\n".join(display_lines))

    if args.save:
        out_file = PROJECT_ROOT / "hf_logs.log"
        out_file.write_text("\n".join(clean_lines), encoding="utf-8")
        print(f"\nSaved clean log output to: {out_file.absolute()}")


if __name__ == "__main__":
    main()
