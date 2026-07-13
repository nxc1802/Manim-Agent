# Frontend API reference

Base URL: `http://localhost:8000/v1`. Send `Authorization: Bearer <Supabase JWT>` when `AUTH_MODE=jwt`; development may use `AUTH_MODE=off`.

All IDs are UUIDs. Errors are `{ "detail": "..." }`. `409 Conflict` means the state changed since the client last read it; refresh and use the new `revision`.

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

## Projects and scenes

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/projects` | Create a project |
| `GET` | `/projects?page=1&limit=20` | List the current user's projects |
| `GET` | `/projects/stats` | Dashboard aggregates |
| `GET` | `/projects/{projectId}` | Read a project |
| `PATCH` | `/projects/{projectId}` | Edit project metadata |
| `DELETE` | `/projects/{projectId}` | Delete project and dependent data |
| `GET` | `/projects/{projectId}/scenes?page=1&limit=20` | List scenes |
| `POST` | `/projects/{projectId}/scenes` | Create a scene |
| `GET` | `/scenes/{sceneId}` | Read a scene |
| `PATCH` | `/scenes/{sceneId}` | Edit user-authored scene fields |
| `DELETE` | `/scenes/{sceneId}` | Delete a scene |

Create scene example:

```json
{ "scene_order": 0, "storyboard_text": "Optional starting brief" }
```

## Human-in-the-loop runs

Start an AI run. A run can be at the **Project-level** (generating the storyboard for all scenes) or at the **Scene-level** (generating Manim code for a specific scene). The response returns a durable run and the first queued agent step.

### Project-level Run (Master Storyteller)

Generate the overall script and a list of scenes for the entire project.

`POST /projects/{projectId}/generate-scenes`

```json
{ "prompt": "Explain derivatives visually in a 2-minute video" }
```
*(This creates an AI run with `scene_id = null` and a `storyboarder` step)*

### Scene-level Run (Manim Coder)

Start a run for exactly one scene.

`POST /projects/{projectId}/ai-runs`

```json
{ "scene_id": "3d7e9b9e-3eea-4a0d-a534-83e35acfac1c", "brief_override": "Focus on the power rule" }
```

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/projects/{projectId}/ai-runs` | List project runs (both project-level and scene-level) |
| `GET` | `/projects/{projectId}/ai-runs/{runId}/steps` | Get every draft/final output in order |
| `PATCH` | `/projects/{projectId}/ai-runs/{runId}/steps/{stepId}` | Save a human edit to a pending draft |
| `POST` | `/projects/{projectId}/ai-runs/{runId}/steps/{stepId}/approve` | Approve an output and queue the next agent |
| `POST` | `/projects/{projectId}/ai-runs/{runId}/steps/{stepId}/reject` | Reject with feedback and queue a retry |
| `POST` | `/projects/{projectId}/ai-runs/{runId}/rollback` | Revert to a previous step (deleting subsequent steps) |

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

The agent kinds are `storyboarder`, `builder`, `code_reviewer`, `visual_reviewer`. 
- **`storyboarder`**: Pauses in `pending_review`. Upon approval, the backend automatically creates `scenes` records from the generated JSON array.
- **`builder`**: Pauses in `pending_review`. Translates visual actions into Manim code.
- **Reviewer steps** (`code_reviewer`, `visual_reviewer`): These are background fallback steps. They are only triggered automatically if the `builder` fails its dry-run. They output a self-loop result containing `passed`, `manim_code`, and `iterations`.

## Rendering and jobs

`POST /projects/{projectId}/render`

```json
{ "scene_id": "...", "render_type": "full", "quality": "1080p" }
```

The scene must have approved builder code. Send `X-Idempotency-Key` for retry-safe button actions. The response is `202 { "job_id": "..." }`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/jobs/{jobId}` | Poll queued/rendering/completed/failed status |
| `GET` | `/jobs/{jobId}/video` | Stream the local Docker Compose artifact after completion |
| `GET` | `/jobs/{jobId}/signed-video-url` | Fetch a signed storage URL after completion |

Use `/jobs/{jobId}/video` for local Docker Compose. `signed-video-url` is available only when the completed artifact has been uploaded to configured Supabase Storage.

## Chat and real-time events

| Transport | Path | Purpose |
| --- | --- | --- |
| `POST` | `/chat` | Short request/response chat |
| WebSocket | `/ws/chat?token=<jwt>` | Token-streamed chat |
| WebSocket | `/ws/projects/{projectId}?token=<jwt>` | HITL and render state events |

Chat body:

```json
{ "messages": [{ "role": "user", "content": "Explain a derivative in one sentence." }] }
```

For `/ws/chat`, send the same JSON text frame. Receive frames such as `{ "type": "delta", "text": "..." }`, then `{ "type": "done", "model": "..." }`.

For project events, retain the latest step from `data.step`; typical types are `hitl.step.queued`, `hitl.step.generating`, `hitl.step.pending_review`, `hitl.step.edited`, `hitl.step.approved`, `hitl.step.rejected`, `hitl.step.failed`, `hitl.run.rolled_back`, `render.queued`, `render.started`, `render.completed` and `render.failed`.
*Note*: During `hitl.step.generating`, the payload may include a `content_delta` field containing the streamed chunk of the LLM output.

Send `ping` to receive `pong`.

## Health and API schema

- `GET /health` confirms the API process.
- `GET /ready` also checks Redis.
- `GET /openapi.json` and `/docs` are generated from the running public contract.

`/internal/*` endpoints are service-to-service only and must never be called by the frontend.
