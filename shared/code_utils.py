from __future__ import annotations

import re


def extract_python_code(text: str) -> str:
    """Extract code from ```python ... ``` or return the original text if no blocks found."""
    # Try to find a python code block
    match = re.search(r"```(?:python|py)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Try to find any code block
    match = re.search(r"```\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    return text.strip()
