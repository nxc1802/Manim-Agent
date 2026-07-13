from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from app.core.config import settings
from app.db.base import ContentStore
from shared.schemas.project import DashboardStats, Project, ProjectStatus
from shared.schemas.scene import Scene, StoryboardStatus
from shared.schemas.user import UserSettings


class SupabaseContentStore(ContentStore):
    """The production database adapter; all DB access terminates in Backend."""

    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase is not configured")
        self.base_url = settings.supabase_url.rstrip("/")
        self.headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _request(self, method: str, table: str, *, params: dict[str, str] | None = None, body: Any = None) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, f"{self.base_url}/rest/v1/{table}", headers=self.headers, params=params, json=body)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, list) else []

    def get_project(self, project_id: UUID) -> Project | None:
        rows = self._request("GET", "projects", params={"id": f"eq.{project_id}", "select": "*"})
        return Project.model_validate(rows[0]) if rows else None

    def list_projects_for_user(self, user_id: UUID, *, limit: int, offset: int) -> tuple[list[Project], int]:
        params = {"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
        rows = self._request("GET", "projects", params=params)
        # PostgREST count is intentionally avoided here; a cheap exact count is clear and portable.
        total = len(self._request("GET", "projects", params={"user_id": f"eq.{user_id}", "select": "id"}))
        return [Project.model_validate(row) for row in rows], total

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
    ) -> Project:
        now = datetime.now(tz=UTC)
        project = Project(id=project_id, user_id=user_id, title=title, description=description, source_language=source_language, target_scenes=target_scenes, status=status, config=config or {}, created_at=now, updated_at=now)
        return Project.model_validate(self._request("POST", "projects", body=project.model_dump(mode="json"))[0])

    def update_project(self, project_id: UUID, **fields: Any) -> Project | None:
        rows = self._request("PATCH", "projects", params={"id": f"eq.{project_id}"}, body=fields)
        return Project.model_validate(rows[0]) if rows else None

    def delete_project(self, project_id: UUID) -> None:
        self._request("DELETE", "projects", params={"id": f"eq.{project_id}"})

    def get_scene(self, scene_id: UUID) -> Scene | None:
        rows = self._request("GET", "scenes", params={"id": f"eq.{scene_id}", "select": "*"})
        return Scene.model_validate(rows[0]) if rows else None

    def list_scenes_for_project(self, project_id: UUID, *, limit: int, offset: int) -> tuple[list[Scene], int]:
        filters = {"project_id": f"eq.{project_id}", "select": "*", "order": "scene_order.asc", "limit": str(limit), "offset": str(offset)}
        rows = self._request("GET", "scenes", params=filters)
        total = len(self._request("GET", "scenes", params={"project_id": f"eq.{project_id}", "select": "id"}))
        return [Scene.model_validate(row) for row in rows], total

    def create_scene(
        self,
        *,
        scene_id: UUID,
        project_id: UUID,
        scene_order: int,
        storyboard_text: str | None,
        voice_script: str | None,
        storyboard_status: StoryboardStatus,
    ) -> Scene:
        scene = Scene(id=scene_id, project_id=project_id, scene_order=scene_order, storyboard_text=storyboard_text, voice_script=voice_script, storyboard_status=storyboard_status, created_at=datetime.now(tz=UTC), updated_at=datetime.now(tz=UTC))
        return Scene.model_validate(self._request("POST", "scenes", body=scene.model_dump(mode="json"))[0])

    def update_scene(self, scene_id: UUID, **fields: Any) -> Scene | None:
        rows = self._request("PATCH", "scenes", params={"id": f"eq.{scene_id}"}, body=fields)
        return Scene.model_validate(rows[0]) if rows else None

    def delete_scene(self, scene_id: UUID) -> None:
        self._request("DELETE", "scenes", params={"id": f"eq.{scene_id}"})

    def get_dashboard_stats(self, user_id: UUID) -> DashboardStats:
        projects, total = self.list_projects_for_user(user_id, limit=1, offset=0)
        _ = projects
        return DashboardStats(total_projects=total, active_jobs=0, total_tokens_used=0, total_render_time_hours=0.0)

    def get_user_settings(self, user_id: UUID) -> UserSettings | None:
        rows = self._request("GET", "user_settings", params={"user_id": f"eq.{user_id}", "select": "*"})
        return UserSettings.model_validate(rows[0]) if rows else None

    def upsert_user_settings(self, settings: UserSettings) -> UserSettings:
        # Upsert requires Prefer: resolution=merge-duplicates or similar, but POST with upsert works with ON CONFLICT
        # Supabase REST API handles upsert via POST if we set "Prefer": "resolution=merge-duplicates"
        # Since _request doesn't let us override Prefer header, let's use standard upsert query format if needed.
        # But wait, POST with ON CONFLICT needs resolution=merge-duplicates header.
        # A simpler way is to GET, then PATCH if exists, or POST if not exists.
        existing = self.get_user_settings(settings.user_id)
        if existing:
            rows = self._request("PATCH", "user_settings", params={"user_id": f"eq.{settings.user_id}"}, body=settings.model_dump(mode="json"))
            return UserSettings.model_validate(rows[0])
        else:
            rows = self._request("POST", "user_settings", body=settings.model_dump(mode="json"))
            return UserSettings.model_validate(rows[0])
