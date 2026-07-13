-- ==========================================
-- Manim Agent - User Settings Schema
-- Location: supabase/migrations/20260713000000_user_settings.sql
-- ==========================================

CREATE TABLE public.user_settings (
  user_id UUID PRIMARY KEY,
  theme TEXT NOT NULL DEFAULT 'dark' CHECK (theme IN ('dark', 'light')),
  language TEXT NOT NULL DEFAULT 'en',
  hitl_enabled BOOLEAN NOT NULL DEFAULT true,
  ai_agent_persona TEXT NOT NULL DEFAULT 'Professional Educator',
  template_selection TEXT NOT NULL DEFAULT 'Educational',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger for updated_at
CREATE TRIGGER trg_user_settings_updated_at
  BEFORE UPDATE ON public.user_settings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS Policies
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY user_settings_owner_all
  ON public.user_settings
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
