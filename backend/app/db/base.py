from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from shared.schemas.project import DashboardStats, Project, ProjectStatus
from shared.schemas.scene import Scene, StoryboardStatus
from shared.schemas.user import UserSettings


@runtime_checkable
class ContentStore(Protocol):
    """Database boundary used by the API and HITL coordinator."""

    def get_project(self, project_id: UUID) -> Project | None: ...
    def list_projects_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Project], int]: ...
    def create_project(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        title: str,
        description: str | None,
        source_language: str,
        target_scenes: int | None,
        status: ProjectStatus,
        config: dict[str, Any] | None,
    ) -> Project: ...
    def update_project(self, project_id: UUID, **fields: Any) -> Project | None: ...
    def update_project_if_current(
        self, project_id: UUID, *, expected_updated_at: datetime, **fields: Any
    ) -> Project | None: ...
    def delete_project(self, project_id: UUID) -> None: ...

    def get_scene(self, scene_id: UUID) -> Scene | None: ...
    def list_scenes_for_project(
        self, project_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Scene], int]: ...
    def get_project_scenes(self, project_id: UUID) -> list[Scene]: ...
    def create_scene(
        self,
        *,
        scene_id: UUID,
        project_id: UUID,
        scene_order: int,
        storyboard_text: str | None,
        voice_script: str | None,
        storyboard_status: StoryboardStatus,
    ) -> Scene: ...
    def update_scene(self, scene_id: UUID, **fields: Any) -> Scene | None: ...
    def update_scene_if_current(
        self, scene_id: UUID, *, expected_updated_at: datetime, **fields: Any
    ) -> Scene | None: ...
    def delete_scene(self, scene_id: UUID) -> None: ...

    def get_dashboard_stats(self, user_id: UUID) -> DashboardStats: ...

    def get_user_settings(self, user_id: UUID) -> UserSettings | None: ...
    def upsert_user_settings(self, settings: UserSettings) -> UserSettings: ...
