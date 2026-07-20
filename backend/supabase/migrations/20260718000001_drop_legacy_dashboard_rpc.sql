-- Dashboard aggregates are owned by the authenticated Backend cache/service.
-- The legacy SECURITY DEFINER RPC accepted an arbitrary user UUID and is no
-- longer consumed, so remove it from existing deployments and PostgREST.
DROP FUNCTION IF EXISTS public.get_dashboard_stats(UUID);
