-- Keep the database contract aligned with the public settings schema and the
-- AI worker's configured defaults.  The previous migration pre-dated the
-- Gemini 3.5 Lite/3.6 and Gemma options exposed by the UI.

BEGIN;

ALTER TABLE public.user_settings
  DROP CONSTRAINT IF EXISTS user_settings_llm_model_check;

ALTER TABLE public.user_settings
  ADD CONSTRAINT user_settings_llm_model_check
  CHECK (llm_model IS NULL OR llm_model IN (
    'gemini-3-flash-preview',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.6-flash',
    'gemma-4-31b-it',
    'gemma-4-26b-it',
    'gemma-4-31b-it-thinking',
    'gemma-4-26b-it-thinking'
  ));

COMMIT;
