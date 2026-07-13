from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared.schemas.user import UserSettings, UserSettingsUpdate

from app.api.deps import ContentStore, get_content_store, get_request_user_id

router = APIRouter(tags=["users"])


@router.get("/me/settings", response_model=UserSettings, summary="Get current user settings")
def get_settings(
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> UserSettings:
    settings = store.get_user_settings(user_id)
    if not settings:
        # Return default settings if none exist yet
        settings = UserSettings(user_id=user_id)
    return settings


@router.patch("/me/settings", response_model=UserSettings, summary="Update current user settings")
def update_settings(
    body: UserSettingsUpdate,
    user_id: UUID = Depends(get_request_user_id),  # noqa: B008
    store: ContentStore = Depends(get_content_store),  # noqa: B008
) -> UserSettings:
    current = store.get_user_settings(user_id)
    if not current:
        current = UserSettings(user_id=user_id)
    
    updated_data = current.model_dump()
    update_data = body.model_dump(exclude_unset=True)
    updated_data.update(update_data)
    
    new_settings = UserSettings.model_validate(updated_data)
    return store.upsert_user_settings(new_settings)
