-- Expose the lightweight idea sketcher as a durable, user-visible pipeline stage.
-- Safe to run repeatedly from the Supabase SQL Editor.

BEGIN;

ALTER TABLE public.ai_steps
  DROP CONSTRAINT IF EXISTS ai_steps_kind_check;

ALTER TABLE public.ai_steps
  ADD CONSTRAINT ai_steps_kind_check CHECK (kind IN (
    'director',
    'planner',
    'scene_designer',
    'idea_sketcher',
    'storyboarder',
    'builder',
    'code_reviewer',
    'visual_reviewer'
  ));

NOTIFY pgrst, 'reload schema';

COMMIT;
