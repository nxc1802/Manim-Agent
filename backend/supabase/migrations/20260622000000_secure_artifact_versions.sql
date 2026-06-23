DROP POLICY IF EXISTS artifact_versions_policy ON public.artifact_versions;

CREATE POLICY artifact_versions_policy ON public.artifact_versions
    FOR ALL
    USING (
        EXISTS (
            SELECT 1
            FROM public.scenes s
            JOIN public.projects p ON p.id = s.project_id
            WHERE s.id = artifact_versions.entity_id
              AND p.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.scenes s
            JOIN public.projects p ON p.id = s.project_id
            WHERE s.id = artifact_versions.entity_id
              AND p.user_id = auth.uid()
        )
    );
