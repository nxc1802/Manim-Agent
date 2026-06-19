from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from shared.schemas.scene import Scene, SceneUpdate

from backend.api.access import project_readable_by_user
from backend.api.deps import (
    get_content_store,
    get_request_user_id,
)
from backend.db.base import ContentStore

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{scene_id}", response_model=Scene, summary="Get scene by id")
def get_scene(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)
    return scene


@router.patch("/{scene_id}", response_model=Scene, summary="Update scene")
def update_scene(
    scene_id: UUID,
    body: SceneUpdate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)

    update_data = body.model_dump(exclude_unset=True)
    updated = store.update_scene(scene_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Update failed")
    return updated


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete scene")
def delete_scene(
    scene_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> None:
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Scene not found: {scene_id}")
    project_readable_by_user(store, scene.project_id, user_id)
    store.delete_scene(scene_id)
