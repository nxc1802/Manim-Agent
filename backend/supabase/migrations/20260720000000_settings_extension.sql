-- Location: supabase/migrations/20260720000000_settings_extension.sql
-- Description: Persist every user-facing generation, review, render, and TTS setting.
-- Safe to run repeatedly from the Supabase SQL Editor.

BEGIN;

ALTER TABLE public.user_settings
  ADD COLUMN IF NOT EXISTS visual_review_enabled BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS code_review_enabled BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS max_review_attempts INTEGER NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS video_quality TEXT NOT NULL DEFAULT '720p',
  ADD COLUMN IF NOT EXISTS fps INTEGER NOT NULL DEFAULT 30,
  ADD COLUMN IF NOT EXISTS llm_model TEXT,
  ADD COLUMN IF NOT EXISTS llm_temperature NUMERIC(3, 2),
  ADD COLUMN IF NOT EXISTS llm_max_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS llm_agent_configs JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS tts_enabled BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS tts_voice TEXT NOT NULL DEFAULT 'auto',
  ADD COLUMN IF NOT EXISTS tts_speaking_rate NUMERIC(3, 2) NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS tts_pitch NUMERIC(4, 1) NOT NULL DEFAULT 0;

-- Existing deployments may already have nullable or out-of-range versions of
-- these columns. Normalize them before tightening the database contract.
UPDATE public.user_settings
SET
  language = CASE WHEN language IN ('vi', 'en') THEN language ELSE 'en' END,
  ai_agent_persona = CASE
    WHEN ai_agent_persona IN (
      'Professional Educator',
      'Creative Storyteller',
      'Technical Explainer'
    ) THEN ai_agent_persona
    ELSE 'Professional Educator'
  END,
  template_selection = CASE
    WHEN template_selection IN (
      'Educational',
      'Conceptual walkthrough',
      'Worked example'
    ) THEN template_selection
    ELSE 'Educational'
  END,
  visual_review_enabled = COALESCE(visual_review_enabled, true),
  code_review_enabled = COALESCE(code_review_enabled, true),
  max_review_attempts = CASE
    WHEN max_review_attempts BETWEEN 1 AND 5 THEN max_review_attempts
    ELSE 3
  END,
  video_quality = CASE
    WHEN video_quality IN ('480p', '720p', '1080p', '4k') THEN video_quality
    ELSE '720p'
  END,
  fps = CASE WHEN fps IN (15, 30, 60) THEN fps ELSE 30 END,
  llm_model = CASE
    WHEN llm_model IS NULL OR llm_model IN (
      'gemini-3-flash-preview',
      'gemini-3.5-flash',
      'gemma-4-31b-it'
    ) THEN llm_model
    ELSE NULL
  END,
  llm_temperature = CASE
    WHEN llm_temperature IS NULL OR llm_temperature BETWEEN 0 AND 1
      THEN llm_temperature
    ELSE NULL
  END,
  llm_max_tokens = CASE
    WHEN llm_max_tokens IS NULL OR llm_max_tokens BETWEEN 1024 AND 16384
      THEN llm_max_tokens
    ELSE NULL
  END,
  llm_agent_configs = CASE
    WHEN jsonb_typeof(llm_agent_configs) = 'object' THEN llm_agent_configs
    ELSE '{}'::jsonb
  END,
  tts_enabled = COALESCE(tts_enabled, false),
  tts_voice = CASE
    WHEN tts_voice IN (
      'auto',
      'vi-VN-Standard-A',
      'vi-VN-Standard-B',
      'en-US-Standard-C',
      'en-US-Standard-D'
    ) THEN tts_voice
    ELSE 'auto'
  END,
  tts_speaking_rate = CASE
    WHEN tts_speaking_rate BETWEEN 0.25 AND 2 THEN tts_speaking_rate
    ELSE 1
  END,
  tts_pitch = CASE WHEN tts_pitch BETWEEN -20 AND 20 THEN tts_pitch ELSE 0 END
