from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, TypedDict, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from shared.constants import ReviewLoopMode

logger = logging.getLogger(__name__)


class ProjectState(TypedDict):
    project_id: UUID
    user_id: UUID
    scene_ids: list[UUID]
    errors: dict[str, str]
    storyboard_texts: dict[str, str]
    plan_status: dict[str, str]
    voice_job_ids: dict[str, str]
    sync_status: dict[str, str]
    builder_loop_status: dict[str, str]


class SubSceneState(TypedDict):
    project_id: UUID
    user_id: UUID
    scene_id: UUID
    error: str | None
    storyboard_text: str | None
    plan_status: str | None
    voice_job_id: str | None
    sync_status: str | None
    builder_loop_status: str | None


async def sub_director_node(state: SubSceneState, config: RunnableConfig) -> dict[str, Any]:
    """Director Node for a single scene."""
    if state.get("error"):
        return {}
    configurable = config.get("configurable", {})
    store = configurable["store"]
    llm = configurable["llm"]
    user_id = state["user_id"]
    scene_id = state["scene_id"]

    from backend.services.scene_service import SceneService

    service = SceneService(store, llm=llm)

    try:
        scene = store.get_scene(scene_id)
        if not scene:
            return {}
        if scene.storyboard_status in ("approved", "pending_review") and scene.storyboard_text:
            return {"storyboard_text": scene.storyboard_text}

        updated = await service.generate_storyboard(scene_id, user_id)
        # Auto-approve storyboard for non-interactive parallel run
        store.update_scene(scene_id, storyboard_status="approved")
        return {"storyboard_text": updated.storyboard_text or ""}
    except Exception as e:
        logger.exception("Director node failed for scene %s", scene_id)
        return {"error": f"Storyboard generation failed: {e}"}


async def sub_planner_node(state: SubSceneState, config: RunnableConfig) -> dict[str, Any]:
    """Planner Node for a single scene."""
    if state.get("error"):
        return {}
    configurable = config.get("configurable", {})
    store = configurable["store"]
    llm = configurable["llm"]
    user_id = state["user_id"]
    scene_id = state["scene_id"]

    from backend.services.scene_service import SceneService

    service = SceneService(store, llm=llm)

    try:
        scene = store.get_scene(scene_id)
        if not scene:
            return {}
        if scene.planner_output:
            if scene.plan_status != "approved":
                store.update_scene(scene_id, plan_status="approved")
            return {"plan_status": "approved"}

        # Ensure storyboard is marked approved
        if scene.storyboard_status != "approved":
            store.update_scene(scene_id, storyboard_status="approved")

        await service.run_planner(scene_id, user_id)
        store.update_scene(scene_id, plan_status="approved")
        return {"plan_status": "approved"}
    except Exception as e:
        logger.exception("Planner node failed for scene %s", scene_id)
        return {"error": f"Planning failed: {e}"}


async def sub_voice_node(state: SubSceneState, config: RunnableConfig) -> dict[str, Any]:
    """Voice Node for a single scene."""
    if state.get("error"):
        return {}
    configurable = config.get("configurable", {})
    store = configurable["store"]
    vstore = configurable["vstore"]
    user_id = state["user_id"]
    scene_id = state["scene_id"]

    from backend.services.scene_service import SceneService

    service = SceneService(store, vstore=vstore)

    try:
        scene = store.get_scene(scene_id)
        if not scene:
            return {}
        if scene.timestamps:
            if scene.voice_script_status != "approved":
                store.update_scene(scene_id, voice_script_status="approved")
            return {}

        if scene.voice_script_status != "approved":
            store.update_scene(scene_id, voice_script_status="approved")

        job_id = service.enqueue_voice(scene_id, user_id)

        # Poll for TTS task completion
        start_time = time.monotonic()
        while True:
            job = vstore.get(job_id)
            if job and job.status == "completed":
                break
            if job and job.status == "failed":
                raise RuntimeError(f"TTS job failed: {job.error}")
            if time.monotonic() - start_time > 120:
                raise TimeoutError("TTS synthesis timed out after 120s")
            await asyncio.sleep(1)
        return {"voice_job_id": str(job_id)}
    except Exception as e:
        logger.exception("Voice node failed for scene %s", scene_id)
        return {"error": f"Voice synthesis failed: {e}"}


async def sub_sync_node(state: SubSceneState, config: RunnableConfig) -> dict[str, Any]:
    """Sync Node for a single scene."""
    if state.get("error"):
        return {}
    configurable = config.get("configurable", {})
    store = configurable["store"]
    user_id = state["user_id"]
    scene_id = state["scene_id"]

    from backend.services.scene_service import SceneService

    service = SceneService(store)

    try:
        scene = store.get_scene(scene_id)
        if not scene:
            return {}
        if scene.sync_segments:
            return {"sync_status": "synced"}

        if not scene.timestamps:
            raise ValueError("Missing voice timestamps for timeline sync")

        service.sync_timeline(scene_id, user_id)
        return {"sync_status": "synced"}
    except Exception as e:
        logger.exception("Sync node failed for scene %s", scene_id)
        return {"error": f"Timeline synchronization failed: {e}"}


