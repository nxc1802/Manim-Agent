from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedError:
    error_type: str          # "AttributeError", "TypeError", "ImportError", "NameError", "SyntaxError", etc.
    symbol: str | None       # Extracted symbol: "play_text", "ShowCreation", etc.
    invalid_arg: str | None  # For TypeError: what arg was wrong
    traceback_tail: str      # Last few lines of traceback
    line_number: int | None  # Extracted from "line XX" in traceback
    raw_message: str


def parse_render_error(error_logs: str) -> ParsedError:
    """Extract structured error info from Manim render logs."""
    
    # 1. Get the last line (the error message itself)
    lines = [l.strip() for l in error_logs.strip().split("\n") if l.strip()]
    if not lines:
        return ParsedError("UnknownError", None, None, "", None, error_logs)
        
    last_line = lines[-1]
    
    # 2. Extract Traceback Tail
    traceback_tail = "\n".join(lines[-5:]) if len(lines) >= 5 else "\n".join(lines)
    
    # 3. Extract Line Number
    line_match = re.search(r'File ".*", line (\d+)', error_logs)
    line_number = int(line_match.group(1)) if line_match else None
    
    # 4. Classification & Symbol Extraction
    error_type = "UnknownError"
    symbol = None
    invalid_arg = None
    
    # AttributeError: 'Scene' object has no attribute 'play_text'
    if "AttributeError" in last_line:
        error_type = "AttributeError"
        match = re.search(r"has no attribute '([^']+)'", last_line)
        if match:
            symbol = match.group(1)
            
    # NameError: name 'ShowCreation' is not defined
    elif "NameError" in last_line:
        error_type = "NameError"
        match = re.search(r"name '([^']+)' is not defined", last_line)
        if match:
            symbol = match.group(1)
            
    # TypeError: play() got an unexpected keyword argument 'run_time_extra'
    elif "TypeError" in last_line:
        error_type = "TypeError"
        # Function/Class match: "TypeError: play() got..."
        match_func = re.search(r"(?:TypeError:\s*)?(\w+)\(\)", last_line)
        if match_func:
            symbol = match_func.group(1)
        # Arg match
        match_arg = re.search(r"unexpected keyword argument '([^']+)'", last_line)
        if match_arg:
            invalid_arg = match_arg.group(1)
            
    # ImportError: cannot import name 'X' from 'Y'
    elif "ImportError" in last_line or "ModuleNotFoundError" in last_line:
        error_type = "ImportError"
        match = re.search(r"cannot import name '([^']+)'", last_line)
        if not match:
            match = re.search(r"No module named '([^']+)'", last_line)
        if match:
            symbol = match.group(1)
            
    # SyntaxError: invalid syntax (file, line N)
    elif "SyntaxError" in last_line:
        error_type = "SyntaxError"
        
    # LaTeX compilation error
    elif "LaTeX compilation" in error_logs or "Missing $" in error_logs:
        error_type = "LatexError"
        symbol = "LaTeX"
        
    # Generic catch-all for ErrorName: Message
    if error_type == "UnknownError":
        match = re.search(r"^(\w+Error):", last_line)
        if match:
            error_type = match.group(1)

    return ParsedError(
        error_type=error_type,
        symbol=symbol,
        invalid_arg=invalid_arg,
        traceback_tail=traceback_tail,
        line_number=line_number,
        raw_message=last_line
    )