WHERE
  language IS NULL OR language NOT IN ('vi', 'en')
  OR ai_agent_persona IS NULL OR ai_agent_persona NOT IN (
    'Professional Educator',
    'Creative Storyteller',
    'Technical Explainer'
  )
  OR template_selection IS NULL OR template_selection NOT IN (
    'Educational',
    'Conceptual walkthrough',
    'Worked example'
  )
  OR visual_review_enabled IS NULL
  OR code_review_enabled IS NULL
  OR max_review_attempts IS NULL OR max_review_attempts NOT BETWEEN 1 AND 5
  OR video_quality IS NULL OR video_quality NOT IN ('480p', '720p', '1080p', '4k')
  OR fps IS NULL OR fps NOT IN (15, 30, 60)
  OR (llm_model IS NOT NULL AND llm_model NOT IN (
    'gemini-3-flash-preview',
    'gemini-3.5-flash',
    'gemma-4-31b-it'
  ))
  OR (llm_temperature IS NOT NULL AND llm_temperature NOT BETWEEN 0 AND 1)
  OR (llm_max_tokens IS NOT NULL AND llm_max_tokens NOT BETWEEN 1024 AND 16384)
  OR llm_agent_configs IS NULL
  OR jsonb_typeof(llm_agent_configs) IS DISTINCT FROM 'object'
  OR tts_enabled IS NULL
  OR tts_voice IS NULL OR tts_voice NOT IN (
    'auto',
    'vi-VN-Standard-A',
    'vi-VN-Standard-B',
    'en-US-Standard-C',
    'en-US-Standard-D'
  )
  OR tts_speaking_rate IS NULL OR tts_speaking_rate NOT BETWEEN 0.25 AND 2
  OR tts_pitch IS NULL OR tts_pitch NOT BETWEEN -20 AND 20;

ALTER TABLE public.user_settings
  ALTER COLUMN visual_review_enabled SET DEFAULT true,
  ALTER COLUMN visual_review_enabled SET NOT NULL,
  ALTER COLUMN code_review_enabled SET DEFAULT true,
  ALTER COLUMN code_review_enabled SET NOT NULL,
  ALTER COLUMN max_review_attempts SET DEFAULT 3,
  ALTER COLUMN max_review_attempts SET NOT NULL,
  ALTER COLUMN video_quality SET DEFAULT '720p',
  ALTER COLUMN video_quality SET NOT NULL,
  ALTER COLUMN fps SET DEFAULT 30,
  ALTER COLUMN fps SET NOT NULL,
  ALTER COLUMN llm_agent_configs SET DEFAULT '{}'::jsonb,
  ALTER COLUMN llm_agent_configs SET NOT NULL,
  ALTER COLUMN tts_enabled SET DEFAULT false,
  ALTER COLUMN tts_enabled SET NOT NULL,
  ALTER COLUMN tts_voice SET DEFAULT 'auto',
  ALTER COLUMN tts_voice SET NOT NULL,
  ALTER COLUMN tts_speaking_rate SET DEFAULT 1,
  ALTER COLUMN tts_speaking_rate SET NOT NULL,
  ALTER COLUMN tts_pitch SET DEFAULT 0,
  ALTER COLUMN tts_pitch SET NOT NULL;

ALTER TABLE public.user_settings
  DROP CONSTRAINT IF EXISTS user_settings_language_check,
  DROP CONSTRAINT IF EXISTS user_settings_ai_agent_persona_check,
  DROP CONSTRAINT IF EXISTS user_settings_template_selection_check,
  DROP CONSTRAINT IF EXISTS user_settings_max_review_attempts_check,
  DROP CONSTRAINT IF EXISTS user_settings_video_quality_check,
  DROP CONSTRAINT IF EXISTS user_settings_fps_check,
  DROP CONSTRAINT IF EXISTS user_settings_llm_model_check,
  DROP CONSTRAINT IF EXISTS user_settings_llm_temperature_check,
  DROP CONSTRAINT IF EXISTS user_settings_llm_max_tokens_check,
  DROP CONSTRAINT IF EXISTS user_settings_llm_agent_configs_check,
  DROP CONSTRAINT IF EXISTS user_settings_tts_voice_check,
  DROP CONSTRAINT IF EXISTS user_settings_tts_speaking_rate_check,
  DROP CONSTRAINT IF EXISTS user_settings_tts_pitch_check;

