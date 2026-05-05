from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from backend.core.limiter import limiter
from shared.schemas.project import Project, ProjectCreate
from shared.schemas.scene import Scene, SceneCreate, StoryboardStatus

from backend.api.access import project_readable_by_user
from backend.api.deps import get_content_store, get_request_user_id
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


@router.get("", response_model=list[Project], summary="List projects", description="Lấy danh sách tất cả các dự án của người dùng hiện tại.")
def list_projects(
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> list[Project]:
    return store.list_projects_for_user(user_id)


@router.get("/{project_id}", response_model=Project, summary="Get project by id", description="Lấy thông tin chi tiết của một dự án cụ thể theo ID.")
def get_project(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Project:
    return project_readable_by_user(store, project_id, user_id)


@router.get("/{project_id}/scenes", response_model=list[Scene], summary="List scenes for project", description="Lấy danh sách các scene thuộc về một dự án.")
def list_project_scenes(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> list[Scene]:
    project_readable_by_user(store, project_id, user_id)
    return store.list_scenes_for_project(project_id)


@router.post(
    "/{project_id}/scenes",
    response_model=Scene,
    status_code=status.HTTP_201_CREATED,
    summary="Create scene",
    description="Tạo một scene mới trong dự án. Scene đại diện cho một phân đoạn video.",
)
def create_scene(
    project_id: UUID,
    body: SceneCreate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Scene:
    project_readable_by_user(store, project_id, user_id)
    storyboard_status: StoryboardStatus = (
        "pending_review" if body.storyboard_text else "missing"
    )
    return store.create_scene(
        scene_id=uuid4(),
        project_id=project_id,
        scene_order=body.scene_order,
        storyboard_text=body.storyboard_text,
        voice_script=body.voice_script,
        storyboard_status=storyboard_status,
    )


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
    scenes = store.list_scenes_for_project(project_id)
    if not scenes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no scenes",
        )
    for s in scenes:
        if s.storyboard_status != "pending_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Scene {s.id} is not awaiting storyboard approval "
                    f"(status={s.storyboard_status})"
                ),
            )
        if not (s.storyboard_text and s.storyboard_text.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scene {s.id} has empty storyboard text",
            )

    updated: list[Scene] = []
    for s in scenes:
        u = store.update_scene(s.id, storyboard_status="approved")
        assert u is not None
        updated.append(u)
    return updated
