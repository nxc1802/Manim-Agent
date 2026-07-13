from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from app.core.config import settings
from app.db.base import ContentStore
from redis import Redis
from shared.schemas.project import DashboardStats, Project, ProjectStatus
from shared.schemas.scene import Scene, StoryboardStatus


def _project_key(project_id: UUID) -> str:
    return f"{settings.redis_prefix}:project:{project_id}"


def _scene_key(scene_id: UUID) -> str:
    return f"{settings.redis_prefix}:scene:{scene_id}"


class RedisContentStore(ContentStore):
    """Development persistence only; production requires Supabase/Postgres."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    def _user_projects_key(self, user_id: UUID) -> str:
        return f"{settings.redis_prefix}:user_projects:{user_id}"

    def _project_scenes_key(self, project_id: UUID) -> str:
        return f"{settings.redis_prefix}:project_scenes:{project_id}"

    def _save_project(self, project: Project) -> None:
        self._redis.set(_project_key(project.id), json.dumps(project.model_dump(mode="json")))
        self._redis.sadd(self._user_projects_key(project.user_id), str(project.id))

    def _save_scene(self, scene: Scene) -> None:
        self._redis.set(_scene_key(scene.id), json.dumps(scene.model_dump(mode="json")))

    def get_project(self, project_id: UUID) -> Project | None:
        raw = self._redis.get(_project_key(project_id))
        return Project.model_validate(json.loads(cast(str, raw))) if raw else None

    def list_projects_for_user(self, user_id: UUID, *, limit: int, offset: int) -> tuple[list[Project], int]:
        ids = sorted(cast(set[str], self._redis.smembers(self._user_projects_key(user_id))))
        items = [self.get_project(UUID(value)) for value in ids[offset : offset + limit]]
        projects = sorted((item for item in items if item), key=lambda item: item.created_at, reverse=True)
        return projects, len(ids)

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
            id=project_id, user_id=user_id, title=title, description=description,
            source_language=source_language, target_scenes=target_scenes, status=status,
            config=config or {}, created_at=now, updated_at=now,
        )
        self._save_project(project)
        return project

    def update_project(self, project_id: UUID, **fields: Any) -> Project | None:
        project = self.get_project(project_id)
        if not project:
            return None
        updated = project.model_copy(update={**fields, "updated_at": datetime.now(tz=UTC)})
        self._save_project(updated)
        return updated

    def delete_project(self, project_id: UUID) -> None:
        project = self.get_project(project_id)
        if project:
            self._redis.delete(_project_key(project_id), self._project_scenes_key(project_id))
            self._redis.srem(self._user_projects_key(project.user_id), str(project_id))

    def get_scene(self, scene_id: UUID) -> Scene | None:
        raw = self._redis.get(_scene_key(scene_id))
        return Scene.model_validate(json.loads(cast(str, raw))) if raw else None

    def list_scenes_for_project(self, project_id: UUID, *, limit: int, offset: int) -> tuple[list[Scene], int]:
        ids = cast(list[str], self._redis.lrange(self._project_scenes_key(project_id), 0, -1))
        items = [self.get_scene(UUID(value)) for value in ids[offset : offset + limit]]
        scenes = sorted((item for item in items if item), key=lambda item: item.scene_order)
        return scenes, len(ids)

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
        now = datetime.now(tz=UTC)
        scene = Scene(
            id=scene_id, project_id=project_id, scene_order=scene_order,
            storyboard_text=storyboard_text, voice_script=voice_script,
            storyboard_status=storyboard_status, created_at=now, updated_at=now,
        )
        self._save_scene(scene)
        self._redis.rpush(self._project_scenes_key(project_id), str(scene.id))
        return scene

    def update_scene(self, scene_id: UUID, **fields: Any) -> Scene | None:
        scene = self.get_scene(scene_id)
        if not scene:
            return None
        updated = scene.model_copy(update={**fields, "updated_at": datetime.now(tz=UTC)})
        self._save_scene(updated)
        return updated

    def delete_scene(self, scene_id: UUID) -> None:
        scene = self.get_scene(scene_id)
        if scene:
            self._redis.delete(_scene_key(scene_id))
            self._redis.lrem(self._project_scenes_key(scene.project_id), 0, str(scene_id))

    def get_dashboard_stats(self, user_id: UUID) -> DashboardStats:
        total = self._redis.scard(self._user_projects_key(user_id))
        return DashboardStats(total_projects=total, active_jobs=0, total_tokens_used=0, total_render_time_hours=0.0)


def get_content_store() -> ContentStore:
    from app.db.supabase_store import SupabaseContentStore
    from app.services.redis_client import get_redis

    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseContentStore()
    if settings.app_env.lower() in {"production", "prod", "staging"}:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required outside development")
    return RedisContentStore(get_redis())
