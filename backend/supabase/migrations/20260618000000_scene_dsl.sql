ALTER TABLE public.scenes ADD COLUMN scene_dsl JSONB;
ALTER TABLE public.scenes ADD COLUMN scene_dsl_version INTEGER NOT NULL DEFAULT 0;
