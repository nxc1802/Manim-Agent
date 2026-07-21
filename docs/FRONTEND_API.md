# Frontend API reference

Production Vercel builds use the absolute protected Hugging Face base
`https://<space>.hf.space/v1`; local Backend defaults to
`http://localhost:8000/v1`. `VITE_WS_BASE_URL` uses the same HTTPS base and is
converted to `wss://` by the client. Send `Authorization: Bearer <Supabase JWT>`
when `AUTH_MODE=jwt`; development may use `AUTH_MODE=off`.

All IDs are UUIDs. Public errors use the stable envelope below. `409 Conflict` means the state changed since the client last read it; refresh and use the new `revision`.

```json
{
  "error": {
    "code": "conflict",
    "message": "Step was updated elsewhere",
    "request_id": "..."
  },
  "details": null
}
```

Backend also returns the same ID in `X-Request-ID`; frontend includes its generated `X-Request-ID` on every REST call.

## User Settings

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/users/me/settings` | Get the current user's personalized settings |
| `PATCH` | `/users/me/settings` | Update the current user's settings |

Settings example:
```json
{
  "theme": "dark",
  "language": "en",
  "hitl_enabled": true,
  "ai_agent_persona": "Professional Educator",
  "template_selection": "Educational"
}
```

The frontend reads these settings before starting a run: `hitl_enabled` selects review versus auto-approval, while `ai_agent_persona` and `template_selection` are included in the Storyboard/Builder prompt context. The lightweight Idea Sketch stage always auto-advances after producing a validated blueprint.

## Projects and scenes

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/projects` | Create a project |
| `GET` | `/projects?page=1&limit=20` | List the current user's projects |
| `GET` | `/projects/stats` | Dashboard aggregates |
| `GET` | `/projects/{projectId}` | Read a project |
| `DELETE` | `/projects/{projectId}` | Delete project and dependent data |
| `GET` | `/projects/{projectId}/scenes?page=1&limit=20` | List scenes |

Scenes are created only when the approved Master storyboard is persisted; this prevents the frontend from creating scenes that have no approved plan.

**New Fields:**
- `Project.video_url`: Persisted URL of the full project final video.
- `Scene.video_url`: Persisted URL of the scene's rendered video.
- `Scene.generation_status`: Status of the scene's AI code generation (`pending`, `generating`, `completed`, `failed`). Can be used to show color-coded UI.

## Human-in-the-loop runs

Start an AI run. A run can be at the **Project-level** (generating the storyboard for all scenes) or at the **Scene-level** (generating Manim code for a specific scene). The response returns a durable run and the first queued agent step.

### Project-level Run (Master Storyteller)

Generate the overall script and a list of scenes for the entire project.

`POST /projects/{projectId}/generate-scenes`

```json
{ "prompt": "Explain derivatives visually", "hitl_enabled": true }
```

### Scene-level run (Manim Coder & Debugger)

Start a run for exactly one scene to generate its code. `hitl_enabled` defaults to the saved user setting in the frontend; send `false` only for deliberate test runs.

`POST /projects/{projectId}/ai-runs`

```json
{ "scene_id": "3d7e9b9e-3eea-4a0d-a534-83e35acfac1c", "brief_override": "Make the circle blue", "hitl_enabled": true }
```

### Managing Runs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/projects/{projectId}/ai-runs` | List project runs |
| `GET` | `/projects/{projectId}/ai-runs/{runId}/steps` | Get every draft/final output in order |
| `PATCH` | `/projects/{projectId}/ai-runs/{runId}/steps/{stepId}` | Save a human edit to a pending draft |
| `POST` | `/projects/{projectId}/ai-runs/{runId}/steps/{stepId}/approve` | Approve an output and persist its result |
| `POST` | `/projects/{projectId}/ai-runs/{runId}/steps/{stepId}/reject` | Reject with feedback and queue a retry |
| `POST` | `/projects/{projectId}/ai-runs/{runId}/rollback` | Reopen an approved draft and invalidate its derived artifacts |

Agent step shape:

```json
{
  "id": "...",
  "kind": "builder",
  "status": "pending_review",
  "draft_output": { "manim_code": "from manim import ..." },
  "final_output": null,
  "revision": 1
}
```

Edit a draft (only `pending_review`):

```json
{ "expected_revision": 1, "draft_output": { "manim_code": "edited code" } }
```

Approve the currently displayed version:

```json
{ "expected_revision": 2 }
```

The backend increments revision on both edit and approval. To approve a final transformation in the same call, add `final_output`. Rejection requires `{ "expected_revision": 2, "feedback": "Use a slower camera transition." }`.

Rollback is intentionally cascading. Reopening a Master draft cancels unfinished
Builder children and removes the scene topology created by that approval.
Reopening a Builder draft clears its approved code, scene video and project
video. A later approval creates/persists fresh derivatives.

The public generation pipeline has three visible stages: `idea_sketcher`, `storyboarder`, and `builder`.
- **Idea Sketch**: produces a concise validated concept blueprint, persists it as an `AgentStep`, and auto-advances without adding another HITL pause.
- **Storyboard**: runs at the project level, consumes the approved blueprint, generates a JSON array of scenes (with `scene_order`, `narration`, and `visual_action`), and pauses in `pending_review`. Upon approval, the backend automatically creates `scene` records in the database **and dispatches `builder` tasks in parallel for all created scenes**.
- **Builder**: runs at the scene level to generate Python Manim code based on `visual_action`. It performs internal code and visual review before returning its draft. `draft_output.auto_review` records the review attempts; changes are minimal exact source replacements, never a full rewrite.

