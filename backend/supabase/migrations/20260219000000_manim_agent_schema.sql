-- Manim Agent — consolidated schema (single migration for new Supabase projects).
-- Prerequisites: Apply via Supabase SQL Editor or `supabase db push`.

CREATE TABLE public.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL, -- Constraint relaxed to allow easier integration
  title TEXT NOT NULL,
  description TEXT,
  source_language TEXT DEFAULT 'en',
  target_scenes INTEGER,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'processing', 'completed', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_user_id ON public.projects (user_id);
CREATE INDEX idx_projects_status ON public.projects (status);
CREATE INDEX idx_projects_updated_at ON public.projects (updated_at DESC);

CREATE TABLE public.scenes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_order INTEGER NOT NULL,
  storyboard_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (storyboard_status IN ('missing', 'pending_review', 'approved')),
  storyboard_text TEXT,
  voice_script TEXT,
  plan_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (plan_status IN ('missing', 'pending_review', 'approved')),
  voice_script_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (voice_script_status IN ('missing', 'pending_review', 'approved')),
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
CREATE INDEX idx_scenes_project_order ON public.scenes (project_id, scene_order);
CREATE INDEX idx_scenes_plan_status ON public.scenes (plan_status);
CREATE INDEX idx_scenes_voice_script_status ON public.scenes (voice_script_status);

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
CREATE INDEX idx_render_jobs_status ON public.render_jobs (status);
CREATE INDEX idx_render_jobs_created ON public.render_jobs (created_at DESC);
CREATE INDEX idx_render_jobs_scene ON public.render_jobs (scene_id);

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
CREATE INDEX idx_voice_jobs_scene ON public.voice_jobs (scene_id);
CREATE INDEX idx_voice_jobs_status ON public.voice_jobs (status);
CREATE INDEX idx_voice_jobs_created ON public.voice_jobs (created_at DESC);

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
CREATE INDEX idx_assets_scene ON public.assets (scene_id);
CREATE INDEX idx_assets_type ON public.assets (file_type);

CREATE TABLE public.pipeline_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  report JSONB NOT NULL DEFAULT '{}'::jsonb,
  prompt_tokens INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  total_tokens INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.scene_code_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  run_id UUID REFERENCES public.pipeline_runs (id) ON DELETE SET NULL,
  version INTEGER NOT NULL,
  round_idx INTEGER,
  manim_code TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scene_code_history_scene_id ON public.scene_code_history (scene_id);
CREATE INDEX idx_scene_code_history_run_id ON public.scene_code_history (run_id);

CREATE TABLE public.agent_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES public.pipeline_runs (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE CASCADE,
  round_idx INTEGER,
  agent_name TEXT NOT NULL,
  prompt_version TEXT,
  system_prompt TEXT,
  user_prompt TEXT,
  output_text TEXT,
  error TEXT,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_logs_run_id ON public.agent_logs (run_id);
CREATE INDEX idx_agent_logs_scene_id ON public.agent_logs (scene_id);

CREATE INDEX idx_pipeline_runs_project ON public.pipeline_runs (project_id);
CREATE INDEX idx_pipeline_runs_scene ON public.pipeline_runs (scene_id);
CREATE INDEX idx_pipeline_runs_created ON public.pipeline_runs (created_at DESC);

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
CREATE INDEX idx_worker_audit_scene ON public.worker_service_audit (scene_id);

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
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.worker_service_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scene_code_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_logs ENABLE ROW LEVEL SECURITY;

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

CREATE POLICY scene_code_history_by_project_owner
  ON public.scene_code_history
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      JOIN public.scenes s ON s.project_id = p.id
      WHERE s.id = scene_code_history.scene_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      JOIN public.scenes s ON s.project_id = p.id
      WHERE s.id = scene_code_history.scene_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY agent_logs_by_project_owner
  ON public.agent_logs
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      JOIN public.scenes s ON s.project_id = p.id
      WHERE s.id = agent_logs.scene_id AND p.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      JOIN public.scenes s ON s.project_id = p.id
      WHERE s.id = agent_logs.scene_id AND p.user_id = auth.uid()
    )
  );

ALTER TABLE public.projects FORCE ROW LEVEL SECURITY;
ALTER TABLE public.scenes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.render_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.voice_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assets FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.worker_service_audit FORCE ROW LEVEL SECURITY;
ALTER TABLE public.scene_code_history FORCE ROW LEVEL SECURITY;
ALTER TABLE public.agent_logs FORCE ROW LEVEL SECURITY;
