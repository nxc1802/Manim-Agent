from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.config import settings

_ALLOWED_IMPORTS = {"manim", "math", "numpy", "typing", "__future__"}
_FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "__import__", "input"}


def _get_manim_cmd() -> str:
    venv_manim = Path(sys.executable).parent / "manim"
    if venv_manim.exists():
        return str(venv_manim)
    return "manim"


class UnsafeManimCode(ValueError):
    pass


def validate_manim_code(code: str) -> None:
    if not code.strip():
        raise UnsafeManimCode("Manim code is empty")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise UnsafeManimCode(f"Invalid Python: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    raise UnsafeManimCode(f"Import is not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] not in _ALLOWED_IMPORTS:
                raise UnsafeManimCode(f"Import is not allowed: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            raise UnsafeManimCode(f"Call is not allowed: {node.func.id}")


def render_manim_code(job_id: UUID, code: str) -> str:
    """Render in the AI Core worker; no Backend module or database is involved."""
    validate_manim_code(code)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"manim_{job_id}_") as temp_dir:
        temp = Path(temp_dir)
        scene_file = temp / "scene.py"
        scene_file.write_text(code, encoding="utf-8")
        result = subprocess.run(
            [_get_manim_cmd(), "render", "-qh", "--media_dir", str(temp / "media"), str(scene_file), "GeneratedScene"],
            capture_output=True,
            text=True,
            timeout=settings.manim_timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Manim failed")[-4000:])
        videos = list((temp / "media" / "videos").rglob("*.mp4"))
        if not videos:
            raise RuntimeError("Manim completed without an mp4 artifact")
        artifact = settings.artifacts_dir / f"{job_id}.mp4"
        artifact.write_bytes(videos[0].read_bytes())
    if settings.artifact_public_base_url:
        return f"{settings.artifact_public_base_url.rstrip('/')}/{artifact.name}"
    return artifact.as_uri()


# ---------------------------------------------------------------------------
# Review-loop helpers
# ---------------------------------------------------------------------------

@dataclass
class ManimRenderResult:
    """Result of a validation render (low quality or save-last-frame)."""
    success: bool
    stderr: str
    stdout: str
    image_path: Path | None = None   # set when -s is used
    video_path: Path | None = None
    temp_dir: str | None = None      # caller responsible for cleanup if set


def render_manim_for_validation(
    code: str,
    *,
    extra_flags: list[str] | None = None,
    quality: str | None = None,
    timeout: int | None = None,
) -> ManimRenderResult:
    """Run manim render with configurable flags for validation / frame capture.

    ``extra_flags`` may include ``["-s"]`` to save last frame only (no video).
    ``quality`` defaults to ``settings.review_render_quality`` (``"-ql"``).
    """
    validate_manim_code(code)
    qual = quality or settings.review_render_quality
    tout = timeout or settings.review_render_timeout
    flags = list(extra_flags or [])

    temp_dir = tempfile.mkdtemp(prefix="manim_review_")
    temp = Path(temp_dir)
    scene_file = temp / "scene.py"
    scene_file.write_text(code, encoding="utf-8")
    media_dir = temp / "media"

    cmd = [_get_manim_cmd(), "render", qual, "--media_dir", str(media_dir), *flags, str(scene_file), "GeneratedScene"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=tout, check=False)

    image_path: Path | None = None
    video_path: Path | None = None
    if result.returncode == 0:
        # -s writes images; otherwise look for videos
        images = list(media_dir.rglob("*.png"))
        if images:
            image_path = images[0]
        videos = list(media_dir.rglob("*.mp4"))
        if videos:
            video_path = videos[0]

    return ManimRenderResult(
        success=result.returncode == 0,
        stderr=result.stderr or "",
        stdout=result.stdout or "",
        image_path=image_path,
        video_path=video_path,
        temp_dir=temp_dir,
    )


@dataclass
class ManimError:
    """A single error extracted from Manim's stderr."""
    line: int | None
    message: str


def parse_manim_errors(stderr: str) -> list[ManimError]:
    """Extract (line, message) pairs from a Manim traceback."""
    import re

    errors: list[ManimError] = []
    # Pattern: File "scene.py", line <N>
    line_pattern = re.compile(r'File\s+"[^"]*scene\.py",\s+line\s+(\d+)')
    lines = stderr.strip().splitlines()

    last_line_no: int | None = None
    for raw_line in lines:
        m = line_pattern.search(raw_line)
        if m:
            last_line_no = int(m.group(1))

    # Last line of traceback is usually the actual error message
    error_msg = ""
    for raw_line in reversed(lines):
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("File ") and not stripped.startswith("^"):
            error_msg = stripped
            break

    if error_msg:
        errors.append(ManimError(line=last_line_no, message=error_msg))
    elif stderr.strip():
        errors.append(ManimError(line=None, message=stderr.strip()[-500:]))

    return errors

