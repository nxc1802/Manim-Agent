from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from backend.core.config import settings
from backend.db.base import ContentStore
from redis import Redis
from shared.schemas.project import Project, ProjectStatus
from shared.schemas.scene import Scene, SceneCodeHistory, StoryboardStatus


def _project_key(project_id: UUID) -> str:
    return f"{settings.redis_prefix}:project:{project_id}"


def _scene_key(scene_id: UUID) -> str:
    return f"{settings.redis_prefix}:scene:{scene_id}"


def _user_projects_key(user_id: UUID) -> str:
    return f"{settings.redis_prefix}:user_projects:{user_id}"


def _project_scenes_key(project_id: UUID) -> str:
    return f"{settings.redis_prefix}:project_scenes:{project_id}"


class RedisContentStore(ContentStore):
    """Persist `Project` / `Scene` JSON in Redis (Phase 4; Supabase in Phase 6)."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    def save_project(self, project: Project) -> None:
        payload = project.model_dump(mode="json")
        self._r.set(_project_key(project.id), json.dumps(payload))
        self._r.sadd(_user_projects_key(project.user_id), str(project.id))

    def get_project(self, project_id: UUID) -> Project | None:
        raw = self._r.get(_project_key(project_id))
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(cast(str, raw))
        return Project.model_validate(data)

    def list_projects_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        ids = cast(set[str], self._r.smembers(_user_projects_key(user_id)))
        all_ids = sorted(ids)
        total = len(all_ids)

        subset = all_ids[offset : offset + limit]
        out: list[Project] = []
        for sid in subset:
            p = self.get_project(UUID(sid))
            if p is not None:
                out.append(p)
        out.sort(key=lambda p: p.created_at)
        return out, total

    def save_scene(self, scene: Scene) -> None:
        payload = scene.model_dump(mode="json")
        self._r.set(_scene_key(scene.id), json.dumps(payload))

    def get_scene(self, scene_id: UUID) -> Scene | None:
        raw = self._r.get(_scene_key(scene_id))
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(cast(str, raw))
        return Scene.model_validate(data)

    def add_scene_to_project_index(self, scene: Scene) -> None:
        key = _project_scenes_key(scene.project_id)
        sid = str(scene.id)
        existing = list(cast(list[str], self._r.lrange(key, 0, -1)))
        if sid not in existing:
            self._r.rpush(key, sid)

    def list_scenes_for_project(
        self,
        project_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Scene], int]:
        all_ids = cast(list[str], self._r.lrange(_project_scenes_key(project_id), 0, -1))
        total = len(all_ids)
        subset = all_ids[offset : offset + limit]

        scenes: list[Scene] = []
        for raw_id in subset:
            s = self.get_scene(UUID(raw_id))
            if s is not None:
                scenes.append(s)
        scenes.sort(key=lambda s: (s.scene_order, s.created_at))
        return scenes, total

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
    ) -> Project:
        now = datetime.now(tz=UTC)
        project = Project(
            id=project_id,
            user_id=user_id,
            title=title,
            description=description,
            source_language=source_language,
            target_scenes=target_scenes,
            config=config or {},
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.save_project(project)
        return project

    def touch_project(self, project_id: UUID) -> Project | None:
        project = self.get_project(project_id)
        if project is None:
            return None
        updated = project.model_copy(update={"updated_at": datetime.now(tz=UTC)})
        self.save_project(updated)
        return updated

    def update_scene(self, scene_id: UUID, **fields: Any) -> Scene | None:
        scene = self.get_scene(scene_id)
        if scene is None:
            return None
        data = dict(fields)
        if "updated_at" not in data:
            data["updated_at"] = datetime.now(tz=UTC)
        updated = scene.model_copy(update=data)
        self.save_scene(updated)
        return updated

    def create_scene(
        self,
        *,
        scene_id: UUID,
        project_id: UUID,
        scene_order: int,
        storyboard_text: str | None = None,
        voice_script: str | None = None,
        storyboard_status: StoryboardStatus = "missing",
    ) -> Scene:
        now = datetime.now(tz=UTC)
        scene = Scene(
            id=scene_id,
            project_id=project_id,
            scene_order=scene_order,
            storyboard_status=storyboard_status,
            storyboard_text=storyboard_text,
            voice_script=voice_script,
            planner_output=None,
            sync_segments=None,
            manim_code=None,
            manim_code_version=1,
            audio_url=None,
            timestamps=None,
            duration_seconds=None,
            review_loop_status="idle",
            created_at=now,
            updated_at=now,
        )
        self.save_scene(scene)
        self.add_scene_to_project_index(scene)
        self.touch_project(project_id)
        return scene

    def save_scene_code_history(self, history: SceneCodeHistory) -> None:
        key = f"{settings.redis_prefix}:scene_code_history:{history.scene_id}"
        payload = history.model_dump(mode="json")
        self._r.rpush(key, json.dumps(payload))

    def resolve_asset_local_path(self, asset_url: str | None) -> Path | None:
        """Handle file:// scheme for local/Redis persistence."""
        if not asset_url:
            return None
        if not asset_url.startswith("file://"):
            return None
        p = Path(asset_url.replace("file://", "", 1))
        return p if p.is_file() else None

    def update_project(self, project_id: UUID, **fields: Any) -> Project | None:
        project = self.get_project(project_id)
        if project is None:
            return None
        data = dict(fields)
        if "updated_at" not in data:
            data["updated_at"] = datetime.now(tz=UTC)
        updated = project.model_copy(update=data)
        self.save_project(updated)
        return updated

    def delete_project(self, project_id: UUID) -> None:
        project = self.get_project(project_id)
        if project:
            self._r.delete(_project_key(project_id))
            self._r.srem(_user_projects_key(project.user_id), str(project_id))
            self._r.delete(_project_scenes_key(project_id))

    def delete_scene(self, scene_id: UUID) -> None:
        scene = self.get_scene(scene_id)
        if scene:
            self._r.delete(_scene_key(scene_id))
            self._r.lrem(_project_scenes_key(scene.project_id), 0, str(scene_id))

    def batch_upsert_scenes(self, project_id: UUID, scenes: list[Scene]) -> list[Scene]:
        for s in scenes:
            self.save_scene(s)
            self.add_scene_to_project_index(s)
        return scenes


def get_content_store() -> ContentStore:
    """Prefer Supabase for project/scene persistence if configured; fallback to Redis (dev only)."""
    from backend.core.config import settings
    from backend.db.supabase_store import SupabaseContentStore
    from backend.services.redis_client import get_redis

    is_configured = bool(settings.supabase_url and settings.supabase_service_role_key)

    if is_configured:
        return SupabaseContentStore()

    if settings.app_env == "production":
        msg = (
            "CRITICAL: Supabase must be configured for content persistence in production "
            "(missing SUPABASE_URL or KEY)."
        )
        raise ValueError(msg)

    return RedisContentStore(get_redis())
