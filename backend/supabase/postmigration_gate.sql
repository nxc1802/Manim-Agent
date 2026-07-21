WITH required_constraints(table_name, constraint_name, constraint_type) AS (
  VALUES
    ('public.projects', 'projects_id_user_id_key', 'u'),
    ('public.scenes', 'scenes_id_project_id_key', 'u'),
    ('public.ai_runs', 'ai_runs_id_project_id_key', 'u'),
    ('public.ai_runs', 'ai_runs_id_scene_id_key', 'u'),
    ('public.projects', 'projects_user_id_auth_fkey', 'f'),
    ('public.user_settings', 'user_settings_user_id_auth_fkey', 'f'),
    ('public.ai_runs', 'ai_runs_user_id_auth_fkey', 'f'),
    ('public.ai_runs', 'ai_runs_project_owner_fkey', 'f'),
    ('public.ai_runs', 'ai_runs_scene_project_fkey', 'f'),
    ('public.ai_steps', 'ai_steps_run_project_fkey', 'f'),
    ('public.ai_steps', 'ai_steps_run_scene_fkey', 'f'),
    ('public.scenes', 'scenes_scene_order_positive', 'c'),
    ('public.render_jobs', 'render_jobs_job_type_check', 'c'),
    ('public.render_jobs', 'render_jobs_render_quality_check', 'c'),
    ('public.ai_steps', 'ai_steps_kind_check', 'c'),
    ('public.ai_steps', 'ai_steps_run_sequence_key', 'u')
),
application_tables(table_name, is_active) AS (
  VALUES
    ('projects', TRUE),
    ('scenes', TRUE),
    ('ai_runs', TRUE),
    ('ai_steps', TRUE),
    ('user_settings', TRUE),
    ('render_jobs', FALSE),
    ('voice_jobs', FALSE),
    ('assets', FALSE),
    ('pipeline_runs', FALSE),
    ('scene_code_history', FALSE),
    ('agent_logs', FALSE),
    ('worker_service_audit', FALSE),
    ('pipeline_events', FALSE),
    ('artifact_versions', FALSE)
),
application_roles(role_name) AS (
  VALUES ('anon'), ('authenticated'), ('service_role')
),
table_privileges(privilege_name) AS (
  VALUES
    ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'),
    ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')
)
SELECT
  (
    SELECT COUNT(*)
    FROM pg_catalog.pg_constraint AS constraint_record
    WHERE constraint_record.connamespace = pg_catalog.to_regnamespace('public')
      AND NOT constraint_record.convalidated
  ) AS unvalidated_constraint_count,
  (
    SELECT COUNT(*)
    FROM (
      SELECT step_record.run_id, step_record.sequence
      FROM public.ai_steps AS step_record
      GROUP BY step_record.run_id, step_record.sequence
      HAVING COUNT(*) > 1
    ) AS duplicate_sequences
  ) AS duplicate_step_sequence_count,
  (
    SELECT COUNT(*)
    FROM required_constraints AS required_constraint
    WHERE NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_constraint AS constraint_record
      WHERE constraint_record.conrelid = pg_catalog.to_regclass(
              required_constraint.table_name
            )
        AND constraint_record.conname = required_constraint.constraint_name
        AND constraint_record.contype = required_constraint.constraint_type::"char"
    )
  ) AS required_constraint_issue_count,
  (
    SELECT COUNT(*)
    FROM pg_catalog.pg_constraint AS constraint_record
    WHERE constraint_record.conrelid = 'public.scenes'::regclass
      AND constraint_record.conname = 'scenes_scene_order_positive'
      AND pg_catalog.regexp_replace(
        pg_catalog.pg_get_expr(
          constraint_record.conbin,
          constraint_record.conrelid
        ),
        '[[:space:]()]',
        '',
        'g'
      ) <> 'scene_order>=1'
  ) AS scenes_check_definition_issue_count,
  (
    SELECT COUNT(*)
    FROM application_tables
    CROSS JOIN application_roles
    CROSS JOIN table_privileges
    WHERE pg_catalog.has_table_privilege(
            application_roles.role_name,
            pg_catalog.format('public.%I', application_tables.table_name),
            table_privileges.privilege_name
          ) IS DISTINCT FROM (
            application_roles.role_name = 'service_role'
            AND application_tables.is_active
            AND table_privileges.privilege_name = ANY (
              ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']
            )
          )
  ) AS table_acl_issue_count,
  (
    SELECT COUNT(*)
    FROM application_roles
    WHERE pg_catalog.has_schema_privilege(
            application_roles.role_name,
            'public',
            'CREATE'
          )
       OR (
            application_roles.role_name = 'service_role'
            AND NOT pg_catalog.has_schema_privilege(
              application_roles.role_name,
              'public',
              'USAGE'
            )
          )
  ) AS schema_acl_issue_count,
  (
    SELECT COUNT(*)
    FROM pg_catalog.pg_proc AS function_record
    JOIN pg_catalog.pg_namespace AS namespace_record
      ON namespace_record.oid = function_record.pronamespace
    CROSS JOIN application_roles
    WHERE namespace_record.nspname = 'public'
      AND pg_catalog.has_function_privilege(
        application_roles.role_name,
        function_record.oid,
        'EXECUTE'
      )
  ) AS function_acl_issue_count,
  CASE WHEN EXISTS (
    SELECT 1
    FROM information_schema.columns AS column_definition
    WHERE column_definition.table_schema = 'public'
      AND column_definition.table_name = 'projects'
      AND column_definition.column_name = 'source_language'
      AND column_definition.is_nullable = 'NO'
      AND column_definition.column_default = '''vi''::text'
  ) THEN 0 ELSE 1 END AS project_contract_issue_count;
