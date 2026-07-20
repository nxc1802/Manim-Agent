from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from app.core.config import settings
from app.db.base import ContentStore
from app.services.cache import CACHE_MISS, RedisJsonCache
from app.services.redis_client import get_redis
from shared.schemas.project import DashboardStats, Project, ProjectStatus
from shared.schemas.scene import Scene, StoryboardStatus
from shared.schemas.user import UserSettings


class SupabaseContentStore(ContentStore):
    """The production database adapter; all DB access terminates in Backend."""

    def __init__(self, cache: RedisJsonCache | None = None) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase is not configured")
        self.base_url = settings.supabase_url.rstrip("/")
        self.headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self.cache = cache or RedisJsonCache(get_redis())

    @staticmethod
    def _project_scope(user_id: UUID) -> str:
        return f"content:user-projects:{user_id}"

    @staticmethod
    def _scene_scope(project_id: UUID) -> str:
        return f"content:project-scenes:{project_id}"

    def _object_key(self, kind: str, identifier: UUID) -> str:
        return self.cache.key("content", kind, identifier)

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        body: Any = None,
        prefer: str | None = None,
    ) -> list[dict[str, Any]]:
        request_headers = self.headers if prefer is None else {**self.headers, "Prefer": prefer}
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method,
                f"{self.base_url}/rest/v1/{table}",
                headers=request_headers,
                params=params,
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, list) else []

    def get_project(self, project_id: UUID) -> Project | None:
        cache_key = self._object_key("project", project_id)
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS:
            return Project.model_validate(cached) if cached is not None else None
        rows = self._request("GET", "projects", params={"id": f"eq.{project_id}", "select": "*"})
        project = Project.model_validate(rows[0]) if rows else None
        self.cache.set(cache_key, project.model_dump(mode="json") if project else None)
        return project

    def list_projects_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Project], int]:
        generation = self.cache.generation(self._project_scope(user_id))
        cache_key = self.cache.key(
            "content", "projects", user_id, generation, "limit", limit, "offset", offset
        )
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS and isinstance(cached, dict):
            return (
                [Project.model_validate(row) for row in cached.get("items", [])],
                int(cached.get("total", 0)),
            )
        params = {
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        }
        rows = self._request("GET", "projects", params=params)
        # PostgREST count is intentionally avoided here; a cheap exact count is clear and portable.
        total = len(
            self._request("GET", "projects", params={"user_id": f"eq.{user_id}", "select": "id"})
        )
        projects = [Project.model_validate(row) for row in rows]
        self.cache.set(
            cache_key,
            {"items": [item.model_dump(mode="json") for item in projects], "total": total},
            ttl_seconds=settings.cache_list_ttl_seconds,
        )
        return projects, total

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
        project = Project(
            id=project_id,
            user_id=user_id,
            title=title,
            description=description,
            source_language=source_language,
            target_scenes=target_scenes,
            status=status,
            config=config or {},
            created_at=now,
            updated_at=now,
        )
        created = Project.model_validate(
            self._request("POST", "projects", body=project.model_dump(mode="json"))[0]
        )
        self.cache.set(self._object_key("project", created.id), created.model_dump(mode="json"))
        self.cache.bump(self._project_scope(created.user_id), "dashboard:projects")
        return created

    def update_project(self, project_id: UUID, **fields: Any) -> Project | None:
        rows = self._request("PATCH", "projects", params={"id": f"eq.{project_id}"}, body=fields)
        updated = Project.model_validate(rows[0]) if rows else None
        if updated is None:
            self.cache.delete(self._object_key("project", project_id))
            return None
        self.cache.set(self._object_key("project", project_id), updated.model_dump(mode="json"))
        self.cache.bump(self._project_scope(updated.user_id), "dashboard:projects")
        return updated

    def update_project_if_current(
        self, project_id: UUID, *, expected_updated_at: datetime, **fields: Any
    ) -> Project | None:
        rows = self._request(
            "PATCH",
            "projects",
            params={
                "id": f"eq.{project_id}",
                "updated_at": f"eq.{expected_updated_at.isoformat()}",
            },
            body=fields,
        )
        updated = Project.model_validate(rows[0]) if rows else None
        if updated is None:
            self.cache.delete(self._object_key("project", project_id))
            return None
        self.cache.set(self._object_key("project", project_id), updated.model_dump(mode="json"))
        self.cache.bump(self._project_scope(updated.user_id), "dashboard:projects")
        return updated

    def delete_project(self, project_id: UUID) -> None:
        project = self.get_project(project_id)
        scenes = self.get_project_scenes(project_id)
        self._request("DELETE", "projects", params={"id": f"eq.{project_id}"})
        self.cache.delete(
            self._object_key("project", project_id),
            *(self._object_key("scene", scene.id) for scene in scenes),
        )
        scopes = [self._scene_scope(project_id), "dashboard:projects"]
        if project is not None:
            scopes.append(self._project_scope(project.user_id))
        self.cache.bump(*scopes)

    def get_scene(self, scene_id: UUID) -> Scene | None:
        cache_key = self._object_key("scene", scene_id)
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS:
            return Scene.model_validate(cached) if cached is not None else None
        rows = self._request("GET", "scenes", params={"id": f"eq.{scene_id}", "select": "*"})
        scene = Scene.model_validate(rows[0]) if rows else None
        self.cache.set(cache_key, scene.model_dump(mode="json") if scene else None)
        return scene

    def list_scenes_for_project(
        self, project_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Scene], int]:
        generation = self.cache.generation(self._scene_scope(project_id))
        cache_key = self.cache.key(
            "content", "scenes", project_id, generation, "limit", limit, "offset", offset
        )
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS and isinstance(cached, dict):
            return (
                [Scene.model_validate(row) for row in cached.get("items", [])],
                int(cached.get("total", 0)),
            )
        filters = {
            "project_id": f"eq.{project_id}",
            "select": "*",
            "order": "scene_order.asc",
            "limit": str(limit),
            "offset": str(offset),
        }
        rows = self._request("GET", "scenes", params=filters)
        total = len(
            self._request(
                "GET", "scenes", params={"project_id": f"eq.{project_id}", "select": "id"}
            )
        )
        scenes = [Scene.model_validate(row) for row in rows]
        self.cache.set(
            cache_key,
            {"items": [item.model_dump(mode="json") for item in scenes], "total": total},
            ttl_seconds=settings.cache_list_ttl_seconds,
        )
        return scenes, total

    def get_project_scenes(self, project_id: UUID) -> list[Scene]:
        generation = self.cache.generation(self._scene_scope(project_id))
        cache_key = self.cache.key("content", "scenes", project_id, generation, "all")
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS and isinstance(cached, list):
            return [Scene.model_validate(row) for row in cached]
        rows = self._request(
            "GET",
            "scenes",
            params={"project_id": f"eq.{project_id}", "select": "*", "order": "scene_order.asc"},
        )
        scenes = [Scene.model_validate(row) for row in rows]
        self.cache.set(
            cache_key,
            [item.model_dump(mode="json") for item in scenes],
            ttl_seconds=settings.cache_list_ttl_seconds,
        )
        return scenes

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
        scene = Scene(
            id=scene_id,
            project_id=project_id,
            scene_order=scene_order,
            storyboard_text=storyboard_text,
            voice_script=voice_script,
            storyboard_status=storyboard_status,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        created = Scene.model_validate(
            self._request("POST", "scenes", body=scene.model_dump(mode="json"))[0]
        )
        self.cache.set(self._object_key("scene", created.id), created.model_dump(mode="json"))
        self.cache.bump(self._scene_scope(created.project_id))
        return created

    def update_scene(self, scene_id: UUID, **fields: Any) -> Scene | None:
        rows = self._request("PATCH", "scenes", params={"id": f"eq.{scene_id}"}, body=fields)
        updated = Scene.model_validate(rows[0]) if rows else None
        if updated is None:
            self.cache.delete(self._object_key("scene", scene_id))
            return None
        self.cache.set(self._object_key("scene", scene_id), updated.model_dump(mode="json"))
        self.cache.bump(self._scene_scope(updated.project_id))
        return updated

    def update_scene_if_current(
        self, scene_id: UUID, *, expected_updated_at: datetime, **fields: Any
    ) -> Scene | None:
        rows = self._request(
            "PATCH",
            "scenes",
            params={
                "id": f"eq.{scene_id}",
                "updated_at": f"eq.{expected_updated_at.isoformat()}",
            },
            body=fields,
        )
        updated = Scene.model_validate(rows[0]) if rows else None
        if updated is None:
            self.cache.delete(self._object_key("scene", scene_id))
            return None
        self.cache.set(self._object_key("scene", scene_id), updated.model_dump(mode="json"))
        self.cache.bump(self._scene_scope(updated.project_id))
        return updated

    def delete_scene(self, scene_id: UUID) -> None:
        scene = self.get_scene(scene_id)
        self._request("DELETE", "scenes", params={"id": f"eq.{scene_id}"})
        self.cache.delete(self._object_key("scene", scene_id))
        if scene is not None:
            self.cache.bump(self._scene_scope(scene.project_id))

    def get_dashboard_stats(self, user_id: UUID) -> DashboardStats:
        project_generation = self.cache.generation("dashboard:projects")
        job_generation = self.cache.generation("dashboard:jobs")
        cache_key = self.cache.key(
            "content",
            "dashboard",
            user_id,
            "projects",
            project_generation,
            "jobs",
            job_generation,
        )
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS:
            return DashboardStats.model_validate(cached)

        projects, total = self.list_projects_for_user(user_id, limit=10_000, offset=0)
        from app.services.job_store import RedisRenderJobStore

        active_jobs, render_seconds = RedisRenderJobStore(get_redis()).aggregate_for_projects(
            {project.id for project in projects}
        )
        result = DashboardStats(
            total_projects=total,
            active_jobs=active_jobs,
            total_render_time_hours=round(render_seconds / 3600, 2),
        )
        self.cache.set(
            cache_key,
            result.model_dump(mode="json"),
            ttl_seconds=settings.cache_list_ttl_seconds,
        )
        return result

    def get_user_settings(self, user_id: UUID) -> UserSettings | None:
        cache_key = self._object_key("user-settings", user_id)
        cached = self.cache.get(cache_key)
        if cached is not CACHE_MISS:
            return UserSettings.model_validate(cached) if cached is not None else None
        rows = self._request(
            "GET", "user_settings", params={"user_id": f"eq.{user_id}", "select": "*"}
        )
        user_settings = UserSettings.model_validate(rows[0]) if rows else None
        self.cache.set(
            cache_key, user_settings.model_dump(mode="json") if user_settings else None
        )
        return user_settings

    def upsert_user_settings(self, user_settings: UserSettings) -> UserSettings:
        payload = user_settings.model_dump(mode="json")
        try:
            rows = self._request(
                "POST",
                "user_settings",
                params={"on_conflict": "user_id"},
                body=payload,
                prefer="resolution=merge-duplicates,return=representation",
            )
        except httpx.HTTPStatusError as exc:
            error = exc.response.json() if exc.response.content else {}
            if isinstance(error, dict) and error.get("code") == "PGRST204":
                raise RuntimeError(
                    "Supabase user_settings schema is outdated; apply "
                    "20260720000000_settings_extension.sql"
                ) from exc
            raise
        if not rows:
            raise RuntimeError("Supabase settings upsert returned no row")
        saved = UserSettings.model_validate(rows[0])
        self.cache.set(
            self._object_key("user-settings", saved.user_id), saved.model_dump(mode="json")
        )
        return saved
