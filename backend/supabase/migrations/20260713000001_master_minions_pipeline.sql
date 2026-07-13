-- ==========================================
-- Manim Agent - Master Minions Pipeline Update
-- Location: supabase/migrations/20260713000001_master_minions_pipeline.sql
-- ==========================================

-- 1. Make scene_id nullable in ai_runs and ai_steps
ALTER TABLE public.ai_runs ALTER COLUMN scene_id DROP NOT NULL;
ALTER TABLE public.ai_steps ALTER COLUMN scene_id DROP NOT NULL;

-- 2. Update ai_steps kind constraint (Keep legacy kinds to avoid constraint violation on existing rows)
ALTER TABLE public.ai_steps DROP CONSTRAINT ai_steps_kind_check;
ALTER TABLE public.ai_steps ADD CONSTRAINT ai_steps_kind_check CHECK (kind IN (
  'director', 'planner', 'scene_designer',  -- Legacy kinds
  'storyboarder', 'builder', 'code_reviewer', 'visual_reviewer' -- New/Active kinds
));
