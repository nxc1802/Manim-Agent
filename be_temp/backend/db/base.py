from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from shared.schemas.project import Project, ProjectStatus
from shared.schemas.scene import Scene, SceneCodeHistory, StoryboardStatus


@runtime_checkable
class ContentStore(Protocol):
    """Common interface for project and scene persistence."""

    def resolve_asset_local_path(self, asset_url: str | None) -> Path | None:
        """Convert a stored asset URL/path into a local filesystem Path.

        Handles file:// schemes for local storage or downloads from remote buckets (e.g. Supabase).
        """
        ...

    def save_project(self, project: Project) -> None: ...
    def get_project(self, project_id: UUID) -> Project | None: ...
    def list_projects_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Project], int]: ...
    def create_project(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        title: str,
        description: str | None,
        source_language: str,
        target_scenes: int | None = None,
        status: ProjectStatus = "draft",
        config: dict[str, Any] | None = None,
    ) -> Project: ...
    def touch_project(self, project_id: UUID) -> Project | None: ...
    def update_project(self, project_id: UUID, **fields: Any) -> Project | None: ...
    def delete_project(self, project_id: UUID) -> None: ...

    def save_scene(self, scene: Scene) -> None: ...
    def get_scene(self, scene_id: UUID) -> Scene | None: ...
    def list_scenes_for_project(
        self,
        project_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Scene], int]: ...
    def update_scene(self, scene_id: UUID, **fields: Any) -> Scene | None: ...
    def create_scene(
        self,
        *,
        scene_id: UUID,
        project_id: UUID,
        scene_order: int,
        storyboard_text: str | None = None,
        voice_script: str | None = None,
        storyboard_status: StoryboardStatus = "missing",
    ) -> Scene: ...
    def add_scene_to_project_index(self, scene: Scene) -> None: ...
    def save_scene_code_history(self, history: SceneCodeHistory) -> None: ...
    def delete_scene(self, scene_id: UUID) -> None: ...
    def batch_upsert_scenes(self, project_id: UUID, scenes: list[Scene]) -> list[Scene]: ...
