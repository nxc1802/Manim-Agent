ALTER TABLE public.scenes
  ADD COLUMN IF NOT EXISTS video_url TEXT,
  ADD COLUMN IF NOT EXISTS generation_status TEXT;

UPDATE public.scenes
SET generation_status = 'pending'
WHERE generation_status IS NULL;

ALTER TABLE public.scenes
  ALTER COLUMN generation_status SET DEFAULT 'pending',
  ALTER COLUMN generation_status SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'scenes_generation_status_check'
      AND conrelid = 'public.scenes'::regclass
  ) THEN
    ALTER TABLE public.scenes
      ADD CONSTRAINT scenes_generation_status_check
      CHECK (generation_status IN ('pending', 'generating', 'completed', 'failed'));
  END IF;
END;
$$;

ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS video_url TEXT;
