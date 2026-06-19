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

ALTER TABLE public.artifact_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY artifact_versions_policy ON public.artifact_versions
    FOR ALL USING (true) WITH CHECK (true);