Before each Code Reviewer fix, `runtime_api_context` records the installed Manim version, implicated symbol, live signature/description/example, and any runtime-verified compatibility alternative. Later attempts also receive the failed repair ledger. Iterations expose `error_fingerprint`, `strategy_fingerprint`, `outcome`, and Strategy Guard fields; the active repair ledger resets only after execution advances to a new error.

## Rendering and jobs

`POST /projects/{projectId}/render`

```json
{ "scene_id": "...", "render_type": "full", "quality": "1080p" }
```

To render the **entire project** (concatenating all rendered scenes), omit `scene_id` and set `render_type` to `"full_project"`:
```json
{ "render_type": "full_project", "quality": "1080p" }
```

The scene must have approved builder code. Send `X-Idempotency-Key` for retry-safe button actions. The response is `202 { "job_id": "..." }`.
Upon successful render completion, the resulting video URL is persistently saved to `scene.video_url` (or `project.video_url` for full project renders), meaning it will persist across page reloads.

The Backend binds each job to the exact source snapshot present at enqueue time.
If code, generation state, or a full-project scene video changes before claim or
completion, the job becomes terminal `failed` with
`error_code="stale_render_source"`; its artifact is never attached to current
content. A retry uses the new source snapshot and receives a new job ID.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/jobs/{jobId}` | Poll queued/rendering/completed/failed status |
| `GET` | `/jobs/{jobId}/video` | Stream the local Docker Compose artifact after completion |
| `GET` | `/jobs/{jobId}/signed-video-url` | Fetch a signed storage URL after completion |
| `GET` | `/projects/{projectId}/render-jobs?active=true` | Recover active scene/project jobs after reload or reconnect |
| `GET` | `/projects/{projectId}/rendered-video?scene_id={sceneId}` | Stream the durable local scene/project video reference |
| `GET` | `/projects/{projectId}/rendered-video-url?scene_id={sceneId}` | Sign the durable private scene/project video reference |

Omit `scene_id` on either durable-video route to resolve the full-project video.
Use job-specific routes for an immediate completion response. Reload uses the
project/scene routes, so persisted playback does not depend on Redis retaining
the original render job. The worker currently reports start and completion, so
the UI uses an indeterminate rendering label rather than inventing intermediate
percentages.

## Real-time events

| Transport | Path | Purpose |
| --- | --- | --- |
| WebSocket | `/ws/projects/{projectId}` | HITL and render state events |

In JWT mode the browser requests subprotocols `manim.jwt` and `<access-token>`.
Backend authenticates the second value and negotiates only `manim.jwt`; query
string tokens are not accepted because URLs are commonly retained in access
logs and browser/proxy telemetry.

For step events, retain the latest step from `data.step`; render and rollback events intentionally do not require a step. Typical types are `hitl.step.queued`, `hitl.step.generating`, `hitl.step.review`, `hitl.step.pending_review`, `hitl.step.edited`, `hitl.step.approved`, `hitl.step.auto_approved`, `hitl.step.rejected`, `hitl.step.failed`, `hitl.run.rolled_back`, `render.queued`, `render.started`, `render.completed` and `render.failed`.

**Note:** For step events, the backend explicitly provides a `data.scene_id` property at the top-level payload to help the frontend easily map incoming AI completion/error events to the correct scene card UI.

`hitl.step.generating` carries a `data.content_delta` string. The frontend must append it in arrival order (the Studio renders that queue character-by-character). `hitl.step.review` carries a stage such as:

```json
{
  "review": {
    "phase": "fixing",
    "reviewer": "code",
    "attempt": 3,
    "model": "gemini-3.5-flash",
    "message": "Đang thực hiện fix bug lần 3 với gemini-3.5-flash"
  }
}
```

When `phase` is `patch_applied`, `original_code`, `replacement_code`, and `explanation` are supplied. Render these as an explicit before/after diff; reviewer edits are always one exact replacement, never a full-file rewrite.

Review phases also include `runtime_api_context`, `strategy_guard`, `repair_memory_reset`, and `patch_rejected`. The complete structured audit is persisted inside the Builder draft output; WebSocket messages are progress hints.

Send `ping` to receive `pong`. Clients reconnect with backoff and refetch project/runs/scenes/steps plus `render-jobs?active=true` after `open`; Pub/Sub delivery is not assumed to be durable. A REST response is applied per project/scene only when its captured event version is still current, so a slow reload cannot overwrite a newer live run. Render polling continues with bounded backoff while the page remains mounted, including when the WebSocket is unavailable.

## Health and API schema

- `GET /health` confirms the API process.
- Backend `GET /ready` checks Redis, Supabase/HITL persistence, content-store mode, and live Celery consumers for both `ai` and `render` queues.
- The single-Space production profile runs AI Core as Celery workers, not as a public HTTP service. Its standalone Compose API may expose a separate readiness endpoint for development diagnostics.
- `GET /openapi.json` and `/docs` are generated from the running public contract.

`/internal/*` endpoints are service-to-service only and must never be called by the frontend.
