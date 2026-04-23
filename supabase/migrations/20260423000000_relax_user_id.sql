-- Relax foreign key constraint for projects.user_id to allow easier integration
-- especially when auth.users is managed separately or not yet populated.

ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_user_id_fkey;

-- We still keep the column, but it's no longer a hard reference to auth.users.
-- This allows using dummy IDs like '00000000-0000-0000-0000-000000000001'.
