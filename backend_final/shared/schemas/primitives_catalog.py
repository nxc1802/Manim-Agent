from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Define the allowed types for primitive parameters
PrimitiveKind = Literal["str", "int", "float", "bool", "list", "dict", "object", "mobject", "scene"]


class PrimitiveParameter(BaseModel):
    """Schema for a single parameter of a primitive."""

    name: str
    kind: PrimitiveKind
    required: bool = True
    default: str | None = None
    description: str | None = None


class PrimitiveEntry(BaseModel):
    """Schema for a single primitive in the catalog."""

    name: str
    module: str
    description: str
    parameters: list[PrimitiveParameter]
    example: str
    tags: list[str] = Field(default_factory=list)


class PrimitivesCatalogResponse(BaseModel):
    """Schema for the full primitives catalog response."""

    version: str | int
    primitives: list[PrimitiveEntry]
