from __future__ import annotations

import json
import re
from typing import Any


def strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", t, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def parse_json_object(text: str, list_key: str = "beats") -> dict[str, Any]:
    """Tries to extract and parse a JSON object from text with high resilience."""
    # 1. Strip markdown fences
    raw = strip_json_fence(text)
    
    # 2. Try simple load first
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {list_key: data}
    except Exception:
        pass
    
    # 3. Locate the first { and last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        snippet = raw[start : end + 1]
        try:
            # Basic cleanup: remove trailing commas before } or ]
            snippet = re.sub(r",\s*([}\]])", r"\1", snippet)
            data = json.loads(snippet)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
            
    # 4. If it's a list [ ... ]
    start_l = raw.find("[")
    end_l = raw.rfind("]")
    if start_l != -1 and end_l != -1:
        snippet_l = raw[start_l : end_l + 1]
        try:
            snippet_l = re.sub(r",\s*([}\]])", r"\1", snippet_l)
            data_l = json.loads(snippet_l)
            if isinstance(data_l, list):
                return {list_key: data_l}
        except Exception:
            pass

    # Final attempt at raw loads
    try:
        return json.loads(raw)
    except Exception as exc:
        msg = f"Failed to parse resilient JSON: {exc}. Original: {text[:200]}..."
        raise ValueError(msg) from exc
