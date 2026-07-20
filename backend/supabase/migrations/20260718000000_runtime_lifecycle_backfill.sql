-- Align rows created before the current Master/Builder lifecycle was enforced.
-- The application remains the source of transitions after this one-time repair.

UPDATE public.ai_runs AS run
SET status = 'completed'
WHERE run.status IN ('queued', 'waiting_for_human')
  AND EXISTS (
    SELECT 1
    FROM public.ai_steps AS step
    WHERE step.run_id = run.id
      AND step.status = 'approved'
  )
  AND NOT EXISTS (
    SELECT 1
    FROM public.ai_steps AS step
    WHERE step.run_id = run.id
      AND step.status IN ('queued', 'generating', 'pending_review', 'failed')
  );

UPDATE public.scenes
SET generation_status = 'completed'
WHERE NULLIF(BTRIM(manim_code), '') IS NOT NULL
  AND generation_status <> 'completed';

UPDATE public.projects AS project
SET status = 'completed'
WHERE project.status <> 'archived'
  AND EXISTS (
    SELECT 1 FROM public.scenes AS scene WHERE scene.project_id = project.id
  )
  AND NOT EXISTS (
    SELECT 1
    FROM public.scenes AS scene
    WHERE scene.project_id = project.id
      AND scene.generation_status <> 'completed'
  );

-- Enforce 1-based ordering for new/updated rows without making deployment
-- fail on an unknown legacy row. Existing rows can be validated separately.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'scenes_scene_order_positive'
      AND conrelid = 'public.scenes'::regclass
  ) THEN
    ALTER TABLE public.scenes
      ADD CONSTRAINT scenes_scene_order_positive
      CHECK (scene_order >= 1) NOT VALID;
  END IF;
END;
$$;
