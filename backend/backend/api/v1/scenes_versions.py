from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.schemas.artifact_version import (
    ArtifactEntityType,
    ArtifactVersion,
    RollbackEntityType,
)
from shared.schemas.scene import Scene
from worker.tasks import render_manim_scene

from backend.api.access import project_readable_by_user
from backend.api.deps import (
    get_content_store,
    get_job_store,
    get_request_user_id,
)
from backend.core.config import settings
from backend.db.base import ContentStore
from backend.services.job_store import RedisRenderJobStore
from backend.services.version_store import VersionStore

logger = logging.getLogger(__name__)

router = APIRouter()

SCENE_VERSION_ENTITY_TYPES: tuple[RollbackEntityType, ...] = (
    "storyboard",
    "plan",
    "dsl",
    "code",
)


class RollbackRequest(BaseModel):
    entity_type: RollbackEntityType
    target_version: int = Field(ge=1)


class DirectDslEditRequest(BaseModel):
    dsl_code: str = Field(min_length=1, max_length=200_000)


class DirectDslEditResponse(BaseModel):
    scene: Scene
    preview_job_id: UUID


@router.get("/{scene_id}/versions", response_model=list[ArtifactVersion])
def get_scene_versions(
    scene_id: UUID,
    entity_type: ArtifactEntityType | None = None,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> list[ArtifactVersion]:
    """Retrieve version history of artifacts for a given scene."""
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)

    version_store = VersionStore(store)
    if entity_type:
        all_versions = version_store.list_versions(entity_type=entity_type, entity_id=scene_id)
    else:
        # Fetch versions across all types if not specified
        all_versions = []
        for et in SCENE_VERSION_ENTITY_TYPES:
            all_versions.extend(version_store.list_versions(entity_type=et, entity_id=scene_id))
        all_versions.sort(key=lambda x: x.created_at, reverse=True)

    return all_versions


@router.post("/{scene_id}/rollback", response_model=ArtifactVersion)
def rollback_scene_artifact(
    scene_id: UUID,
    body: RollbackRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> ArtifactVersion:
    """Roll back an artifact version to a prior snapshot and update active state."""
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)

    version_store = VersionStore(store)
    try:
        new_ver = version_store.rollback(
            entity_type=body.entity_type,
            entity_id=scene_id,
            target_version=body.target_version,
            created_by="user_rollback",
        )
        return new_ver
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err)
        ) from val_err


@router.patch("/{scene_id}/dsl", response_model=DirectDslEditResponse)
def edit_scene_dsl_directly(
    scene_id: UUID,
    body: DirectDslEditRequest,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
    job_store: RedisRenderJobStore = Depends(get_job_store),  # noqa: B008
) -> DirectDslEditResponse:
    """Parse and compile a direct DSL edit, save versions, and trigger a preview."""
    scene = store.get_scene(scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene not found: {scene_id}"
        )
    project_readable_by_user(store, scene.project_id, user_id)

    # 1. Parse Python DSL class
    from ai_engine.dsl_compiler import compile_dsl_to_manim, parse_python_class_dsl
    from shared.code_utils import extract_python_code

    from backend.services.code_sandbox import SandboxLimits, validate_manim_code

    dsl_stripped = extract_python_code(body.dsl_code).strip()
    try:
        dsl_obj = parse_python_class_dsl(dsl_stripped)
    except Exception as parse_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DSL parsing failed: {parse_err}",
        ) from parse_err

    # 2. Compile to Manim code
    try:
        compiled_code = compile_dsl_to_manim(dsl_obj)
        validate_manim_code(
            compiled_code,
            limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        )
    except Exception as compile_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manim compilation failed: {compile_err}",
        ) from compile_err

    # 3. Save versions to the history database
    version_store = VersionStore(store)
    saved_dsl_ver = version_store.save_version(
        entity_type="dsl",
        entity_id=scene_id,
        content=dsl_obj.model_dump(mode="json"),
        created_by="user_edit",
    )
    saved_code_ver = version_store.save_version(
        entity_type="code",
        entity_id=scene_id,
        content=compiled_code,
        created_by="user_edit",
    )

    # 4. Update scene table active state
    updated_scene = store.update_scene(
        scene_id,
        scene_dsl=dsl_obj.model_dump(mode="json"),
        scene_dsl_version=saved_dsl_ver.version,
        manim_code=compiled_code,
        manim_code_version=saved_code_ver.version,
        review_loop_status="running",
    )
    if not updated_scene:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update scene details in DB.",
        )

    # 5. Enqueue background preview rendering job
    job_id = uuid4()
    job_store.create_queued_job(
        job_id=job_id,
        project_id=updated_scene.project_id,
        scene_id=scene_id,
        job_type="preview",
        render_quality="720p",
        webhook_url=None,
        docker_image_tag=settings.worker_image_tag,
    )
    render_manim_scene.apply_async(args=[str(job_id)], queue="render")

    return DirectDslEditResponse(scene=updated_scene, preview_job_id=job_id)
