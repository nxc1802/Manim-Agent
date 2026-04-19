-- CI / local Postgres: minimal auth stub + RLS matching production policies (doc 09).
-- Requires PostgreSQL 15+ (EXECUTE FUNCTION on triggers).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

DROP SCHEMA IF EXISTS auth CASCADE;
CREATE SCHEMA auth;

CREATE TABLE auth.users (
  id UUID PRIMARY KEY
);

INSERT INTO auth.users (id) VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');

CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql
STABLE
SET search_path = public, auth
AS $$
  SELECT CASE
    WHEN trim(coalesce(current_setting('app.jwt_sub', true), '')) = '' THEN NULL
    ELSE trim(current_setting('app.jwt_sub', true))::uuid
  END;
$$;

CREATE TABLE public.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  description TEXT,
  source_language TEXT DEFAULT 'vi',
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'processing', 'completed', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_user_id ON public.projects (user_id);

CREATE TABLE public.scenes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_order INTEGER NOT NULL,
  storyboard_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (storyboard_status IN ('missing', 'pending_review', 'approved')),
  storyboard_text TEXT,
  voice_script TEXT,
  planner_output JSONB,
  sync_segments JSONB,
  manim_code TEXT,
  manim_code_version INTEGER NOT NULL DEFAULT 1,
  audio_url TEXT,
  timestamps JSONB,
  duration_seconds NUMERIC(10, 3),
  review_loop_status TEXT NOT NULL DEFAULT 'idle'
    CHECK (review_loop_status IN ('idle', 'running', 'completed', 'hitl_pending', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, scene_order)
);

CREATE INDEX idx_scenes_project_id ON public.scenes (project_id);

CREATE TABLE public.render_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE SET NULL,
  job_type TEXT NOT NULL CHECK (job_type IN ('preview', 'full')),
  render_quality TEXT CHECK (render_quality IN ('720p', '1080p', '4k')),
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'rendering', 'completed', 'failed', 'cancelled')),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  logs TEXT,
  asset_url TEXT,
  error_code TEXT,
  webhook_url TEXT,
  docker_image_tag TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_render_jobs_project ON public.render_jobs (project_id);

CREATE TABLE public.voice_jobs (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'synthesizing', 'completed', 'failed', 'cancelled')),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  logs TEXT,
  asset_url TEXT,
  error_code TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  voice_engine TEXT NOT NULL DEFAULT 'piper',
  docker_image_tag TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_voice_jobs_project ON public.voice_jobs (project_id);

CREATE TABLE public.pipeline_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  report JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_runs_project ON public.pipeline_runs (project_id);

CREATE TABLE public.worker_service_audit (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE SET NULL,
  render_job_id UUID REFERENCES public.render_jobs (id) ON DELETE SET NULL,
  voice_job_id UUID REFERENCES public.voice_jobs (id) ON DELETE SET NULL,
  worker_kind TEXT NOT NULL CHECK (worker_kind IN ('manim', 'tts')),
  worker_name TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_worker_audit_project ON public.worker_service_audit (project_id);

CREATE TABLE public.assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE SET NULL,
  file_name TEXT NOT NULL,
  file_type TEXT NOT NULL CHECK (file_type IN ('audio', 'image', 'video', 'subtitle', 'other')),
  bucket_path TEXT NOT NULL,
  meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_assets_project ON public.assets (project_id);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_projects_updated_at
  BEFORE UPDATE ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_scenes_updated_at
  BEFORE UPDATE ON public.scenes
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.render_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.worker_service_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY projects_owner_all
  ON public.projects
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY scenes_by_project_owner
  ON public.scenes
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = scenes.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = scenes.project_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY render_jobs_by_project_owner
  ON public.render_jobs
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = render_jobs.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = render_jobs.project_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY voice_jobs_by_project_owner
  ON public.voice_jobs
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = voice_jobs.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = voice_jobs.project_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY pipeline_runs_by_project_owner
  ON public.pipeline_runs
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = pipeline_runs.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = pipeline_runs.project_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY worker_service_audit_owner_select
  ON public.worker_service_audit
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = worker_service_audit.project_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY assets_by_project_owner
  ON public.assets
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = assets.project_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = assets.project_id AND p.user_id = auth.uid()
    )
  );

INSERT INTO public.projects (id, user_id, title, status)
VALUES
  (
    '11111111-1111-1111-1111-111111111111',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'Owned by A',
    'draft'
  ),
  (
    '22222222-2222-2222-2222-222222222222',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'Owned by B',
    'draft'
  );

ALTER TABLE public.projects FORCE ROW LEVEL SECURITY;
ALTER TABLE public.scenes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.render_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.voice_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.worker_service_audit FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assets FORCE ROW LEVEL SECURITY;
