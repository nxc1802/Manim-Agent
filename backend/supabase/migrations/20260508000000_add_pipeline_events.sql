-- Add pipeline_events table for Supabase Realtime broadcasting
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

-- Enable RLS
ALTER TABLE public.pipeline_events ENABLE ROW LEVEL SECURITY;

-- Allow project owners to see their events
CREATE POLICY pipeline_events_owner_all
  ON public.pipeline_events
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = pipeline_events.project_id AND p.user_id = auth.uid()
    )
  );

-- Enable Realtime for this table
ALTER PUBLICATION supabase_realtime ADD TABLE public.pipeline_events;

-- Dashboard Stats RPC
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
