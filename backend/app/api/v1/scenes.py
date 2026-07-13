from fastapi import APIRouter

from app.api.v1.scenes_crud import router as crud_router

router = APIRouter(tags=["scenes"])
router.include_router(crud_router)
