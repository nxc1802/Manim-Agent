-- ==========================================
-- Manim Agent - Consolidated Database Schema
-- Location: supabase/migrations/20260219000000_init_schema.sql
-- ==========================================

-- ------------------------------------------
-- 1. Helper Functions & Extensions
-- ------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- ------------------------------------------
-- 2. Core Tables
-- ------------------------------------------

-- PROJECTS
CREATE TABLE public.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  source_language TEXT DEFAULT 'en',
  target_scenes INTEGER,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'processing', 'completed', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_user_id ON public.projects (user_id);
CREATE INDEX idx_projects_status ON public.projects (status);
CREATE INDEX idx_projects_updated_at ON public.projects (updated_at DESC);

CREATE TRIGGER trg_projects_updated_at
  BEFORE UPDATE ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- SCENES
CREATE TABLE public.scenes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_order INTEGER NOT NULL,
  storyboard_status TEXT NOT NULL DEFAULT 'missing' CHECK (storyboard_status IN ('missing', 'pending_review', 'approved')),
  storyboard_text TEXT,
  voice_script TEXT,
  plan_status TEXT NOT NULL DEFAULT 'missing' CHECK (plan_status IN ('missing', 'pending_review', 'approved')),
  voice_script_status TEXT NOT NULL DEFAULT 'missing' CHECK (voice_script_status IN ('missing', 'pending_review', 'approved')),
  planner_output JSONB,
  sync_segments JSONB,
  manim_code TEXT,
  manim_code_version INTEGER NOT NULL DEFAULT 1,
  audio_url TEXT,
  timestamps JSONB,
  duration_seconds NUMERIC(10, 3),
  review_loop_status TEXT NOT NULL DEFAULT 'idle' CHECK (review_loop_status IN ('idle', 'running', 'completed', 'hitl_pending', 'failed')),
  scene_dsl JSONB,
  scene_dsl_version INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, scene_order)
);

CREATE INDEX idx_scenes_project_id ON public.scenes (project_id);
CREATE INDEX idx_scenes_project_order ON public.scenes (project_id, scene_order);
CREATE INDEX idx_scenes_plan_status ON public.scenes (plan_status);
CREATE INDEX idx_scenes_voice_script_status ON public.scenes (voice_script_status);

CREATE TRIGGER trg_scenes_updated_at
  BEFORE UPDATE ON public.scenes
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- RENDER JOBS
CREATE TABLE public.render_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE SET NULL,
  job_type TEXT NOT NULL CHECK (job_type IN ('preview', 'full')),
  render_quality TEXT CHECK (render_quality IN ('720p', '1080p', '4k')),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'rendering', 'completed', 'failed', 'cancelled')),
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


-- VOICE JOBS
CREATE TABLE public.voice_jobs (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'synthesizing', 'completed', 'failed', 'cancelled')),
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


-- ASSETS
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


-- PIPELINE RUNS
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

CREATE INDEX idx_pipeline_runs_project ON public.pipeline_runs (project_id);
CREATE INDEX idx_pipeline_runs_scene ON public.pipeline_runs (scene_id);
CREATE INDEX idx_pipeline_runs_created ON public.pipeline_runs (created_at DESC);


-- SCENE CODE HISTORY
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


-- AGENT LOGS
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


-- WORKER SERVICE AUDIT
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


-- PIPELINE EVENTS
CREATE TABLE public.pipeline_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID REFERENCES public.scenes (id) ON DELETE CASCADE,
  component TEXT NOT NULL,
  phase TEXT NOT NULL,
  message TEXT NOT NULL,
  details JSONB DEFAULT '{}'::jsonb,
  trace_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ARTIFACT VERSIONS
CREATE TABLE public.artifact_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL,
  entity_id UUID NOT NULL,
  version INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  content JSONB NOT NULL,
  parent_version INTEGER,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_type, entity_id, version)
);

CREATE INDEX idx_artifact_versions_entity ON public.artifact_versions (entity_type, entity_id);


