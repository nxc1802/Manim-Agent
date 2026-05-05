from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Any

# Define the allowed types for primitive parameters
PrimitiveKind = Literal[
    "str", "int", "float", "bool", "list", "dict", "object", "mobject", "scene"
]

class PrimitiveParameter(BaseModel):
    """Schema for a single parameter of a primitive."""
    name: str
    kind: PrimitiveKind
    required: bool = True
    default: Optional[str] = None
    description: Optional[str] = None

class PrimitiveEntry(BaseModel):
    """Schema for a single primitive in the catalog."""
    name: str
    module: str
    description: str
    parameters: List[PrimitiveParameter]
    example: str
    tags: List[str] = Field(default_factory=list)

class PrimitivesCatalogResponse(BaseModel):
    """Schema for the full primitives catalog response."""
    version: str | int
    primitives: List[PrimitiveEntry]
