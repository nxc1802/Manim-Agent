from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from shared.schemas.project import Project, ProjectStatus
from shared.schemas.scene import Scene, StoryboardStatus

from backend.core.config import settings

logger = logging.getLogger(__name__)

def _service_headers() -> dict[str, str] | None:
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    if not base or not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

class SupabaseContentStore:
    """Persist Project / Scene JSON in Supabase (PostgREST)."""

    def __init__(self) -> None:
        self._headers = _service_headers()
        self._base_url = (settings.supabase_url or "").strip().rstrip("/")

    def _get_client(self) -> httpx.Client:
        return httpx.Client(headers=self._headers, timeout=30.0)

    def save_project(self, project: Project) -> None:
        if not self._headers: return
        payload = project.model_dump(mode="json")
        url = f"{self._base_url}/rest/v1/projects?id=eq.{project.id}"
        with self._get_client() as client:
            client.patch(url, json=payload)

    def get_project(self, project_id: UUID) -> Project | None:
        if not self._headers: return None
        url = f"{self._base_url}/rest/v1/projects?id=eq.{project_id}"
        with self._get_client() as client:
            r = client.get(url)
            if r.status_code == 200 and r.json():
                return Project.model_validate(r.json()[0])
        return None

    def list_projects_for_user(self, user_id: UUID) -> list[Project]:
        if not self._headers: return []
        url = f"{self._base_url}/rest/v1/projects?user_id=eq.{user_id}&order=created_at.asc"
        with self._get_client() as client:
            r = client.get(url)
            if r.status_code == 200:
                return [Project.model_validate(p) for p in r.json()]
        return []

    def save_scene(self, scene: Scene) -> None:
        if not self._headers: return
        payload = scene.model_dump(mode="json")
        url = f"{self._base_url}/rest/v1/scenes?id=eq.{scene.id}"
        with self._get_client() as client:
            client.patch(url, json=payload)

    def get_scene(self, scene_id: UUID) -> Scene | None:
        if not self._headers: return None
        url = f"{self._base_url}/rest/v1/scenes?id=eq.{scene_id}"
        with self._get_client() as client:
            r = client.get(url)
            if r.status_code == 200 and r.json():
                return Scene.model_validate(r.json()[0])
        return None

    def list_scenes_for_project(self, project_id: UUID) -> list[Scene]:
        if not self._headers: return []
        url = f"{self._base_url}/rest/v1/scenes?project_id=eq.{project_id}&order=scene_order.asc,created_at.asc"
        with self._get_client() as client:
            r = client.get(url)
            if r.status_code == 200:
                return [Scene.model_validate(s) for s in r.json()]
        return []

    def create_project(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        title: str,
        description: str | None,
        source_language: str,
        status: ProjectStatus = "draft",
    ) -> Project:
        if not self._headers:
            # Fallback for dev if no supabase? Or just error?
            raise RuntimeError("Supabase not configured")
            
        project = Project(
            id=project_id,
            user_id=user_id,
            title=title,
            description=description,
            source_language=source_language,
            status=status,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        url = f"{self._base_url}/rest/v1/projects"
        with self._get_client() as client:
            r = client.post(url, json=project.model_dump(mode="json"))
            if r.status_code >= 400:
                logger.error(f"Supabase create_project failed: {r.status_code} {r.text}")
            r.raise_for_status()
            return Project.model_validate(r.json()[0])

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
        if not self._headers:
            raise RuntimeError("Supabase not configured")
            
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
        url = f"{self._base_url}/rest/v1/scenes"
        with self._get_client() as client:
            r = client.post(url, json=scene.model_dump(mode="json"))
            if r.status_code >= 400:
                logger.error(f"Supabase create_scene failed: {r.status_code} {r.text}")
            r.raise_for_status()
            return Scene.model_validate(r.json()[0])

    def update_scene(self, scene_id: UUID, **kwargs: Any) -> Scene | None:
        if not self._headers: return None
        url = f"{self._base_url}/rest/v1/scenes?id=eq.{scene_id}"
        with self._get_client() as client:
            r = client.patch(url, json=kwargs)
            r.raise_for_status()
            return self.get_scene(scene_id)
