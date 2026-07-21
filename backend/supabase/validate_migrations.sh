#!/usr/bin/env bash
set -Eeuo pipefail

export LC_ALL=C

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
migration_dir="$script_dir/migrations"
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
END
$$;

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

echo "migration validation passed (clean + upgrade + non-destructive dirty fixture)"
