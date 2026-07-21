-- Production hardening for the Backend-only Supabase access model.
--
-- This is the final delta in the ordered migration chain, not a standalone
-- bootstrap script. Apply every backend/supabase/migrations/*.sql file in
-- timestamp order through Supabase CLI; never paste this file by itself into
-- the SQL Editor.
--
-- The browser uses Supabase Auth, but it never reads or writes application
-- tables directly. Backend is the sole Data API client and authenticates with
-- service_role. RLS remains enabled as defense in depth if table grants change.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Align active/retained tables with the strict application contracts.
-- ---------------------------------------------------------------------------

-- ProjectCreate defaults to Vietnamese and Project requires a non-null string.
-- Older schemas allowed an explicitly-null source_language, which makes a
-- PostgREST row fail strict Pydantic validation. Repair only missing values.
UPDATE public.projects
SET source_language = 'vi'
WHERE source_language IS NULL;

ALTER TABLE public.projects
  ALTER COLUMN source_language SET DEFAULT 'vi',
  ALTER COLUMN source_language SET NOT NULL;

ALTER TABLE public.render_jobs
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.render_jobs
  DROP CONSTRAINT IF EXISTS render_jobs_job_type_check;

ALTER TABLE public.render_jobs
  ADD CONSTRAINT render_jobs_job_type_check
  CHECK (job_type IN ('preview', 'full', 'full_project'))
  NOT VALID;

ALTER TABLE public.render_jobs
  DROP CONSTRAINT IF EXISTS render_jobs_render_quality_check;

ALTER TABLE public.render_jobs
  ADD CONSTRAINT render_jobs_render_quality_check
  CHECK (render_quality IN ('480p', '720p', '1080p', '4k'))
  NOT VALID;

-- ---------------------------------------------------------------------------
-- 2. Add integrity constraints without rejecting unknown legacy rows.
--
-- NOT VALID foreign keys protect every new write immediately. The validation
-- block below validates each constraint when existing rows are clean and emits
-- a warning, rather than aborting the deployment, when legacy repair is needed.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'projects_id_user_id_key'
      AND conrelid = 'public.projects'::regclass
  ) THEN
    ALTER TABLE public.projects
      ADD CONSTRAINT projects_id_user_id_key UNIQUE (id, user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'scenes_id_project_id_key'
      AND conrelid = 'public.scenes'::regclass
  ) THEN
    ALTER TABLE public.scenes
      ADD CONSTRAINT scenes_id_project_id_key UNIQUE (id, project_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_runs_id_project_id_key'
      AND conrelid = 'public.ai_runs'::regclass
  ) THEN
    ALTER TABLE public.ai_runs
      ADD CONSTRAINT ai_runs_id_project_id_key UNIQUE (id, project_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_runs_id_scene_id_key'
      AND conrelid = 'public.ai_runs'::regclass
  ) THEN
    ALTER TABLE public.ai_runs
      ADD CONSTRAINT ai_runs_id_scene_id_key UNIQUE (id, scene_id);
  END IF;
END
$$;

-- This check originally lived only in an older lifecycle migration. A hosted
-- database may have that version recorded from before the check was added, so
-- production hardening must converge the catalog instead of assuming the
-- historical file was replayed byte-for-byte. A same-name/different-definition
-- constraint is unsafe drift and must fail explicitly.
DO $$
DECLARE
  existing_type "char";
  existing_expression TEXT;
BEGIN
  SELECT
    constraint_record.contype,
    pg_get_expr(constraint_record.conbin, constraint_record.conrelid)
  INTO existing_type, existing_expression
  FROM pg_constraint AS constraint_record
  WHERE constraint_record.conname = 'scenes_scene_order_positive'
    AND constraint_record.conrelid = 'public.scenes'::regclass;

  IF NOT FOUND THEN
    ALTER TABLE public.scenes
      ADD CONSTRAINT scenes_scene_order_positive
      CHECK (scene_order >= 1) NOT VALID;
  ELSIF existing_type <> 'c'
     OR regexp_replace(existing_expression, '[[:space:]()]', '', 'g') <> 'scene_order>=1' THEN
    RAISE EXCEPTION
      'Schema drift: public.scenes constraint scenes_scene_order_positive has unexpected definition: %',
      COALESCE(existing_expression, '<non-check constraint>');
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'projects_user_id_auth_fkey'
      AND conrelid = 'public.projects'::regclass
  ) THEN
    ALTER TABLE public.projects
      ADD CONSTRAINT projects_user_id_auth_fkey
      FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
      NOT VALID;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'user_settings_user_id_auth_fkey'
      AND conrelid = 'public.user_settings'::regclass
  ) THEN
    ALTER TABLE public.user_settings
      ADD CONSTRAINT user_settings_user_id_auth_fkey
      FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
      NOT VALID;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_runs_user_id_auth_fkey'
      AND conrelid = 'public.ai_runs'::regclass
  ) THEN
    ALTER TABLE public.ai_runs
      ADD CONSTRAINT ai_runs_user_id_auth_fkey
      FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
      NOT VALID;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_runs_project_owner_fkey'
      AND conrelid = 'public.ai_runs'::regclass
  ) THEN
    ALTER TABLE public.ai_runs
      ADD CONSTRAINT ai_runs_project_owner_fkey
      FOREIGN KEY (project_id, user_id)
      REFERENCES public.projects (id, user_id) ON DELETE CASCADE
      NOT VALID;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_runs_scene_project_fkey'
      AND conrelid = 'public.ai_runs'::regclass
  ) THEN
    ALTER TABLE public.ai_runs
      ADD CONSTRAINT ai_runs_scene_project_fkey
      FOREIGN KEY (scene_id, project_id)
      REFERENCES public.scenes (id, project_id) ON DELETE CASCADE
      NOT VALID;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_steps_run_project_fkey'
      AND conrelid = 'public.ai_steps'::regclass
  ) THEN
    ALTER TABLE public.ai_steps
      ADD CONSTRAINT ai_steps_run_project_fkey
      FOREIGN KEY (run_id, project_id)
      REFERENCES public.ai_runs (id, project_id) ON DELETE CASCADE
      NOT VALID;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_steps_run_scene_fkey'
      AND conrelid = 'public.ai_steps'::regclass
  ) THEN
    ALTER TABLE public.ai_steps
      ADD CONSTRAINT ai_steps_run_scene_fkey
      FOREIGN KEY (run_id, scene_id)
      REFERENCES public.ai_runs (id, scene_id) ON DELETE CASCADE
      NOT VALID;
  END IF;
END
$$;

-- Serialize the duplicate check with application writes. A dirty legacy table
-- remains deployable, but receives a warning and must be repaired before the
-- post-deployment validation gate can pass.
LOCK TABLE public.ai_steps IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ai_steps_run_sequence_key'
      AND conrelid = 'public.ai_steps'::regclass
  ) THEN
    IF EXISTS (
      SELECT 1
      FROM public.ai_steps
      GROUP BY run_id, sequence
      HAVING COUNT(*) > 1
    ) THEN
      RAISE WARNING
        'Skipped ai_steps_run_sequence_key: duplicate (run_id, sequence) rows require repair';
    ELSE
      ALTER TABLE public.ai_steps
        ADD CONSTRAINT ai_steps_run_sequence_key UNIQUE (run_id, sequence);
    END IF;
  END IF;
END
$$;

DO $$
DECLARE
  target RECORD;
BEGIN
  FOR target IN
    SELECT *
    FROM (VALUES
      ('public.projects'::regclass, 'projects_user_id_auth_fkey'),
      ('public.user_settings'::regclass, 'user_settings_user_id_auth_fkey'),
      ('public.ai_runs'::regclass, 'ai_runs_user_id_auth_fkey'),
      ('public.ai_runs'::regclass, 'ai_runs_project_owner_fkey'),
      ('public.ai_runs'::regclass, 'ai_runs_scene_project_fkey'),
      ('public.ai_steps'::regclass, 'ai_steps_run_project_fkey'),
      ('public.ai_steps'::regclass, 'ai_steps_run_scene_fkey'),
      ('public.scenes'::regclass, 'scenes_scene_order_positive'),
      ('public.render_jobs'::regclass, 'render_jobs_job_type_check'),
      ('public.render_jobs'::regclass, 'render_jobs_render_quality_check')
    ) AS constraints_to_validate(table_name, constraint_name)
  LOOP
    BEGIN
      EXECUTE format(
        'ALTER TABLE %s VALIDATE CONSTRAINT %I',
        target.table_name,
        target.constraint_name
      );
    EXCEPTION
      WHEN foreign_key_violation OR check_violation THEN
        RAISE WARNING
          'Constraint %.% remains NOT VALID because legacy rows require repair',
          target.table_name,
          target.constraint_name;
    END;
  END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Index foreign keys and the actual Backend query shapes.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_projects_user_created
  ON public.projects (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_runs_user_id
  ON public.ai_runs (user_id);
CREATE INDEX IF NOT EXISTS idx_ai_steps_scene_id
  ON public.ai_steps (scene_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_project_created
  ON public.pipeline_events (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_scene_id
  ON public.pipeline_events (scene_id);
CREATE INDEX IF NOT EXISTS idx_worker_audit_render_job_id
  ON public.worker_service_audit (render_job_id);
CREATE INDEX IF NOT EXISTS idx_worker_audit_voice_job_id
  ON public.worker_service_audit (voice_job_id);

-- This index duplicates the index already created by UNIQUE(project_id,
-- scene_order). Removing it does not remove the uniqueness constraint.
DROP INDEX IF EXISTS public.idx_scenes_project_order;

-- ---------------------------------------------------------------------------
-- 4. Restrict the public Data API to Backend service_role only.
--
-- Explicit grants are required by current Supabase projects. Revoke first so
-- projects created under older permissive defaults converge to the same state.
-- ---------------------------------------------------------------------------

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES
  FROM anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE USAGE, SELECT ON SEQUENCES
  FROM anon, authenticated, service_role;

-- PostgreSQL's built-in EXECUTE grant to PUBLIC is a global default and cannot
-- be revoked by a per-schema default ACL. Revoke that global function default,
-- then remove Supabase's explicit public-schema application-role defaults.
-- Functions intended as RPCs must opt in with a reviewed explicit GRANT.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
  REVOKE EXECUTE ON FUNCTIONS
  FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS
  FROM anon, authenticated, service_role;

DO $$
DECLARE
  function_to_restrict REGPROCEDURE;
BEGIN
  FOR function_to_restrict IN
    SELECT function_record.oid::regprocedure
    FROM pg_proc AS function_record
    JOIN pg_namespace AS namespace_record
      ON namespace_record.oid = function_record.pronamespace
    WHERE namespace_record.nspname = 'public'
  LOOP
    EXECUTE format(
      'REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, anon, authenticated, service_role',
      function_to_restrict
    );
  END LOOP;
END
$$;

DO $$
DECLARE
  table_record RECORD;
BEGIN
  FOR table_record IN
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename = ANY (ARRAY[
        'projects',
        'scenes',
        'render_jobs',
        'voice_jobs',
        'assets',
        'pipeline_runs',
        'scene_code_history',
        'agent_logs',
        'worker_service_audit',
        'pipeline_events',
        'artifact_versions',
        'ai_runs',
        'ai_steps',
        'user_settings'
      ])
  LOOP
    EXECUTE format(
      'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated, service_role',
      table_record.tablename
    );
  END LOOP;
END
$$;

GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.projects,
  public.scenes,
  public.ai_runs,
  public.ai_steps,
  public.user_settings
TO service_role;

-- The five active tables use UUID keys rather than sequences. The nine other
-- public tables are retained only for migration/data-retention compatibility;
-- no current Backend or worker adapter accesses them, so they intentionally
-- remain unavailable to service_role.

-- ---------------------------------------------------------------------------
-- 5. Replace permissive legacy policies with explicit authenticated policies.
--
-- authenticated currently has no table privileges. These policies are defense
-- in depth and remain correct if a future feature deliberately grants access.
-- Legacy tables keep RLS enabled but have no policies, so they are deny-by-
-- default even if a grant is accidentally reintroduced.
-- ---------------------------------------------------------------------------

-- Remove policy drift created outside migrations. Backend-only access means no
-- legacy table policy is part of the supported public contract.
DO $$
DECLARE
  policy_to_drop RECORD;
BEGIN
  FOR policy_to_drop IN
    SELECT schemaname, tablename, policyname
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = ANY (ARRAY[
        'projects',
        'scenes',
        'render_jobs',
        'voice_jobs',
        'assets',
        'pipeline_runs',
        'scene_code_history',
        'agent_logs',
        'worker_service_audit',
        'pipeline_events',
        'artifact_versions',
        'ai_runs',
        'ai_steps',
        'user_settings'
      ])
  LOOP
    EXECUTE format(
      'DROP POLICY %I ON %I.%I',
      policy_to_drop.policyname,
      policy_to_drop.schemaname,
      policy_to_drop.tablename
    );
  END LOOP;
END
$$;

CREATE POLICY projects_owner_all
  ON public.projects
  FOR ALL
  TO authenticated
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id);

CREATE POLICY scenes_by_project_owner
  ON public.scenes
  FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.projects AS project
      WHERE project.id = scenes.project_id
        AND project.user_id = (SELECT auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM public.projects AS project
      WHERE project.id = scenes.project_id
        AND project.user_id = (SELECT auth.uid())
    )
  );

CREATE POLICY ai_runs_owner_all
  ON public.ai_runs
  FOR ALL
  TO authenticated
  USING (
    user_id = (SELECT auth.uid())
    AND EXISTS (
      SELECT 1
      FROM public.projects AS project
      WHERE project.id = ai_runs.project_id
        AND project.user_id = (SELECT auth.uid())
    )
    AND (
      scene_id IS NULL
      OR EXISTS (
        SELECT 1
        FROM public.scenes AS scene
        WHERE scene.id = ai_runs.scene_id
          AND scene.project_id = ai_runs.project_id
      )
    )
  )
  WITH CHECK (
    user_id = (SELECT auth.uid())
    AND EXISTS (
      SELECT 1
      FROM public.projects AS project
      WHERE project.id = ai_runs.project_id
        AND project.user_id = (SELECT auth.uid())
    )
    AND (
      scene_id IS NULL
      OR EXISTS (
        SELECT 1
        FROM public.scenes AS scene
        WHERE scene.id = ai_runs.scene_id
          AND scene.project_id = ai_runs.project_id
      )
    )
  );

CREATE POLICY ai_steps_owner_all
  ON public.ai_steps
  FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.ai_runs AS run
      WHERE run.id = ai_steps.run_id
        AND run.project_id = ai_steps.project_id
        AND run.scene_id IS NOT DISTINCT FROM ai_steps.scene_id
        AND run.user_id = (SELECT auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM public.ai_runs AS run
      WHERE run.id = ai_steps.run_id
        AND run.project_id = ai_steps.project_id
        AND run.scene_id IS NOT DISTINCT FROM ai_steps.scene_id
        AND run.user_id = (SELECT auth.uid())
    )
  );

CREATE POLICY user_settings_owner_all
  ON public.user_settings
  FOR ALL
  TO authenticated
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- 6. Provision the Backend-owned render bucket using Supabase's documented SQL
-- bucket interface. No storage.objects policies are needed: only service_role
-- uploads and signs reads. The conditional keeps raw PostgreSQL validation and
-- self-hosted installs without Storage deployable.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF to_regclass('storage.buckets') IS NULL THEN
    RAISE WARNING 'Supabase Storage is unavailable; skipped videos bucket provisioning';
  ELSE
    INSERT INTO storage.buckets (
      id,
      name,
      public,
      file_size_limit,
      allowed_mime_types
    )
    VALUES (
      'videos',
      'videos',
      FALSE,
      1073741824,
      ARRAY['video/mp4']::TEXT[]
    )
    ON CONFLICT (id) DO UPDATE
    SET
      name = EXCLUDED.name,
      public = FALSE,
      file_size_limit = EXCLUDED.file_size_limit,
      allowed_mime_types = EXCLUDED.allowed_mime_types;
  END IF;
END
$$;

NOTIFY pgrst, 'reload schema';

COMMIT;