ALTER TABLE public.user_settings
  ADD CONSTRAINT user_settings_language_check
    CHECK (language IN ('vi', 'en')),
  ADD CONSTRAINT user_settings_ai_agent_persona_check
    CHECK (ai_agent_persona IN (
      'Professional Educator',
      'Creative Storyteller',
      'Technical Explainer'
    )),
  ADD CONSTRAINT user_settings_template_selection_check
    CHECK (template_selection IN (
      'Educational',
      'Conceptual walkthrough',
      'Worked example'
    )),
  ADD CONSTRAINT user_settings_max_review_attempts_check
    CHECK (max_review_attempts BETWEEN 1 AND 5),
  ADD CONSTRAINT user_settings_video_quality_check
    CHECK (video_quality IN ('480p', '720p', '1080p', '4k')),
  ADD CONSTRAINT user_settings_fps_check
    CHECK (fps IN (15, 30, 60)),
  ADD CONSTRAINT user_settings_llm_model_check
    CHECK (llm_model IS NULL OR llm_model IN (
      'gemini-3-flash-preview',
      'gemini-3.5-flash',
      'gemma-4-31b-it'
    )),
  ADD CONSTRAINT user_settings_llm_temperature_check
    CHECK (llm_temperature IS NULL OR llm_temperature BETWEEN 0 AND 1),
  ADD CONSTRAINT user_settings_llm_max_tokens_check
    CHECK (llm_max_tokens IS NULL OR llm_max_tokens BETWEEN 1024 AND 16384),
  ADD CONSTRAINT user_settings_llm_agent_configs_check
    CHECK (jsonb_typeof(llm_agent_configs) = 'object'),
  ADD CONSTRAINT user_settings_tts_voice_check
    CHECK (tts_voice IN (
      'auto',
      'vi-VN-Standard-A',
      'vi-VN-Standard-B',
      'en-US-Standard-C',
      'en-US-Standard-D'
    )),
  ADD CONSTRAINT user_settings_tts_speaking_rate_check
    CHECK (tts_speaking_rate BETWEEN 0.25 AND 2),
  ADD CONSTRAINT user_settings_tts_pitch_check
    CHECK (tts_pitch BETWEEN -20 AND 20);

COMMENT ON COLUMN public.user_settings.llm_agent_configs IS
  'Per-agent model, temperature, token, reasoning, and ordered reviewer-tier configuration.';

ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_settings_owner_all ON public.user_settings;
CREATE POLICY user_settings_owner_all
  ON public.user_settings
  FOR ALL
  TO authenticated
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id);

-- Explicit Data API privileges are required on projects using the current
-- security-first Supabase Data API defaults. RLS still limits rows by owner.
REVOKE ALL ON TABLE public.user_settings FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.user_settings TO authenticated;

DO $$
DECLARE
  settings_column_count INTEGER;
BEGIN
  SELECT COUNT(*)
  INTO settings_column_count
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'user_settings'
    AND column_name IN (
      'visual_review_enabled',
      'code_review_enabled',
      'max_review_attempts',
      'video_quality',
      'fps',
      'llm_model',
      'llm_temperature',
      'llm_max_tokens',
      'llm_agent_configs',
      'tts_enabled',
      'tts_voice',
      'tts_speaking_rate',
      'tts_pitch'
    );

  IF settings_column_count <> 13 THEN
    RAISE EXCEPTION
      'user_settings migration incomplete: expected 13 settings columns, found %',
      settings_column_count;
  END IF;
END
$$;

-- Ask PostgREST to refresh immediately so new columns do not return PGRST204.
NOTIFY pgrst, 'reload schema';

COMMIT;
