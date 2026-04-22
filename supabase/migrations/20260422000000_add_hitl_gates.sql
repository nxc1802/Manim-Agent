-- Migration: Add HITL Gates for Plan and Voice Script
-- Target: public.scenes

-- 1. Add plan_status column
ALTER TABLE public.scenes 
ADD COLUMN IF NOT EXISTS plan_status TEXT NOT NULL DEFAULT 'missing'
CHECK (plan_status IN ('missing', 'pending_review', 'approved'));

-- 2. Add voice_script_status column
ALTER TABLE public.scenes 
ADD COLUMN IF NOT EXISTS voice_script_status TEXT NOT NULL DEFAULT 'missing'
CHECK (voice_script_status IN ('missing', 'pending_review', 'approved'));

-- 3. Migration logic for existing records:
-- If planner_output exists, assume it was approved in the old system or needs review.
-- For safety, we'll set existing records with planner_output to 'approved' so we don't break current workflows.
UPDATE public.scenes 
SET plan_status = 'approved', voice_script_status = 'approved'
WHERE planner_output IS NOT NULL AND plan_status = 'missing';

-- 4. Indices for new status columns
CREATE INDEX IF NOT EXISTS idx_scenes_plan_status ON public.scenes (plan_status);
CREATE INDEX IF NOT EXISTS idx_scenes_voice_script_status ON public.scenes (voice_script_status);

-- 5. (Optional Fix) Ensure review_loop_status constraints are up to date
-- The existing table already has the constraint, but if we wanted to add a new state, we'd do it here.
-- ALTER TABLE public.scenes DROP CONSTRAINT IF EXISTS scenes_review_loop_status_check;
-- ALTER TABLE public.scenes ADD CONSTRAINT scenes_review_loop_status_check 
-- CHECK (review_loop_status IN ('idle', 'running', 'completed', 'hitl_pending', 'failed'));
