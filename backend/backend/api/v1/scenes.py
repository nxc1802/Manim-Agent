from __future__ import annotations

from ai_engine.builder_loop import run_builder_loop_phase as run_builder_loop_phase
from fastapi import APIRouter
from worker.tts_tasks import synthesize_voice as synthesize_voice

from backend.api.v1.scenes_crud import router as crud_router
from backend.api.v1.scenes_pipeline import router as pipeline_router
from backend.api.v1.scenes_review import router as review_router
from backend.api.v1.scenes_versions import router as versions_router

router = APIRouter(tags=["scenes"])
router.include_router(crud_router)
router.include_router(pipeline_router)
router.include_router(review_router)
router.include_router(versions_router)
