# Supabase database workflow

`migrations/*.sql` is the only deployable source of truth for the Manim Agent
database. Never initialize a database from `init_schema.sql`; that file is a
non-executable compatibility marker for older tooling.

`20260721000000_production_hardening.sql` is the final production delta, not a
standalone bootstrap script. A complete production schema is the result of
replaying the full timestamp-ordered migration chain. Do not paste only the
hardening file into SQL Editor.

## Access model

- The browser uses Supabase Auth only and does not access application tables.
- Backend is the only Data API client and uses `service_role` server-side.
- Only `projects`, `scenes`, `ai_runs`, `ai_steps`, and `user_settings` grant
  CRUD privileges to `service_role`.
- `anon` and `authenticated` have no application-table privileges. RLS remains
  enabled and forced on every table as defense in depth.
- Retained legacy tables have neither Data API grants nor RLS policies, so they
  are deny-by-default.
- Application roles cannot execute functions in `public`; a new RPC must opt in
  with an explicit, reviewed `GRANT`.
- `videos` is a private Storage bucket. Backend uploads MP4 files and returns
  time-limited signed URLs; clients receive no direct Storage write policy.

Never expose `SUPABASE_SECRET_KEY` (or the legacy service-role key) to Frontend
or AI Core. Because
`service_role` bypasses RLS, every Backend route must still enforce project
ownership before calling the persistence adapters.

## Fast validation

Run the repository validator before every database change:

```bash
bash backend/supabase/validate_migrations.sh
```

It starts an ephemeral `postgres:17-alpine` container, creates compatible Auth,
Storage, role and Realtime stubs, and verifies:

- clean replay of every migration in timestamp order;
- upgrade replay with existing `idea_sketcher` and `storyboarder` rows;
- repair of a missing historical scene-order constraint without SQLSTATE 42704;
- non-destructive handling of orphan, invalid-order and duplicate legacy rows,
  including a missing-constraint drift fixture;
- forced RLS and explicit role targeting;
- exact Backend-only ACLs, real CRUD as `service_role`, fail-closed function
  privileges, private bucket configuration and cross-tenant rejection;
- validated constraints, required foreign-key/query indexes and schema/model
  alignment for `render_jobs`.

Set `POSTGRES_IMAGE` only when intentionally testing another PostgreSQL 17
patch image.

## Local Supabase

The checked-in `config.toml` pins PostgreSQL 17 and the private `videos` bucket.
Run CLI commands from `backend/`, where the `supabase/` directory is located:

```bash
cd backend
supabase --help
supabase start
supabase db reset
supabase db lint --level warning
supabase test db
```

Use the validator above in lightweight CI. Use `supabase db reset`, lint and any
pgTAP suite as the authoritative integration gate when the full local Supabase
stack is available.

To produce a review-only schema snapshot:

```bash
cd backend
supabase db reset
supabase db dump --local --schema public > /tmp/manim-public-schema.sql
```

Do not commit a hand-edited snapshot and do not deploy a dump in addition to
the migrations.

## Deploying migrations

For a new hosted project:

```bash
cd backend
supabase login
supabase link --project-ref <project-ref>
supabase migration list
supabase db push --dry-run
supabase db push
```

`db push` records applied versions in
`supabase_migrations.schema_migrations`. Do not run migration files manually in
the SQL Editor, and never have multiple deployment jobs push concurrently.

For an existing project, first compare local and remote history. If Dashboard
changes exist, capture and review them with `supabase db pull` before pushing.
Never use `supabase db reset --linked` against production.

After deployment, run Supabase Security and Performance Advisors, then execute
the same read-only gate used by CI/CD:

```bash
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
  -f backend/supabase/postmigration_gate.sql
```

The single result row must contain eight zero counts. It verifies constraint
validation and presence, canonical scene-order definition, duplicate sequences,
the complete table/schema/function ACL matrix, and the strict Project column
contract. Warnings mean a data-repair migration is required before promotion.

## Rollback and recovery

Production migrations are forward-only. If an applied migration must be
reverted, create and test a new compensating migration; do not edit migration
history or reset production. Take a database backup/PITR checkpoint before DDL
that transforms data, and test restores on a separate project.

Deleting database rows does not delete rendered Storage objects. Storage
lifecycle cleanup is an operational responsibility until an explicit garbage
collector is implemented.

References:

- [Supabase database migrations](https://supabase.com/docs/guides/local-development/database-migrations)
- [Supabase RLS guidance](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase Storage buckets](https://supabase.com/docs/guides/storage/buckets/creating-buckets)
- [Data API explicit-grant change](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically)
