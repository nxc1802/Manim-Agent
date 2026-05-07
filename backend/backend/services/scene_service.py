from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_engine.agents.builder import run_builder
from ai_engine.config import (
    default_agent_models_path,
    load_agent_models_yaml,
)
from ai_engine.llm_client import LLMClient
from ai_engine.orchestrator import (
    run_planning_phase,
    run_storyboard_phase,
)
from ai_engine.utils.storage_helper import save_agent_interaction
from shared.code_utils import extract_python_code
from shared.pipeline_log import pipeline_event
from shared.schemas.planner_output import PlannerOutput
from shared.schemas.scene import Scene
from shared.schemas.voice_segments import VoiceSegmentTimestamps
from worker.tasks import render_manim_scene
from worker.tts_tasks import synthesize_voice

from backend.core.config import settings
from backend.core.errors import ResourceNotFound
from backend.db.base import ContentStore
from backend.services.code_sandbox import SandboxLimits, validate_manim_code
from backend.services.job_store import RedisRenderJobStore
from backend.services.supabase_voice_rest import insert_voice_job_row
from backend.services.sync_engine_logic import align_beats_to_audio
from backend.services.voice_job_store import RedisVoiceJobStore

logger = logging.getLogger(__name__)


class SceneService:
    def __init__(
        self,
        store: ContentStore,
        llm: LLMClient | None = None,
        job_store: RedisRenderJobStore | None = None,
        vstore: RedisVoiceJobStore | None = None,
    ):
        self.store = store
        self.llm = llm
        self.job_store = job_store
        self.vstore = vstore

    def _agent_models_path(self) -> Path:
        if settings.agent_models_yaml:
            return Path(settings.agent_models_yaml).expanduser()
        return default_agent_models_path()

    async def generate_storyboard(
        self, scene_id: UUID, user_id: UUID, brief_override: str | None = None
    ) -> Scene:
        scene = self.store.get_scene(scene_id)
        if not scene:
            raise ResourceNotFound("Scene", scene_id)

        from backend.api.access import project_readable_by_user
        project = project_readable_by_user(self.store, scene.project_id, user_id)

        if scene.storyboard_status == "approved":
            raise ValueError("Storyboard already approved")

        yaml_data = load_agent_models_yaml(self._agent_models_path())
        
        # Helper to get params (simplified for now, ideally passed in)
        from backend.api.deps import get_agent_llm_params
        params = get_agent_llm_params("director")

        target_scenes = project.target_scenes
        if target_scenes is None:
            target_scenes = yaml_data.get("agents", {}).get("director", {}).get("target_scenes")

        pipeline_event(
            "service.scenes",
            "storyboard_start",
            "Director: generating storyboard",
            scene_id=str(scene_id),
            project_id=str(scene.project_id),
        )

        if not self.llm:
            raise RuntimeError("LLM client not provided to SceneService")

        text, _pv, _metrics, _sys, _usr = await run_storyboard_phase(
            llm=self.llm,
            model=params.model,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            project_title=project.title,
            project_description=project.description,
            target_scenes=target_scenes,
            extra_brief=brief_override,
        )
        save_agent_interaction(scene.project_id, "director", "storyboard", _sys, _usr, text)

        updated = self.store.update_scene(
            scene_id, storyboard_text=text, storyboard_status="pending_review"
        )
        pipeline_event(
            "service.scenes",
            "storyboard_ok",
            "Director: storyboard generated",
            scene_id=str(scene_id),
            project_id=str(scene.project_id),
        )
        assert updated is not None
        return updated

    async def run_planner(self, scene_id: UUID, user_id: UUID) -> Scene:
        scene = self.store.get_scene(scene_id)
        if not scene:
            raise ResourceNotFound("Scene", scene_id)

        from backend.api.access import project_readable_by_user
        project = project_readable_by_user(self.store, scene.project_id, user_id)

        if scene.storyboard_status != "approved":
            raise ValueError("Storyboard must be approved before planning")

        use_primitives = project.config.get("use_primitives", True)

        from backend.api.deps import get_agent_llm_params, get_runtime_limits
        params = get_agent_llm_params("planner")
        rt = get_runtime_limits()

        pipeline_event(
            "service.scenes",
            "plan_start",
            "Planner: generating execution plan",
            scene_id=str(scene_id),
            project_id=str(scene.project_id),
        )

        if not self.llm:
            raise RuntimeError("LLM client not provided to SceneService")

        plan, _pv, _metrics, _sys, _usr = await run_planning_phase(
            llm=self.llm,
            model=params.model,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            storyboard_text=scene.storyboard_text or "",
            use_primitives=use_primitives,
            request_timeout_seconds=rt.llm_timeout_seconds("planner"),
        )
        save_agent_interaction(scene.project_id, "planner", "plan", _sys, _usr, plan)

        updated = self.store.update_scene(
            scene_id,
            planner_output=plan.model_dump(mode="json"),
            plan_status="pending_review",
            voice_script_status="pending_review",
        )
        pipeline_event(
            "service.scenes",
            "plan_ok",
            "Planner: plan generated",
            scene_id=str(scene_id),
            project_id=str(scene.project_id),
        )
        assert updated is not None
        return updated

    def sync_timeline(self, scene_id: UUID, user_id: UUID) -> Scene:
        scene = self.store.get_scene(scene_id)
        if not scene:
            raise ResourceNotFound("Scene", scene_id)

        from backend.api.access import project_readable_by_user
        project_readable_by_user(self.store, scene.project_id, user_id)

        if not scene.planner_output:
            raise ValueError("Missing execution plan for synchronization")
        if not scene.timestamps:
            raise ValueError("Missing voice timestamps. Please run TTS first.")

        plan = PlannerOutput.model_validate(scene.planner_output)
        ts = VoiceSegmentTimestamps.model_validate(scene.timestamps)

        sync_segments = align_beats_to_audio(plan, ts)

        updated = self.store.update_scene(scene_id, sync_segments=sync_segments)
        pipeline_event(
            "service.scenes",
            "sync_ok",
            "Sync: beats aligned to audio",
            scene_id=str(scene_id),
            project_id=str(scene.project_id),
        )
        assert updated is not None
        return updated

    async def generate_code(
        self, scene_id: UUID, user_id: UUID, enqueue_preview: bool = False
    ) -> tuple[Scene, UUID | None]:
        scene = self.store.get_scene(scene_id)
        if not scene:
            raise ResourceNotFound("Scene", scene_id)

        from backend.api.access import project_readable_by_user
        project = project_readable_by_user(self.store, scene.project_id, user_id)

        if scene.storyboard_status != "approved":
            raise ValueError("Storyboard must be approved before code generation")

        use_primitives = project.config.get("use_primitives", True)
        plan = PlannerOutput.model_validate(scene.planner_output)
        excerpt = scene.storyboard_text[:4000] if scene.storyboard_text else None

        from backend.api.deps import get_agent_llm_params, get_runtime_limits
        params = get_agent_llm_params("builder")
        rt = get_runtime_limits()

        if not self.llm:
            raise RuntimeError("LLM client not provided to SceneService")

        raw_code, _pv, _bm, _sys, _usr = await run_builder(
            llm=self.llm,
            model=params.model,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            planner=plan,
            sync_segments=scene.sync_segments,
            storyboard_excerpt=excerpt,
            use_primitives=use_primitives,
            request_timeout_seconds=rt.llm_timeout_seconds("builder"),
        )
        code = extract_python_code(raw_code)
        limits = SandboxLimits(max_bytes=settings.max_manim_code_bytes)
        validate_manim_code(code, limits=limits)

        updated = self.store.update_scene(
            scene_id, manim_code=code.strip(), manim_code_version=scene.manim_code_version + 1
        )
        assert updated is not None

        preview_job_id: UUID | None = None
        if enqueue_preview:
            if not self.job_store:
                raise RuntimeError("Job store not provided to SceneService")
            job_id = uuid4()
            self.job_store.create_queued_job(
                job_id=job_id,
                project_id=scene.project_id,
                scene_id=scene_id,
                job_type="preview",
                render_quality="720p",
                webhook_url=None,
                docker_image_tag=settings.worker_image_tag,
            )
            render_manim_scene.apply_async(args=[str(job_id)])
            preview_job_id = job_id

        return updated, preview_job_id

    def enqueue_voice(
        self, scene_id: UUID, user_id: UUID, voice_script_override: str | None = None
    ) -> UUID:
        scene = self.store.get_scene(scene_id)
        if not scene:
            raise ResourceNotFound("Scene", scene_id)

        from backend.api.access import project_readable_by_user
        project_readable_by_user(self.store, scene.project_id, user_id)

        if scene.storyboard_status != "approved":
            raise ValueError("Storyboard not approved")

        text = (voice_script_override or scene.voice_script or scene.storyboard_text or "").strip()
        if not text:
            raise ValueError("Missing synthesis text (script or storyboard)")

        if not self.vstore:
            raise RuntimeError("Voice job store not provided to SceneService")

        job_id = uuid4()
        metadata: dict[str, Any] = {"synthesis_text": text}
        if voice_script_override:
            metadata["voice_script_override"] = voice_script_override.strip()

        job = self.vstore.create_queued_job(
            job_id=job_id,
            project_id=scene.project_id,
            scene_id=scene_id,
            metadata=metadata,
            voice_engine="piper",
            docker_image_tag=settings.tts_worker_image_tag,
        )
        insert_voice_job_row(job)
        synthesize_voice.apply_async(args=[str(job_id)])
        return job_id
