from __future__ import annotations

import logging
from uuid import UUID

from app.db.base import ContentStore

logger = logging.getLogger(__name__)


def reconcile_project_status(content: ContentStore, project_id: UUID) -> None:
    """CAS the aggregate project status from the latest scene lifecycle.

    Scene targets intentionally run in parallel. A compare-and-set loop keeps a
    late callback for one scene from publishing a project status calculated
    before another scene started or failed.
    """

    for _attempt in range(5):
        project = content.get_project(project_id)
        if project is None:
            return
        scenes = content.get_project_scenes(project_id)
        if scenes and all(scene.generation_status == "completed" for scene in scenes):
            desired = "completed"
        elif any(scene.generation_status in {"pending", "generating"} for scene in scenes):
            desired = "processing"
        else:
            desired = "draft"
        if project.status == desired:
            return
        if content.update_project_if_current(
            project_id,
            expected_updated_at=project.updated_at,
            status=desired,
        ) is not None:
            return
    logger.warning("Project status reconciliation lost repeated CAS races project_id=%s", project_id)