-- AI RUNS (HITL State)
CREATE TABLE public.ai_runs (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'waiting_for_human', 'completed', 'failed', 'cancelled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_runs_project_created ON public.ai_runs (project_id, created_at DESC);
CREATE INDEX idx_ai_runs_scene_created ON public.ai_runs (scene_id, created_at DESC);

CREATE TRIGGER trg_ai_runs_updated_at
  BEFORE UPDATE ON public.ai_runs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- AI STEPS (HITL State)
CREATE TABLE public.ai_steps (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES public.ai_runs (id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES public.projects (id) ON DELETE CASCADE,
  scene_id UUID NOT NULL REFERENCES public.scenes (id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL CHECK (sequence >= 1),
  kind TEXT NOT NULL CHECK (kind IN ('director', 'planner', 'scene_designer', 'builder', 'code_reviewer')),
  status TEXT NOT NULL CHECK (status IN ('queued', 'generating', 'pending_review', 'approved', 'rejected', 'failed')),
  input JSONB NOT NULL DEFAULT '{}'::jsonb,
  draft_output JSONB,
  final_output JSONB,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_steps_run_sequence ON public.ai_steps (run_id, sequence);
CREATE INDEX idx_ai_steps_project_status ON public.ai_steps (project_id, status);

CREATE TRIGGER trg_ai_steps_updated_at
  BEFORE UPDATE ON public.ai_steps
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ------------------------------------------
-- 3. Row Level Security (RLS) Policies
-- ------------------------------------------

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.render_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.worker_service_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scene_code_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.artifact_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_steps ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.projects FORCE ROW LEVEL SECURITY;
ALTER TABLE public.scenes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.render_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.voice_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assets FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.worker_service_audit FORCE ROW LEVEL SECURITY;
ALTER TABLE public.scene_code_history FORCE ROW LEVEL SECURITY;
ALTER TABLE public.agent_logs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_events FORCE ROW LEVEL SECURITY;
ALTER TABLE public.artifact_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE public.ai_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.ai_steps FORCE ROW LEVEL SECURITY;

-- Policies

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

CREATE POLICY pipeline_events_owner_all
  ON public.pipeline_events
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = pipeline_events.project_id AND p.user_id = auth.uid()
    )
  );

CREATE POLICY artifact_versions_policy ON public.artifact_versions
    FOR ALL
    USING (
        EXISTS (
            SELECT 1
            FROM public.scenes s
            JOIN public.projects p ON p.id = s.project_id
            WHERE s.id = artifact_versions.entity_id
              AND p.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.scenes s
            JOIN public.projects p ON p.id = s.project_id
            WHERE s.id = artifact_versions.entity_id
              AND p.user_id = auth.uid()
        )
    );

CREATE POLICY ai_runs_owner_all ON public.ai_runs
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY ai_steps_owner_all ON public.ai_steps
  FOR ALL
  USING (EXISTS (SELECT 1 FROM public.ai_runs r WHERE r.id = ai_steps.run_id AND r.user_id = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.ai_runs r WHERE r.id = ai_steps.run_id AND r.user_id = auth.uid()));

-- ------------------------------------------
-- 4. Realtime Broadcasting & Publications
-- ------------------------------------------

-- Enable Realtime for pipeline_events to broadcast agent events to the UI
ALTER PUBLICATION supabase_realtime ADD TABLE public.pipeline_events;

-- ------------------------------------------
-- 5. RPC Functions & APIs
-- ------------------------------------------

-- Dashboard stats calculator
CREATE OR REPLACE FUNCTION public.get_dashboard_stats(user_id_param UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    total_projects INTEGER;
    active_jobs INTEGER;
    total_tokens INTEGER;
    total_render_seconds NUMERIC;
BEGIN
    SELECT count(*) INTO total_projects FROM public.projects WHERE user_id = user_id_param;
    
    SELECT count(*) INTO active_jobs FROM public.render_jobs j
    JOIN public.projects p ON j.project_id = p.id
    WHERE p.user_id = user_id_param AND j.status IN ('queued', 'rendering');
    
    SELECT COALESCE(sum(total_tokens), 0) INTO total_tokens FROM public.pipeline_runs r
    JOIN public.projects p ON r.project_id = p.id
    WHERE p.user_id = user_id_param;
    
    SELECT COALESCE(sum(EXTRACT(EPOCH FROM (completed_at - started_at))), 0) INTO total_render_seconds FROM public.render_jobs j
    JOIN public.projects p ON j.project_id = p.id
    WHERE p.user_id = user_id_param AND j.status = 'completed' AND j.completed_at IS NOT NULL AND j.started_at IS NOT NULL;
    
    RETURN jsonb_build_object(
        'total_projects', total_projects,
        'active_jobs', active_jobs,
        'total_tokens_used', total_tokens,
        'total_render_time_hours', ROUND(total_render_seconds / 3600, 2)
    );
END;
$$;
