from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PrimitiveKind = Literal["str", "int", "float", "bool", "list", "object", "mobject"]


class PrimitiveParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: PrimitiveKind
    required: bool = True
    default: str | None = None
    description: str | None = None


class PrimitiveEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    module: str
    description: str
    parameters: list[PrimitiveParameter] = Field(default_factory=list)
    example: str
    tags: list[str] = Field(default_factory=list)


class PrimitivesCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    primitives: list[PrimitiveEntry]
