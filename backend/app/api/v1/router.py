from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import chat, hitl, internal, jobs, projects, render, scenes, users, ws

api_router = APIRouter()
api_router.include_router(users.router, prefix="/users")
api_router.include_router(projects.router, prefix="/projects")
api_router.include_router(render.router, prefix="/projects")
api_router.include_router(scenes.router, prefix="/scenes")
api_router.include_router(hitl.router, prefix="/projects")
api_router.include_router(jobs.router)
api_router.include_router(chat.router)
api_router.include_router(ws.router)

internal_router = APIRouter()
internal_router.include_router(internal.router)