async def sub_builder_loop_node(state: SubSceneState, config: RunnableConfig) -> dict[str, Any]:
    """Builder Loop Node for a single scene."""
    if state.get("error"):
        return {}
    configurable = config.get("configurable", {})
    store = configurable["store"]
    job_store = configurable["job_store"]
    llm = configurable["llm"]
    yaml_data = configurable["yaml_data"]
    rt = configurable["runtime_limits"]
    mode = configurable.get("mode", ReviewLoopMode.HITL)
    extra_rounds = configurable.get("extra_rounds")
    scene_id = state["scene_id"]

    from ai_engine.builder_loop import run_builder_loop_phase

    try:
        scene = store.get_scene(scene_id)
        if not scene:
            return {}
        if scene.review_loop_status == "completed" and scene.manim_code:
            return {"builder_loop_status": "completed"}

        _, report = await run_builder_loop_phase(
            scene_id=scene_id,
            store=store,
            job_store=job_store,
            llm=llm,
            yaml_data=yaml_data,
            runtime_limits=rt,
            preview_poll_timeout_seconds=float(rt.preview_poll_timeout_seconds),
            mode=mode,
            extra_rounds=extra_rounds,
        )

        if report.get("status") == "failed":
            raise RuntimeError(f"Builder review loop failed: {report.get('error')}")

        return {"builder_loop_status": "completed"}
    except Exception as e:
        logger.exception("Builder loop node failed for scene %s", scene_id)
        return {"error": f"Builder loop execution failed: {e}"}


# Compile sub-scene pipeline workflow
sub_workflow = StateGraph(SubSceneState)
sub_workflow.add_node("director", sub_director_node)
sub_workflow.add_node("planner", sub_planner_node)
sub_workflow.add_node("voice", sub_voice_node)
sub_workflow.add_node("sync", sub_sync_node)
sub_workflow.add_node("builder_loop", sub_builder_loop_node)

sub_workflow.add_edge(START, "director")
sub_workflow.add_edge("director", "planner")
sub_workflow.add_edge("planner", "voice")
sub_workflow.add_edge("voice", "sync")
sub_workflow.add_edge("sync", "builder_loop")
sub_workflow.add_edge("builder_loop", END)

sub_app = sub_workflow.compile()


async def parallel_scenes_node(state: ProjectState, config: RunnableConfig) -> dict[str, Any]:
    """Orchestrates all sub-scenes in parallel pipelines concurrently."""
    scene_ids = state["scene_ids"]
    project_id = state["project_id"]
    user_id = state["user_id"]

    async def execute_pipeline(scene_id: UUID) -> tuple[UUID, dict[str, Any]]:
        init_sub_state = SubSceneState(
            project_id=project_id,
            user_id=user_id,
            scene_id=scene_id,
            error=None,
            storyboard_text=None,
            plan_status=None,
            voice_job_id=None,
            sync_status=None,
            builder_loop_status=None,
        )
        res = await sub_app.ainvoke(init_sub_state, config=config)
        return scene_id, res

    results = await asyncio.gather(*(execute_pipeline(sid) for sid in scene_ids))

    errors = {}
    storyboard_texts = {}
    plan_status = {}
    voice_job_ids = {}
    sync_status = {}
    builder_loop_status = {}

    for sid, res in results:
        sid_str = str(sid)
        if res.get("error"):
            errors[sid_str] = res["error"]
        if res.get("storyboard_text"):
            storyboard_texts[sid_str] = res["storyboard_text"]
        if res.get("plan_status"):
            plan_status[sid_str] = res["plan_status"]
        if res.get("voice_job_id"):
            voice_job_ids[sid_str] = res["voice_job_id"]
        if res.get("sync_status"):
            sync_status[sid_str] = res["sync_status"]
        if res.get("builder_loop_status"):
            builder_loop_status[sid_str] = res["builder_loop_status"]

    return {
        "errors": errors,
        "storyboard_texts": storyboard_texts,
        "plan_status": plan_status,
        "voice_job_ids": voice_job_ids,
        "sync_status": sync_status,
        "builder_loop_status": builder_loop_status,
    }


# Construct StateGraph
workflow = StateGraph(ProjectState)
workflow.add_node("parallel_scenes", parallel_scenes_node)

workflow.add_edge(START, "parallel_scenes")
workflow.add_edge("parallel_scenes", END)

app = workflow.compile()


async def run_project_workflow(
    *,
    project_id: UUID,
    user_id: UUID,
    scene_ids: list[UUID],
    store: Any,
    vstore: Any,
    job_store: Any,
    llm: Any,
    yaml_data: dict[str, Any],
    runtime_limits: Any,
    mode: ReviewLoopMode = ReviewLoopMode.HITL,
    extra_rounds: int | None = None,
) -> dict[str, Any]:
    """Helper function to execute the project-level LangGraph workflow."""
    initial_state = ProjectState(
        project_id=project_id,
        user_id=user_id,
        scene_ids=scene_ids,
        errors={},
        storyboard_texts={},
        plan_status={},
        voice_job_ids={},
        sync_status={},
        builder_loop_status={},
    )

    config: RunnableConfig = {
        "configurable": {
            "store": store,
            "vstore": vstore,
            "job_store": job_store,
            "llm": llm,
            "yaml_data": yaml_data,
            "runtime_limits": runtime_limits,
            "mode": mode,
            "extra_rounds": extra_rounds,
        }
    }

    final_state = await app.ainvoke(initial_state, config=config)
    return cast(dict[str, Any], final_state)

