from __future__ import annotations

import json
import re
from typing import Any


def strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", t, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def parse_json_object(text: str) -> dict[str, Any]:
    raw = strip_json_fence(text)
    data = json.loads(raw)
    if not isinstance(data, dict):
        msg = "Expected JSON object"
        raise ValueError(msg)
    return data
