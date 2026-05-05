from __future__ import annotations

from ai_engine.rag.log_parser import parse_render_error, ParsedError
from ai_engine.rag.api_registry import ManimAPIRegistry


def build_reviewer_rag_context(error_logs: str) -> str | None:
    """Parse error -> registry lookup -> formatted markdown block for reviewer prompt.

    Returns None if no relevant entries found.
    """
    if not error_logs:
        return None
        
    # 1. Parse error
    try:
        parsed = parse_render_error(error_logs)
    except Exception:
        return None
        
    # 2. Lookup registry
    try:
        registry = ManimAPIRegistry()
        entries = registry.resolve_error(parsed.error_type, parsed.symbol)
        
        # If no entries by symbol, try similar symbols if it's an AttributeError/NameError
        if not entries and parsed.symbol:
            entries = registry.find_similar(parsed.symbol)
            
        if not entries:
            return None
            
        # 3. Format context block
        return _format_api_reference(parsed, entries)
    except Exception:
        return None


def _format_api_reference(error: ParsedError, entries: list[dict]) -> str:
    """Format as markdown block for injection into reviewer prompt."""
    lines = [
        "### 📚 MANIM_API_REFERENCE (from official ManimCE v0.20.1 docs)",
        f"**Error Context**: {error.error_type} at line {error.line_number or 'unknown'}",
        f"**Error Message**: `{error.raw_message}`",
        ""
    ]
    
    # Check for deprecated mapping specifically to call it out
    registry = ManimAPIRegistry()
    if error.symbol:
        dep = registry.lookup_deprecated(error.symbol)
        if dep:
            lines.append(f"> [!IMPORTANT]")
            lines.append(f"> `{error.symbol}` is DEPRECATED in Manim Community Edition. Use `{dep[0]}` instead.")
            lines.append("")

    for entry in entries:
        lines.append(f"#### `{entry['symbol']}` ({entry.get('module_path', 'manim')})")
        if entry.get("signature"):
            lines.append(f"- **Signature**: `{entry['signature']}`")
        if entry.get("description"):
            lines.append(f"- **Description**: {entry['description']}")
        if entry.get("example"):
            lines.append(f"- **Example**: `{entry['example']}`")
        
        # Check if any common_errors pattern matches the current error symbol
        if error.symbol:
            for err in entry.get("common_errors", []):
                import re
                if re.search(err.get("pattern", ""), error.symbol, re.I):
                    lines.append(f"- **Pro Tip**: {err['fix']}")
        
        lines.append("")
        
    return "\n".join(lines)
