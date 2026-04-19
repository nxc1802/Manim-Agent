from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SignedVideoUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signed_url: str = Field(min_length=8)
    expires_in_seconds: int = Field(ge=1)
