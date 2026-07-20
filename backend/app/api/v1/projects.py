from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, status
from shared.schemas.pagination import PaginatedResponse, PaginationParams
from shared.schemas.project import DashboardStats, Project, ProjectCreate
from shared.schemas.scene import Scene

from app.api.access import project_readable_by_user
from app.api.deps import ContentStore, get_content_store, get_request_user_id
from app.core.limiter import limiter

router = APIRouter(tags=["projects"])


@router.post(
    "", response_model=Project, status_code=status.HTTP_201_CREATED, summary="Create project"
)
@limiter.limit("2/minute")
def create_project(
    request: Request,
    body: ProjectCreate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Project:
    return store.create_project(
        project_id=uuid4(),
        user_id=user_id,
        title=body.title,
        description=body.description,
        source_language=body.source_language,
        target_scenes=body.target_scenes,
        config=body.config or {},
        status="draft",
    )


@router.get("", response_model=PaginatedResponse[Project], summary="List projects")
def list_projects(
    params: PaginationParams = Depends(),  # noqa: B008
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> PaginatedResponse[Project]:
    items, total = store.list_projects_for_user(user_id, limit=params.limit, offset=params.offset)
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        limit=params.limit,
        pages=(total + params.limit - 1) // params.limit,
    )

@router.get("/stats", response_model=DashboardStats, summary="Get dashboard stats")
def get_dashboard_stats(
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> DashboardStats:
    return store.get_dashboard_stats(user_id)


@router.get("/{project_id}", response_model=Project, summary="Get project")
def get_project(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> Project:
    return project_readable_by_user(store, project_id, user_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete project")
def delete_project(
    project_id: UUID,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> None:
    project_readable_by_user(store, project_id, user_id)
    store.delete_project(project_id)


@router.get("/{project_id}/scenes", response_model=PaginatedResponse[Scene], summary="List scenes")
def list_project_scenes(
    project_id: UUID,
    params: PaginationParams = Depends(),  # noqa: B008
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> PaginatedResponse[Scene]:
    project_readable_by_user(store, project_id, user_id)
    items, total = store.list_scenes_for_project(
        project_id, limit=params.limit, offset=params.offset
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        limit=params.limit,
        pages=(total + params.limit - 1) // params.limit,
    )
