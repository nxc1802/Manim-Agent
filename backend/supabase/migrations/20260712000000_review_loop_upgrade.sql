-- ==========================================
-- Migration: Add visual_reviewer + hitl_enabled
-- ==========================================

-- 1. Add hitl_enabled column to ai_runs
ALTER TABLE public.ai_runs
  ADD COLUMN IF NOT EXISTS hitl_enabled BOOLEAN NOT NULL DEFAULT TRUE;

-- 2. Update ai_steps kind constraint to include visual_reviewer
ALTER TABLE public.ai_steps
  DROP CONSTRAINT IF EXISTS ai_steps_kind_check;
ALTER TABLE public.ai_steps
  ADD CONSTRAINT ai_steps_kind_check
  CHECK (kind IN (
    'director',
    'planner',
    'scene_designer',
    'idea_sketcher',
    'storyboarder',
    'builder',
    'code_reviewer',
    'visual_reviewer'
  ));
