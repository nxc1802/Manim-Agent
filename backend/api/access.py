from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from shared.schemas.project import Project

from backend.services.content_store import RedisContentStore


def project_readable_by_user(
    store: Any,
    project_id: UUID,
    user_id: UUID,
) -> Project:
    """Return the project if it exists and is owned by user_id; otherwise 404."""
    project = store.get_project(project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project
