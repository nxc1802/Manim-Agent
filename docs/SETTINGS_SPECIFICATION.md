# Settings contract

This document is the source of truth for user-facing settings. Every option
listed below is validated by Backend, persisted in `public.user_settings`, and
consumed by the application.

## Supported settings

| Field | Options | Default | Runtime effect |
| --- | --- | --- | --- |
| `theme` | `dark`, `light` | `dark` | Applied by the frontend immediately and persisted automatically. |
| `language` | `vi`, `en` | `en` | Used as the default source language when a new project is created. |
| `video_quality` | `480p`, `720p`, `1080p`, `4k` | `720p` | Sent to the Manim worker as `-ql`, `-qm`, `-qh`, or `-qk`. |
| `fps` | `15`, `30`, `60` | `30` | Sent to the Manim worker with `--fps`. |
| `code_review_enabled` | boolean | `true` | Enables the Builder code-review loop. |
| `visual_review_enabled` | boolean | `true` | Enables the post-code visual-review loop. |
| `max_review_attempts` | integer `1`–`5` | `3` | Caps the total automatic review attempts for each code or visual review loop. |
| `hitl_enabled` | boolean | `true` | Requires a human approval before a generated draft is applied. |
| `ai_agent_persona` | `Professional Educator`, `Creative Storyteller`, `Technical Explainer` | `Professional Educator` | Explicit creative direction sent to the Storyboarder and Builder prompts. |
| `template_selection` | `Educational`, `Conceptual walkthrough`, `Worked example` | `Educational` | Explicit structure and pacing direction sent to the Storyboarder and Builder prompts. |
| `llm_agent_configs` | Idea sketcher/Storyboarder/Builder: `model`, `temperature`, `max_tokens`, `reasoning_effort`; reviewers: `temperature`, `max_tokens`, and optional ordered `review_tiers` | `{}` | Gemini accepts `minimal`, `low`, `medium`, or `high`; Gemini 3 reasoning cannot be fully disabled. Each reviewer tier stores its own supported `model`, `max_attempts` (1–5), and reasoning level. `review_tiers: null` uses the backend escalation chain unchanged. Gemma runs with `none`, which means the unsupported parameter is omitted. |
| `tts_enabled` | boolean | `false` | When true, render worker synthesizes `voice_script` and muxes AAC audio into each scene MP4. |
| `tts_voice` | `auto`, `vi-VN-Standard-A`, `vi-VN-Standard-B`, `en-US-Standard-C`, `en-US-Standard-D` | `auto` | Chooses a supported Google Cloud Standard voice; `auto` matches the project source language. |
| `tts_speaking_rate` | `0.25`–`2.0` | `1.0` | Passed to Google Cloud Text-to-Speech `audioConfig.speakingRate`. |
| `tts_pitch` | `-20`–`20` | `0` | Passed to Google Cloud Text-to-Speech `audioConfig.pitch` in semitones. |

## API

- `GET /v1/users/me/settings` returns the validated settings. If no row exists,
  Backend returns the defaults.
- `PATCH /v1/users/me/settings` accepts only fields in the table above. Unknown
  fields are rejected with HTTP 422 instead of being silently ignored.

## Storage and migration

Apply all files in `backend/supabase/migrations/` in lexical order before
using durable settings. In particular,
`20260720000000_settings_extension.sql` adds the review, rendering, LLM, and
TTS columns.

Backend atomically upserts the complete validated document into
`public.user_settings` by `user_id`. Auth metadata is not used as a fallback or
as an authorization source. If PostgREST has not loaded the extension columns,
the API returns a clear migration error instead of silently dropping settings.

TTS uses the server-side `GOOGLE_API_KEY`; it must belong to a Google Cloud
project with Cloud Text-to-Speech enabled. The key is never sent to the
browser or the Manim subprocess.

The final-project render consumes each scene's approved `manim_code` and
`voice_script` directly. It rerenders valid scenes in order, skips invalid
scene sources with an audit message, and verifies that the final MP4 contains
an audio stream whenever TTS is enabled.

The database may still contain legacy columns (`builder_model`,
`output_language`, `max_parallel_scenes`, and the former global `llm_*`
overrides) from earlier revisions. They are retained only for backward
compatibility; the UI writes `llm_agent_configs`, which is the active runtime
contract.
