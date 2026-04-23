from __future__ import annotations

from fastapi import APIRouter

from backend.api.v1 import jobs, primitives, projects, render, scenes, voice_jobs, ws, pipeline_runs

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects")
api_router.include_router(render.router, prefix="/projects")
api_router.include_router(pipeline_runs.router, prefix="")
api_router.include_router(scenes.router, prefix="/scenes")
api_router.include_router(primitives.router, prefix="/primitives")
api_router.include_router(jobs.router, prefix="")
api_router.include_router(voice_jobs.router, prefix="")
api_router.include_router(ws.router, prefix="")
