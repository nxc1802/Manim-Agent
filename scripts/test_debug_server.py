#!/usr/bin/env python3
import sys
import json
import time
import requests
from datetime import datetime
from uuid import UUID

# Try to import rich for pretty printing, fallback to standard print
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    class MockConsole:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, title=""): print(f"\n{'='*20} {title} {'='*20}\n")
    console = MockConsole()

# Configuration
SERVER_URL = "https://cuong2004-manim-agent.hf.space"
# SERVER_URL = "http://localhost:8000" # Uncomment for local test

COMPLEX_PROMPT = """
Animate the 'Sieve of Eratosthenes' algorithm for finding prime numbers up to 30.
1. Show a grid of numbers from 1 to 30.
2. Highlight the number currently being processed.
3. Cross out or dim the multiples of that number (e.g., 2, 4, 6... then 3, 6, 9...).
4. Finally, highlight all remaining numbers as primes.
5. Use clear labels and smooth transitions between steps.
"""

def log(msg, style="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if HAS_RICH:
        color = "cyan" if style == "info" else "green" if style == "success" else "red"
        console.print(f"[[{timestamp}]] [{color}]{msg}[/{color}]")
    else:
        print(f"[{timestamp}] {msg}")

def check_resp(resp, expected=[200, 201, 202]):
    if isinstance(expected, int):
        expected = [expected]
    if resp.status_code not in expected:
        if HAS_RICH:
            console.print(Panel(f"Error {resp.status_code}: {resp.text}", title="API Error", border_style="red"))
        else:
            print(f"Error {resp.status_code}: {resp.text}")
        return None
    try:
        return resp.json()
    except:
        return {}

def run_debug_test():
    console.rule("[bold magenta]Manim Agent Server Debug Test[/bold magenta]")
    log(f"Target Server: {SERVER_URL}")
    log(f"Prompt: {COMPLEX_PROMPT.strip()[:100]}...")

    # 1. Create Project
    log("Step 1: Creating Project...")
    project = check_resp(requests.post(f"{SERVER_URL}/v1/projects", json={
        "title": "Debug E2E Complex Case",
        "description": COMPLEX_PROMPT,
        "source_language": "en"
    }))
    if not project: return
    project_id = project["id"]
    log(f"Project Created: {project_id}", "success")

    # 2. Create Scene
    log("Step 2: Creating Scene...")
    scene = check_resp(requests.post(f"{SERVER_URL}/v1/projects/{project_id}/scenes", json={
        "scene_order": 0,
        "storyboard_text": COMPLEX_PROMPT
    }))
    if not scene: return
    scene_id = scene["id"]
    log(f"Scene Created: {scene_id}", "success")

    # 3. Director Phase
    log("Step 3: Running Director Agent (Storyboard Generation)...")
    storyboard = check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/generate-storyboard"))
    if not storyboard: return
    log("Storyboard generated successfully.", "success")

    # 4. Approve Storyboard
    log("Step 4: Approving Storyboard...")
    check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/approve-storyboard"))

    # 5. Planner Phase
    log("Step 5: Running Planner Agent...")
    plan_resp = check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/plan"))
    if not plan_resp: return
    log("Plan generated successfully.", "success")
    
    # 6. Approve Plan & Script
    log("Step 6: Approving Plan & Voice Script...")
    check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/approve-plan"))
    check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/approve-voice-script"))

    # 7. Voice (TTS) Phase
    log("Step 7: Enqueueing Voice Generation...")
    v_res = check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/voice", json={"language": "en"}))
    if not v_res: return
    v_job_id = v_res["voice_job_id"]
    
    log(f"Voice Job ID: {v_job_id}. Polling for completion...")
    while True:
        v_job = check_resp(requests.get(f"{SERVER_URL}/v1/voice-jobs/{v_job_id}"))
        if not v_job: break
        if v_job["status"] == "completed":
            log("Voice generation completed.", "success")
            break
        elif v_job["status"] == "failed":
            log(f"Voice generation failed: {v_job.get('error')}", "error")
            return
        time.sleep(3)

    # 8. Sync Phase
    log("Step 8: Synchronizing Timeline...")
    check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/sync-timeline"))
    log("Timeline synchronized.", "success")

    # 9. Builder & Review Loop
    log("Step 9: Starting Builder-Review Self-Correction Loop...")
    loop_res = check_resp(requests.post(f"{SERVER_URL}/v1/scenes/{scene_id}/builder-review-loop", json={"mode": "auto"}))
    if not loop_res: return
    
    log("Review loop finished. Generating Report...", "success")
    if "report" in loop_res:
        display_report(loop_res["report"])
    else:
        # Sometimes it might just be the scene object if loop is async (though currently it's sync in this codebase)
        log("No detailed report found in response, checking scene status.")
        scenes = check_resp(requests.get(f"{SERVER_URL}/v1/projects/{project_id}/scenes"))
        if scenes:
            curr_scene = next(s for s in scenes if s["id"] == scene_id)
            log(f"Final Review Loop Status: {curr_scene['review_loop_status']}")

def display_report(report):
    if not HAS_RICH:
        print("\n" + "="*20 + " AGENT REPORT " + "="*20)
        print(json.dumps(report, indent=2))
        return

    console.rule("[bold yellow]Agent Activity Report[/bold yellow]")
    
    # Summary Table
    summary = Table(title="Loop Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="magenta")
    summary.add_row("Total Rounds", str(report.get("total_rounds", 0)))
    summary.add_row("Final Status", report.get("final_status", "N/A"))
    summary.add_row("Success", "Yes" if report.get("success") else "No")
    console.print(summary)

    # Rounds Detail
    for i, round_data in enumerate(report.get("rounds", [])):
        round_table = Table(title=f"Round {i+1} Details", show_lines=True)
        round_table.add_column("Agent", style="bold green")
        round_table.add_column("Status/Outcome", style="white")
        
        # Builder
        builder = round_data.get("builder", {})
        round_table.add_row("Builder", f"Outcome: {builder.get('outcome')}")
        
        # Code Reviewer
        cr = round_data.get("code_review", {})
        cr_status = "PASSED" if cr.get("passed") else "FAILED"
        issues = "\n".join([f"- {iss.get('message')}" for iss in cr.get("issues", [])])
        round_table.add_row("Code Reviewer", f"Status: {cr_status}\nIssues:\n{issues if issues else 'None'}")
        
        # Visual Reviewer
        vr = round_data.get("visual_review", {})
        vr_status = "PASSED" if vr.get("passed") else "FAILED"
        v_issues = "\n".join([f"- {iss.get('message')}" for iss in vr.get("issues", [])])
        round_table.add_row("Visual Reviewer", f"Status: {vr_status}\nIssues:\n{v_issues if v_issues else 'None'}")
        
        console.print(round_table)

if __name__ == "__main__":
    try:
        run_debug_test()
    except KeyboardInterrupt:
        log("Test interrupted by user.", "error")
        sys.exit(1)
    except Exception as e:
        log(f"An unexpected error occurred: {e}", "error")
        import traceback
        traceback.print_exc()
        sys.exit(1)
