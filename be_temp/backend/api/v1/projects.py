from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from shared.schemas.pagination import PaginatedResponse, PaginationParams
from shared.schemas.project import Project, ProjectCreate, ProjectUpdate
from shared.schemas.scene import Scene, SceneCreate, StoryboardStatus

from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_request_user_id
from backend.core.limiter import limiter
from backend.db.base import ContentStore

router = APIRouter(tags=["projects"])


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    summary="Create project",
    description="Khởi tạo một dự án mới. Đây là bước đầu tiên trong quy trình sản xuất video.",
)
@limiter.limit("2/minute")
def create_project(
    request: Request,
    body: ProjectCreate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Project:
    # Merge top-level fields into config for persistence
    project_config = body.config or {}
    if "use_primitives" not in project_config:
        project_config["use_primitives"] = body.use_primitives

    return store.create_project(
        project_id=uuid4(),
        user_id=user_id,
        title=body.title,
        description=body.description,
        source_language=body.source_language,
        target_scenes=body.target_scenes,
        config=project_config,
        status="draft",
    )


@router.get(
    "",
    response_model=PaginatedResponse[Project],
    summary="List projects",
    description="Lấy danh sách phân trang tất cả các dự án của người dùng hiện tại.",
)
def list_projects(
    params: PaginationParams = Depends(),  # noqa: B008
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> PaginatedResponse[Project]:
    items, total = store.list_projects_for_user(
        user_id,
        limit=params.limit,
        offset=params.offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        limit=params.limit,
        pages=(total + params.limit - 1) // params.limit,
    )


@router.get(
    "/{project_id}",
    response_model=Project,
    summary="Get project by id",
    description="Lấy thông tin chi tiết của một dự án cụ thể theo ID.",
)
def get_project(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Project:
    return project_readable_by_user(store, project_id, user_id)


@router.patch(
    "/{project_id}",
    response_model=Project,
    summary="Update project",
)
def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Project:
    project_readable_by_user(store, project_id, user_id)
    update_data = body.model_dump(exclude_unset=True)
    updated = store.update_project(project_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Update failed")
    return updated


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
)
def delete_project(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> None:
    project_readable_by_user(store, project_id, user_id)
    store.delete_project(project_id)


@router.get(
    "/{project_id}/scenes",
    response_model=PaginatedResponse[Scene],
    summary="List scenes for project",
    description="Lấy danh sách phân trang các scene thuộc về một dự án.",
)
def list_project_scenes(
    project_id: UUID,
    params: PaginationParams = Depends(),  # noqa: B008
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> PaginatedResponse[Scene]:
    project_readable_by_user(store, project_id, user_id)
    items, total = store.list_scenes_for_project(
        project_id,
        limit=params.limit,
        offset=params.offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        limit=params.limit,
        pages=(total + params.limit - 1) // params.limit,
    )


@router.post(
    "/{project_id}/scenes",
    response_model=Scene,
    status_code=status.HTTP_201_CREATED,
    summary="Create scene",
    description="Tạo một scene mới trong dự án. Scene đại diện cho một phân đoạn video.",
)
@limiter.limit("10/minute")
def create_scene(
    project_id: UUID,
    body: SceneCreate,
    request: Request,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    project_readable_by_user(store, project_id, user_id)
    storyboard_status: StoryboardStatus = "pending_review" if body.storyboard_text else "missing"
    return store.create_scene(
        scene_id=uuid4(),
        project_id=project_id,
        scene_order=body.scene_order,
        storyboard_text=body.storyboard_text,
        voice_script=body.voice_script,
        storyboard_status=storyboard_status,
    )


@router.post(
    "/{project_id}/scenes/batch",
    response_model=list[Scene],
    summary="Batch upsert scenes",
)
def batch_upsert_scenes(
    project_id: UUID,
    body: list[Scene],
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> list[Scene]:
    project_readable_by_user(store, project_id, user_id)
    # Ensure project_id matches for all scenes
    for s in body:
        if s.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scene {s.id} project_id mismatch",
            )
    return store.batch_upsert_scenes(project_id, body)


@router.post(
    "/{project_id}/approve-storyboard",
    response_model=list[Scene],
    summary="HITL: approve all pending storyboards in project",
)
def approve_project_storyboard(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> list[Scene]:
    project_readable_by_user(store, project_id, user_id)
    # Note: list_scenes_for_project is now paginated, but here we might need ALL scenes.
    # For HITL approval, we usually want all.
    # Let's fetch a large limit or add a non-paginated method.
    # For now, let's use a large limit.
    scenes, _ = store.list_scenes_for_project(project_id, limit=1000)
    if not scenes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no scenes",
        )
    for s in scenes:
        if s.storyboard_status != "pending_review":
            continue  # Skip already approved or missing
        if not (s.storyboard_text and s.storyboard_text.strip()):
            continue
        store.update_scene(s.id, storyboard_status="approved")

    updated, _ = store.list_scenes_for_project(project_id, limit=1000)
    return updated
