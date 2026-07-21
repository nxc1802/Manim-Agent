#!/usr/bin/env bash
set -Eeuo pipefail

export LC_ALL=C

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
migration_dir="$script_dir/migrations"
postmigration_gate="$script_dir/postmigration_gate.sql"
postgres_image="${POSTGRES_IMAGE:-postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193}"
validation_container="manim-schema-validation-$$"
container_created=false

cleanup() {
  if [[ "$container_created" == true ]]; then
    docker rm -f "$validation_container" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for migration validation" >&2
  exit 1
fi

migrations=("$migration_dir"/*.sql)
if [[ ! -e "${migrations[0]}" ]]; then
  echo "no migrations found in $migration_dir" >&2
  exit 1
fi

if [[ "$(basename -- "${migrations[0]}")" != "20260219000000_init_schema.sql" ]]; then
  echo "unexpected first migration: $(basename -- "${migrations[0]}")" >&2
  exit 1
fi

production_migration="$migration_dir/20260721000000_production_hardening.sql"
if [[ ! -f "$production_migration" ]]; then
  echo "production hardening migration is missing: $production_migration" >&2
  exit 1
fi
if [[ ! -s "$postmigration_gate" ]]; then
  echo "post-migration gate SQL is missing: $postmigration_gate" >&2
  exit 1
fi

docker run -d \
  --name "$validation_container" \
  -e POSTGRES_PASSWORD=validation-only \
  "$postgres_image" \
  -c wal_level=logical >/dev/null
container_created=true

ready=false
for _attempt in {1..60}; do
  if docker exec "$validation_container" pg_isready -U postgres >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 0.5
done

if [[ "$ready" != true ]]; then
  docker logs "$validation_container" >&2
  echo "PostgreSQL validation container did not become ready" >&2
  exit 1
fi

psql_db() {
  local database="$1"
  shift
  docker exec -i "$validation_container" \
    psql -X -q -v ON_ERROR_STOP=1 -U postgres -d "$database" "$@"
}

bootstrap_supabase_stubs() {
  local database="$1"
  psql_db "$database" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END
$$;

CREATE SCHEMA auth;
CREATE TABLE auth.users (
  id UUID PRIMARY KEY
);
CREATE FUNCTION auth.uid()
RETURNS UUID
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::UUID
$$;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;

CREATE SCHEMA storage;
CREATE TABLE storage.buckets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  public BOOLEAN NOT NULL DEFAULT FALSE,
  file_size_limit BIGINT,
  allowed_mime_types TEXT[]
);

CREATE PUBLICATION supabase_realtime;

-- Reproduce the permissive default privileges used by older Supabase projects.
-- The production hardening migration must converge these to Backend-only access.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
  TO anon, authenticated, service_role;
SQL
}

apply_migration() {
  local database="$1"
  local migration="$2"
  printf 'apply %-24s %s\n' "$database" "$(basename -- "$migration")"
  psql_db "$database" < "$migration"
}

bootstrap_supabase_stubs postgres
for migration in "${migrations[@]}"; do
  apply_migration postgres "$migration"
done

psql_db postgres <<'SQL'
DO $$
DECLARE
  table_name TEXT;
  privilege_name TEXT;
  role_name TEXT;
  active_tables CONSTANT TEXT[] := ARRAY[
    'public.projects',
    'public.scenes',
    'public.ai_runs',
    'public.ai_steps',
    'public.user_settings'
  ];
  legacy_tables CONSTANT TEXT[] := ARRAY[
    'public.render_jobs',
    'public.voice_jobs',
    'public.assets',
    'public.pipeline_runs',
    'public.scene_code_history',
    'public.agent_logs',
    'public.worker_service_audit',
    'public.pipeline_events',
    'public.artifact_versions'
  ];
  all_tables CONSTANT TEXT[] := ARRAY[
    'public.projects',
    'public.scenes',
    'public.ai_runs',
    'public.ai_steps',
    'public.user_settings',
    'public.render_jobs',
    'public.voice_jobs',
    'public.assets',
    'public.pipeline_runs',
    'public.scene_code_history',
    'public.agent_logs',
    'public.worker_service_audit',
    'public.pipeline_events',
    'public.artifact_versions'
  ];
BEGIN
  IF (
    SELECT COUNT(*)
    FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relkind = 'r'
      AND relation.relname = ANY (ARRAY[
        'projects', 'scenes', 'render_jobs', 'voice_jobs', 'assets',
        'pipeline_runs', 'scene_code_history', 'agent_logs',
        'worker_service_audit', 'pipeline_events', 'artifact_versions',
        'ai_runs', 'ai_steps', 'user_settings'
      ])
      AND relation.relrowsecurity
      AND relation.relforcerowsecurity
  ) <> 14 THEN
    RAISE EXCEPTION 'expected all 14 application tables to have ENABLE + FORCE RLS';
  END IF;

  FOREACH table_name IN ARRAY active_tables LOOP
    FOREACH privilege_name IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
      IF NOT has_table_privilege('service_role', table_name, privilege_name) THEN
        RAISE EXCEPTION 'service_role lacks % on %', privilege_name, table_name;
      END IF;
      IF has_table_privilege('anon', table_name, privilege_name)
         OR has_table_privilege('authenticated', table_name, privilege_name) THEN
        RAISE EXCEPTION 'browser role unexpectedly has % on %', privilege_name, table_name;
      END IF;
    END LOOP;
  END LOOP;

  FOREACH table_name IN ARRAY legacy_tables LOOP
    FOREACH privilege_name IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
      IF has_table_privilege('anon', table_name, privilege_name)
         OR has_table_privilege('authenticated', table_name, privilege_name)
         OR has_table_privilege('service_role', table_name, privilege_name) THEN
        RAISE EXCEPTION 'legacy table % unexpectedly grants %', table_name, privilege_name;
      END IF;
    END LOOP;
  END LOOP;

  -- Exact ACL convergence: no application role receives DDL-like table rights,
  -- including on the five active tables.
  FOREACH table_name IN ARRAY all_tables LOOP
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
      FOREACH privilege_name IN ARRAY ARRAY['TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
        IF has_table_privilege(role_name, table_name, privilege_name) THEN
          RAISE EXCEPTION '% unexpectedly has % on %', role_name, privilege_name, table_name;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;

  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF has_function_privilege(role_name, 'public.set_updated_at()', 'EXECUTE') THEN
      RAISE EXCEPTION '% unexpectedly executes public.set_updated_at()', role_name;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1
    FROM pg_proc AS function_record
    JOIN pg_namespace AS namespace_record
      ON namespace_record.oid = function_record.pronamespace
    CROSS JOIN (VALUES ('anon'), ('authenticated'), ('service_role')) AS app_role(role_name)
    WHERE namespace_record.nspname = 'public'
      AND has_function_privilege(
        app_role.role_name,
        function_record.oid,
        'EXECUTE'
      )
  ) THEN
    RAISE EXCEPTION 'an application role can execute a public-schema function';
  END IF;

  IF (
    SELECT COUNT(*) FROM pg_policies WHERE schemaname = 'public'
  ) <> 5 THEN
    RAISE EXCEPTION 'expected exactly five defense-in-depth RLS policies';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND roles <> ARRAY['authenticated']::NAME[]
  ) THEN
    RAISE EXCEPTION 'every application RLS policy must target authenticated explicitly';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace
      AND NOT convalidated
  ) THEN
    RAISE EXCEPTION 'clean replay left an unvalidated public constraint';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint AS constraint_record
    WHERE constraint_record.conrelid = 'public.scenes'::regclass
      AND constraint_record.conname = 'scenes_scene_order_positive'
      AND constraint_record.contype = 'c'
      AND constraint_record.convalidated
      AND regexp_replace(
        pg_get_expr(constraint_record.conbin, constraint_record.conrelid),
        '[[:space:]()]',
        '',
        'g'
      ) = 'scene_order>=1'
  ) THEN
    RAISE EXCEPTION 'scenes_scene_order_positive is missing, invalid, or has drifted';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.ai_steps'::regclass
      AND conname = 'ai_steps_run_sequence_key'
      AND contype = 'u'
  ) THEN
    RAISE EXCEPTION 'ai_steps(run_id, sequence) is not unique';
  END IF;

  IF to_regclass('public.idx_projects_user_created') IS NULL
     OR to_regclass('public.idx_ai_runs_user_id') IS NULL
     OR to_regclass('public.idx_ai_steps_scene_id') IS NULL
     OR to_regclass('public.idx_pipeline_events_project_created') IS NULL
     OR to_regclass('public.idx_pipeline_events_scene_id') IS NULL
     OR to_regclass('public.idx_worker_audit_render_job_id') IS NULL
     OR to_regclass('public.idx_worker_audit_voice_job_id') IS NULL THEN
    RAISE EXCEPTION 'one or more production indexes are missing';
  END IF;

  IF to_regclass('public.idx_scenes_project_order') IS NOT NULL THEN
    RAISE EXCEPTION 'redundant idx_scenes_project_order still exists';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns AS column_definition
    WHERE column_definition.table_schema = 'public'
      AND column_definition.table_name = 'render_jobs'
      AND column_definition.column_name = 'metadata'
      AND column_definition.is_nullable = 'NO'
  ) THEN
    RAISE EXCEPTION 'render_jobs.metadata is missing or nullable';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.render_jobs'::regclass
      AND conname = 'render_jobs_job_type_check'
      AND pg_get_constraintdef(oid) LIKE '%full_project%'
  ) THEN
    RAISE EXCEPTION 'render_jobs job_type does not support full_project';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.render_jobs'::regclass
      AND conname = 'render_jobs_render_quality_check'
      AND pg_get_constraintdef(oid) LIKE '%480p%'
  ) THEN
    RAISE EXCEPTION 'render_jobs render_quality does not support 480p';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.ai_steps'::regclass
      AND conname = 'ai_steps_kind_check'
      AND pg_get_constraintdef(oid) LIKE '%idea_sketcher%'
      AND pg_get_constraintdef(oid) LIKE '%storyboarder%'
      AND pg_get_constraintdef(oid) LIKE '%visual_reviewer%'
  ) THEN
    RAISE EXCEPTION 'ai_steps kind constraint is not the required superset';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM storage.buckets
    WHERE id = 'videos'
      AND name = 'videos'
      AND public = FALSE
      AND file_size_limit = 1073741824
      AND allowed_mime_types = ARRAY['video/mp4']::TEXT[]
  ) THEN
    RAISE EXCEPTION 'private videos bucket is not provisioned correctly';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns AS column_definition
    WHERE column_definition.table_schema = 'public'
      AND column_definition.table_name = 'projects'
      AND column_definition.column_name = 'source_language'
      AND (
        column_definition.is_nullable <> 'NO'
        OR column_definition.column_default IS DISTINCT FROM '''vi''::text'
      )
  ) OR NOT EXISTS (
    SELECT 1
    FROM information_schema.columns AS column_definition
    WHERE column_definition.table_schema = 'public'
      AND column_definition.table_name = 'projects'
      AND column_definition.column_name = 'source_language'
  ) THEN
    RAISE EXCEPTION 'projects.source_language is not aligned with the strict Project contract';
  END IF;
END
$$;

-- Prove the default function ACL is fail-closed for future migrations too.
CREATE FUNCTION public.validation_default_acl_probe()
RETURNS INTEGER
LANGUAGE sql
AS 'SELECT 1';

DO $$
DECLARE
  role_name TEXT;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF has_function_privilege(
      role_name,
      'public.validation_default_acl_probe()',
      'EXECUTE'
    ) THEN
      RAISE EXCEPTION '% unexpectedly executes a new public function', role_name;
    END IF;
  END LOOP;
END
$$;

DROP FUNCTION public.validation_default_acl_probe();

-- Exercise every runtime table operation as the real Data API database role.
-- This catches effective permission/RLS/trigger failures that catalog-only
-- has_table_privilege checks can miss.
BEGIN;
INSERT INTO auth.users (id)
VALUES ('00000000-0000-0000-0000-0000000000c0');
SET LOCAL ROLE service_role;
INSERT INTO public.projects (id, user_id, title)
VALUES (
  '00000000-0000-0000-0000-0000000000c1',
  '00000000-0000-0000-0000-0000000000c0',
  'service-role-crud'
);
INSERT INTO public.scenes (id, project_id, scene_order)
VALUES (
  '00000000-0000-0000-0000-0000000000c2',
  '00000000-0000-0000-0000-0000000000c1',
  1
);
INSERT INTO public.ai_runs (id, project_id, scene_id, user_id, status)
VALUES (
  '00000000-0000-0000-0000-0000000000c3',
  '00000000-0000-0000-0000-0000000000c1',
  '00000000-0000-0000-0000-0000000000c2',
  '00000000-0000-0000-0000-0000000000c0',
  'queued'
);
INSERT INTO public.ai_steps (
  id, run_id, project_id, scene_id, sequence, kind, status
) VALUES (
  '00000000-0000-0000-0000-0000000000c4',
  '00000000-0000-0000-0000-0000000000c3',
  '00000000-0000-0000-0000-0000000000c1',
  '00000000-0000-0000-0000-0000000000c2',
  1,
  'builder',
  'queued'
);
INSERT INTO public.user_settings (user_id)
VALUES ('00000000-0000-0000-0000-0000000000c0');

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM public.projects
    WHERE id = '00000000-0000-0000-0000-0000000000c1'
  ) OR NOT EXISTS (
    SELECT 1 FROM public.scenes
    WHERE id = '00000000-0000-0000-0000-0000000000c2'
  ) OR NOT EXISTS (
    SELECT 1 FROM public.ai_runs
    WHERE id = '00000000-0000-0000-0000-0000000000c3'
  ) OR NOT EXISTS (
    SELECT 1 FROM public.ai_steps
    WHERE id = '00000000-0000-0000-0000-0000000000c4'
  ) OR NOT EXISTS (
    SELECT 1 FROM public.user_settings
    WHERE user_id = '00000000-0000-0000-0000-0000000000c0'
  ) THEN
    RAISE EXCEPTION 'service_role could not read one or more active tables';
  END IF;
END
$$;

UPDATE public.projects SET title = 'service-role-updated'
WHERE id = '00000000-0000-0000-0000-0000000000c1';
UPDATE public.scenes SET storyboard_text = 'updated'
WHERE id = '00000000-0000-0000-0000-0000000000c2';
UPDATE public.ai_runs SET status = 'waiting_for_human'
WHERE id = '00000000-0000-0000-0000-0000000000c3';
UPDATE public.ai_steps SET status = 'generating'
WHERE id = '00000000-0000-0000-0000-0000000000c4';
UPDATE public.user_settings SET theme = 'light'
WHERE user_id = '00000000-0000-0000-0000-0000000000c0';

DELETE FROM public.ai_steps WHERE id = '00000000-0000-0000-0000-0000000000c4';
DELETE FROM public.ai_runs WHERE id = '00000000-0000-0000-0000-0000000000c3';
DELETE FROM public.scenes WHERE id = '00000000-0000-0000-0000-0000000000c2';
DELETE FROM public.projects WHERE id = '00000000-0000-0000-0000-0000000000c1';
DELETE FROM public.user_settings
WHERE user_id = '00000000-0000-0000-0000-0000000000c0';
RESET ROLE;
ROLLBACK;

-- Temporarily grant direct table access to prove the hardened policy rejects a
-- cross-tenant write. The transaction rolls back both fixtures and grants.
BEGIN;
INSERT INTO auth.users (id) VALUES
  ('00000000-0000-0000-0000-00000000000a'),
  ('00000000-0000-0000-0000-00000000000b');
INSERT INTO public.projects (id, user_id, title)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-00000000000b',
  'tenant-b'
);
INSERT INTO public.scenes (id, project_id, scene_order)
VALUES (
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  1
);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.projects, public.scenes, public.ai_runs, public.ai_steps
TO authenticated;
SET LOCAL ROLE authenticated;
SELECT set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-00000000000a',
  TRUE
);
DO $$
BEGIN
  BEGIN
    INSERT INTO public.ai_runs (
      id, project_id, scene_id, user_id, status, hitl_enabled
    ) VALUES (
      '00000000-0000-0000-0000-000000000003',
      '00000000-0000-0000-0000-000000000001',
      '00000000-0000-0000-0000-000000000002',
      '00000000-0000-0000-0000-00000000000b',
      'queued',
      TRUE
    );
    RAISE EXCEPTION 'cross-tenant ai_run insert unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege THEN
      NULL;
  END;
END
$$;
ROLLBACK;
SQL

gate_result="$(
  psql_db postgres -A -t -F '|' < "$postmigration_gate" | tr -d '[:space:]'
)"
if [[ "$gate_result" != "0|0|0|0|0|0|0|0" ]]; then
  echo "post-migration gate returned unexpected counts: $gate_result" >&2
  exit 1
fi

# Reproduce an upgrade from the baseline with durable idea/storyboard rows. This
# catches accidental enum narrowing that an empty database replay cannot detect.
psql_db postgres -c 'CREATE DATABASE manim_upgrade_fixture'
bootstrap_supabase_stubs manim_upgrade_fixture
apply_migration manim_upgrade_fixture "${migrations[0]}"
psql_db manim_upgrade_fixture <<'SQL'
INSERT INTO auth.users (id)
VALUES ('00000000-0000-0000-0000-000000000010');
INSERT INTO public.projects (id, user_id, title)
VALUES (
  '00000000-0000-0000-0000-000000000011',
  '00000000-0000-0000-0000-000000000010',
  'upgrade-fixture'
);
INSERT INTO public.scenes (id, project_id, scene_order)
VALUES (
  '00000000-0000-0000-0000-000000000012',
  '00000000-0000-0000-0000-000000000011',
  1
);
INSERT INTO public.ai_runs (id, project_id, scene_id, user_id, status)
VALUES (
  '00000000-0000-0000-0000-000000000013',
  '00000000-0000-0000-0000-000000000011',
  '00000000-0000-0000-0000-000000000012',
  '00000000-0000-0000-0000-000000000010',
  'queued'
);
INSERT INTO public.ai_steps (
  id, run_id, project_id, scene_id, sequence, kind, status
) VALUES
  (
    '00000000-0000-0000-0000-000000000014',
    '00000000-0000-0000-0000-000000000013',
    '00000000-0000-0000-0000-000000000011',
    '00000000-0000-0000-0000-000000000012',
    1,
    'idea_sketcher',
    'approved'
  ),
  (
    '00000000-0000-0000-0000-000000000015',
    '00000000-0000-0000-0000-000000000013',
    '00000000-0000-0000-0000-000000000011',
    '00000000-0000-0000-0000-000000000012',
    2,
    'storyboarder',
    'queued'
  );
SQL

for ((index = 1; index < ${#migrations[@]}; index++)); do
  apply_migration manim_upgrade_fixture "${migrations[$index]}"
done

psql_db manim_upgrade_fixture <<'SQL'
DO $$
BEGIN
  IF (
    SELECT COUNT(*)
    FROM public.ai_steps
    WHERE kind IN ('idea_sketcher', 'storyboarder')
  ) <> 2 THEN
    RAISE EXCEPTION 'upgrade replay did not preserve idea/storyboard rows';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace
      AND NOT convalidated
  ) THEN
    RAISE EXCEPTION 'clean upgrade fixture left an unvalidated public constraint';
  END IF;
END
$$;
SQL

# Reproduce a hosted database whose migration history says the lifecycle
# migration ran, but whose catalog lacks the check added to the local historical
# file later. Hardening must recreate and validate it instead of raising 42704.
psql_db postgres -c 'CREATE DATABASE manim_constraint_drift_fixture'
bootstrap_supabase_stubs manim_constraint_drift_fixture
for migration in "${migrations[@]}"; do
  if [[ "$migration" == "$production_migration" ]]; then
    break
  fi
  apply_migration manim_constraint_drift_fixture "$migration"
done

psql_db manim_constraint_drift_fixture <<'SQL'
INSERT INTO auth.users (id)
VALUES ('00000000-0000-0000-0000-000000000030');
INSERT INTO public.projects (id, user_id, title, source_language)
VALUES (
  '00000000-0000-0000-0000-000000000031',
  '00000000-0000-0000-0000-000000000030',
  'constraint-drift-fixture',
  NULL
);
INSERT INTO public.scenes (id, project_id, scene_order)
VALUES (
  '00000000-0000-0000-0000-000000000032',
  '00000000-0000-0000-0000-000000000031',
  1
);
ALTER TABLE public.scenes
  DROP CONSTRAINT scenes_scene_order_positive;
SQL

apply_migration manim_constraint_drift_fixture "$production_migration"

psql_db manim_constraint_drift_fixture <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint AS constraint_record
    WHERE constraint_record.conrelid = 'public.scenes'::regclass
      AND constraint_record.conname = 'scenes_scene_order_positive'
      AND constraint_record.contype = 'c'
      AND constraint_record.convalidated
      AND regexp_replace(
        pg_get_expr(constraint_record.conbin, constraint_record.conrelid),
        '[[:space:]()]',
        '',
        'g'
      ) = 'scene_order>=1'
  ) THEN
    RAISE EXCEPTION 'hardening did not repair the missing scenes check constraint';
  END IF;

  IF (
    SELECT source_language
    FROM public.projects
    WHERE id = '00000000-0000-0000-0000-000000000031'
  ) IS DISTINCT FROM 'vi' THEN
    RAISE EXCEPTION 'hardening did not repair a null project source_language';
  END IF;
END
$$;
SQL

# Prove production hardening does not abort on unknown legacy violations. It
# must install NOT VALID constraints for future writes, warn, and leave repair
# evidence for the post-deployment gate instead of deleting or rewriting rows.
psql_db postgres -c 'CREATE DATABASE manim_dirty_fixture'
bootstrap_supabase_stubs manim_dirty_fixture
for ((index = 0; index <= 4; index++)); do
  apply_migration manim_dirty_fixture "${migrations[$index]}"
done

psql_db manim_dirty_fixture <<'SQL'
INSERT INTO public.projects (id, user_id, title)
VALUES (
  '00000000-0000-0000-0000-000000000021',
  '00000000-0000-0000-0000-000000000020',
  'dirty-fixture'
);
INSERT INTO public.scenes (id, project_id, scene_order)
VALUES (
  '00000000-0000-0000-0000-000000000022',
  '00000000-0000-0000-0000-000000000021',
  -1
);
INSERT INTO public.ai_runs (
  id, project_id, scene_id, user_id, status, hitl_enabled
) VALUES (
  '00000000-0000-0000-0000-000000000023',
  '00000000-0000-0000-0000-000000000021',
  '00000000-0000-0000-0000-000000000022',
  '00000000-0000-0000-0000-000000000020',
  'queued',
  TRUE
);
INSERT INTO public.ai_steps (
  id, run_id, project_id, scene_id, sequence, kind, status
) VALUES
  (
    '00000000-0000-0000-0000-000000000024',
    '00000000-0000-0000-0000-000000000023',
    '00000000-0000-0000-0000-000000000021',
    '00000000-0000-0000-0000-000000000022',
    1,
    'builder',
    'queued'
  ),
  (
    '00000000-0000-0000-0000-000000000025',
    '00000000-0000-0000-0000-000000000023',
    '00000000-0000-0000-0000-000000000021',
    '00000000-0000-0000-0000-000000000022',
    1,
    'builder',
    'queued'
  );
SQL

for ((index = 5; index < ${#migrations[@]}; index++)); do
  if [[ "${migrations[$index]}" == "$production_migration" ]]; then
    psql_db manim_dirty_fixture -c \
      'ALTER TABLE public.scenes DROP CONSTRAINT scenes_scene_order_positive'
  fi
  apply_migration manim_dirty_fixture "${migrations[$index]}"
done

psql_db manim_dirty_fixture <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace
      AND NOT convalidated
  ) THEN
    RAISE EXCEPTION 'dirty fixture unexpectedly hid all legacy repair evidence';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint AS constraint_record
    WHERE constraint_record.conrelid = 'public.scenes'::regclass
      AND constraint_record.conname = 'scenes_scene_order_positive'
      AND constraint_record.contype = 'c'
      AND NOT constraint_record.convalidated
      AND regexp_replace(
        pg_get_expr(constraint_record.conbin, constraint_record.conrelid),
        '[[:space:]()]',
        '',
        'g'
      ) = 'scene_order>=1'
  ) THEN
    RAISE EXCEPTION 'dirty drift fixture did not retain the repaired NOT VALID scenes check';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.ai_steps'::regclass
      AND conname = 'ai_steps_run_sequence_key'
  ) THEN
    RAISE EXCEPTION 'dirty fixture unexpectedly installed a unique sequence constraint';
  END IF;

  IF (
    SELECT COUNT(*)
    FROM public.ai_steps
    WHERE run_id = '00000000-0000-0000-0000-000000000023'
      AND sequence = 1
  ) <> 2 THEN
    RAISE EXCEPTION 'production hardening destructively changed duplicate legacy rows';
  END IF;
END
$$;
SQL

echo "migration validation passed (clean + upgrade + constraint drift + non-destructive dirty drift fixtures)"
