from __future__ import annotations

import ast
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.config import settings
from app.tts import synthesize_speech

logger = logging.getLogger(__name__)

_ALLOWED_IMPORTS = {"manim", "math", "numpy", "typing", "__future__"}
_FORBIDDEN_CALLS = {
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
    "__import__",
}
_FORBIDDEN_NAMES = {"__builtins__", "__loader__", "__package__", "__spec__"}
_FORBIDDEN_IO_ATTRIBUTES = {
    "fromfile",
    "fromregex",
    "genfromtxt",
    "load",
    "load_library",
    "loadtxt",
    "memmap",
    "save",
    "savetxt",
    "tofile",
}
_FORBIDDEN_PATH_PREFIXES = (
    "/dev/",
    "/etc/",
    "/home/",
    "/proc/",
    "/root/",
    "/sys/",
)


def _get_manim_cmd() -> list[str]:
    """Launch Manim through this interpreter so introspection cannot drift."""
    return [sys.executable, "-m", "manim"]


class UnsafeManimCode(ValueError):
    pass


class ManimProcessTimeout(RuntimeError):
    """A Manim subprocess exceeded its deadline, with captured diagnostics."""

    def __init__(self, timeout: int, *, stdout: str, stderr: str) -> None:
        super().__init__(f"Manim exceeded its {timeout}s time limit")
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class FullProjectRenderResult:
    asset_url: str
    logs: str


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
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_CALLS
        ):
            raise UnsafeManimCode(f"Call is not allowed: {node.func.id}")
        elif isinstance(node, ast.Name) and (
            node.id in _FORBIDDEN_NAMES or node.id.startswith("__")
        ):
            raise UnsafeManimCode(f"Name is not allowed: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise UnsafeManimCode(f"Private attribute access is not allowed: {node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_IO_ATTRIBUTES:
            raise UnsafeManimCode(f"File-backed operation is not allowed: {node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip().lower()
            has_parent_traversal = bool(re.search(r"(?:^|[\\/])\.\.(?:[\\/]|$)", value))
            has_external_scheme = bool(re.match(r"^[a-z][a-z0-9+.-]*://", value))
            if (
                value.startswith(("/", "~"))
                or value.startswith(_FORBIDDEN_PATH_PREFIXES)
                or has_parent_traversal
                or has_external_scheme
            ):
                raise UnsafeManimCode("External or sensitive resource paths are not allowed")


def _manim_preexec() -> None:
    """Apply worker-side limits in addition to Compose container isolation."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (settings.manim_memory_limit_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (settings.manim_cpu_limit_seconds,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))
    except (ImportError, OSError, ValueError):
        # Docker's read-only filesystem, dropped capabilities and cgroup limits
        # remain the primary containment boundary when rlimits are unavailable.
        return


def _sanitized_subprocess_env(work_dir: Path) -> dict[str, str]:
    """Return a minimal renderer environment with no provider/service secrets."""
    texmfvar = work_dir / ".texmf-var"
    texmfconfig = work_dir / ".texmf-config"
    texmfvar.mkdir(parents=True, exist_ok=True)
    texmfconfig.mkdir(parents=True, exist_ok=True)

    safe = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SYSTEMROOT", "FONTCONFIG_PATH"}
    }
    safe.update(
        {
            "HOME": str(work_dir),
            "TMPDIR": str(work_dir),
            "TEXMFVAR": str(texmfvar),
            "TEXMFCONFIG": str(texmfconfig),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return safe


def _run_manim(
    command: list[str], *, timeout: int, work_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run Manim and terminate its entire process group when it times out."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=_manim_preexec if os.name == "posix" else None,
        start_new_session=os.name == "posix",
        cwd=work_dir,
        env=_sanitized_subprocess_env(work_dir),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "posix":
            # Manim can spawn TeX/renderer children which inherit stdout/stderr.
            # Killing only the parent leaves those pipes open and turns a code
            # error into a misleading 120s worker timeout.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        stdout, stderr = process.communicate()
        partial_stdout = exc.output if isinstance(exc.output, str) else ""
        partial_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        raise ManimProcessTimeout(
            timeout,
            stdout=stdout or partial_stdout,
            stderr=stderr or partial_stderr,
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def render_manim_code(
    job_id: UUID,
    code: str,
    user_settings: dict | None = None,
    voice_script: str | None = None,
    source_language: str | None = None,
) -> str:
    """Render in the AI Core worker; no Backend module or database is involved."""
    validate_manim_code(code)

    # Parse quality and fps from settings
    settings_dict = user_settings or {}
    quality = settings_dict.get("video_quality", "720p")
    fps_val = settings_dict.get("fps", 30)

    quality_flag = "-qm"  # default 720p
    if quality == "480p":
        quality_flag = "-ql"
    elif quality == "1080p":
        quality_flag = "-qh"
    elif quality == "4k":
        quality_flag = "-qk"

    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"manim_{job_id}_") as temp_dir:
        temp = Path(temp_dir)
        scene_file = temp / "scene.py"
        scene_file.write_text(code, encoding="utf-8")
        final_mp4: Path | None = None
        last_stderr = ""
        for render_attempt in range(2):
            media_dir = temp / f"media_{render_attempt}"
            command = [
                *_get_manim_cmd(),
                "render",
                quality_flag,
                "--fps",
                str(fps_val),
                "--media_dir",
                str(media_dir),
            ]
            if render_attempt:
                command.append("--disable_caching")
            command.extend([str(scene_file), "GeneratedScene"])
            result = _run_manim(
                command,
                timeout=settings.manim_timeout_seconds,
                work_dir=temp,
            )
            last_stderr = result.stderr or ""
            if result.returncode == 0:
                mp4_files = _final_manim_videos(media_dir)
                if mp4_files:
                    final_mp4 = mp4_files[0]
                    break
            elif _is_transient_partial_movie_list_failure(last_stderr):
                recovered = _recover_partial_movie_concat(
                    media_dir,
                    work_dir=temp,
                    renderer_output="\n".join((result.stdout or "", last_stderr)),
                )
                if recovered is not None:
                    final_mp4 = recovered
                    break
                if render_attempt == 0:
                    logger.warning("Retrying final Manim render after partial-movie concat failure")
                    continue
                raise RuntimeError(
                    "Manim renderer could not combine its internal partial movie files"
                )
            elif render_attempt == 0 and _is_transient_frame_allocation_failure(last_stderr):
                logger.warning("Retrying final Manim render after a small frame allocation failure")
                continue
            else:
                raise UnsafeManimCode(f"Manim Error:\n{last_stderr}")

        if final_mp4 is None:
            if last_stderr:
                raise UnsafeManimCode(f"Manim Error:\n{last_stderr}")
            raise UnsafeManimCode("Manim did not produce any MP4 files")
        audio_file = synthesize_speech(
            narration=voice_script,
            source_language=source_language,
            user_settings=settings_dict,
            destination=temp / "narration.mp3",
        )
        if audio_file is not None:
            muxed_mp4 = temp / "scene_with_audio.mp4"
            _mux_audio(video_file=final_mp4, audio_file=audio_file, destination=muxed_mp4, work_dir=temp)
            if not _has_audio_stream(muxed_mp4, temp):
                raise RuntimeError("TTS mux completed without an audio stream")
            final_mp4 = muxed_mp4
        dest_path = settings.artifacts_dir / f"{job_id}.mp4"
        shutil.copy(final_mp4, dest_path)
        return f"file://{dest_path.absolute()}"


def _final_manim_videos(media_dir: Path) -> list[Path]:
    """Exclude Manim's partial render fragments from publishable outputs."""
    candidates = [
        path
        for path in media_dir.rglob("*.mp4")
        if "partial_movie_files" not in path.parts
    ]
    named = [path for path in candidates if path.name == "GeneratedScene.mp4"]
    return sorted(named or candidates, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def _is_transient_partial_movie_list_failure(stderr: str) -> bool:
    """Identify Manim's intermittent internal concat-file race.

    This is deliberately narrow: a user scene can legitimately raise a
    ``FileNotFoundError`` and must still be reviewed.  Only Manim's own
    generated ``partial_movie_file_list.txt`` is safe to retry in a fresh
    workspace without involving the Auto Repair Loop.
    """
    normalised = " ".join(stderr.split())
    return (
        "FileNotFoundError" in normalised
        and "partial_movie_files" in normalised
        and "partial_movie_file_list.txt" in normalised
    )


def _is_transient_frame_allocation_failure(stderr: str) -> bool:
    """Detect failure to allocate one ordinary low-quality RGBA frame.

    This can happen under momentary container pressure.  Only small NumPy
    allocations are retried; large requests remain scene-code errors so an
    updater that allocates unbounded arrays is still sent to Auto-Review.
    """
    normalised = " ".join(stderr.split())
    match = re.search(
        r"MemoryError: Unable to allocate ([0-9]+(?:\.[0-9]+)?) "
        r"(KiB|MiB) for an array with shape \(([^)]+)\)",
        normalised,
    )
    if match is None:
        return False
    amount = float(match.group(1))
    amount_mib = amount / 1024 if match.group(2) == "KiB" else amount
    dimensions = [part.strip() for part in match.group(3).split(",")]
    return amount_mib <= 16 and len(dimensions) in {2, 3}


def _recover_partial_movie_concat(
    media_dir: Path,
    *,
    work_dir: Path,
    renderer_output: str = "",
) -> Path | None:
    """Finish a Manim render whose PyAV concat stage failed.

    Manim has already rendered every animation by the time it opens
    ``partial_movie_file_list.txt``.  Rebuilding that list and invoking the
    FFmpeg concat demuxer avoids turning an internal PyAV race into a scene-code
    error.  Every input is constrained to the current render workspace.
    """
    media_root = media_dir.resolve()
    logged_paths = re.findall(
        r"Partial movie file written in\s+['\"]([^'\"]+\.mp4)['\"]",
        renderer_output,
    )

    for index, partial_dir in enumerate(
        sorted(media_dir.rglob("partial_movie_files/GeneratedScene"))
    ):
        input_files: list[Path] = []
        list_file = partial_dir / "partial_movie_file_list.txt"
        if list_file.is_file():
            for line in list_file.read_text(encoding="utf-8").splitlines():
                match = re.fullmatch(r"\s*file\s+'file:(.+)'\s*", line)
                if match:
                    input_files.append(Path(match.group(1)))
        if not input_files and logged_paths:
            input_files = [Path(path) for path in logged_paths if Path(path).parent == partial_dir]
        if not input_files:
            input_files = sorted(
                partial_dir.glob("*.mp4"),
                key=lambda path: (path.stat().st_mtime_ns, path.name),
            )
        if not input_files:
            continue

        safe_inputs: list[Path] = []
        for input_file in input_files:
            try:
                resolved = input_file.resolve(strict=True)
            except OSError:
                safe_inputs = []
                break
            if not resolved.is_relative_to(media_root) or not resolved.is_file():
                safe_inputs = []
                break
            safe_inputs.append(resolved)
        if not safe_inputs:
            continue

        recovery_list = work_dir / f"partial_movie_recovery_{index}.txt"
        recovery_list.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in safe_inputs),
            encoding="utf-8",
        )
        destination = partial_dir.parent.parent / "GeneratedScene.mp4"
        recovered = destination.with_name("GeneratedScene.recovered.mp4")
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(recovery_list),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(recovered),
                ],
                capture_output=True,
                text=True,
                timeout=settings.manim_timeout_seconds,
                check=False,
                preexec_fn=_manim_preexec if os.name == "posix" else None,
                cwd=work_dir,
                env=_sanitized_subprocess_env(work_dir),
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("FFmpeg fallback for Manim partial movies failed", exc_info=True)
            continue
        if result.returncode != 0 or not recovered.is_file() or recovered.stat().st_size == 0:
            logger.warning(
                "FFmpeg fallback for Manim partial movies returned %s: %s",
                result.returncode,
                (result.stderr or "")[-500:],
            )
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        recovered.replace(destination)
        logger.info(
            "Recovered Manim partial-movie concat with FFmpeg (%d clips)",
            len(safe_inputs),
        )
        return destination
    return None


def _probe_duration(media_file: Path, work_dir: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=work_dir,
            env=_sanitized_subprocess_env(work_dir),
        )
        if result.returncode != 0:
            raise ValueError(result.stderr)
        duration = float(result.stdout.strip())
        if duration <= 0:
            raise ValueError("non-positive duration")
        return duration
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise RuntimeError("Could not determine media duration for TTS muxing") from exc


def _has_audio_stream(media_file: Path, work_dir: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(media_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=work_dir,
            env=_sanitized_subprocess_env(work_dir),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "audio" in result.stdout.split()


def _mux_audio(*, video_file: Path, audio_file: Path, destination: Path, work_dir: Path) -> None:
    """Mux narration while retaining all speech and all animation frames.

    The shorter stream is padded: video holds its final frame if narration is
    longer; audio receives silence if the animation is longer.
    """
    video_seconds = _probe_duration(video_file, work_dir)
    audio_seconds = _probe_duration(audio_file, work_dir)
    video_padding = max(0.0, audio_seconds - video_seconds)
    audio_padding = max(0.0, video_seconds - audio_seconds)
    filter_graph = (
        f"[0:v]tpad=stop_mode=clone:stop_duration={video_padding:.3f}[video];"
        f"[1:a]apad=pad_dur={audio_padding:.3f}[audio]"
    )
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(video_file),
                "-i",
                str(audio_file),
                "-filter_complex",
                filter_graph,
                "-map",
                "[video]",
                "-map",
                "[audio]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                "-y",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=settings.manim_timeout_seconds,
            check=False,
            preexec_fn=_manim_preexec if os.name == "posix" else None,
            cwd=work_dir,
            env=_sanitized_subprocess_env(work_dir),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("FFmpeg TTS muxing timed out") from exc
    if result.returncode != 0 or not destination.is_file():
        raise RuntimeError("FFmpeg could not add TTS audio to the scene video")


def concat_project_videos(
    job_id: UUID,
    video_urls: list[str],
    user_settings: dict | None = None,
    voice_scripts: list[str | None] | None = None,
    source_language: str | None = None,
) -> str:
    """Concatenate ordered scene videos without giving AI Core storage credentials.

    Backend passes local ``file://`` artifacts in Compose and short-lived signed
    HTTPS URLs for private Supabase objects. Arbitrary schemes are rejected.
    """
    if not video_urls:
        raise RuntimeError("Full-project render has no scene videos")
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"concat_{job_id}_") as temp_dir:
        temp = Path(temp_dir)
        local_files = [
            _materialize_concat_source(url, temp, index)
            for index, url in enumerate(video_urls)
        ]
        settings_dict = user_settings or {}
        if settings_dict.get("tts_enabled", False):
            if voice_scripts is None or len(voice_scripts) != len(local_files):
                raise RuntimeError("Full-project TTS requires narration for every rendered scene")
            voiced_files: list[Path] = []
            for index, (scene_file, narration) in enumerate(zip(local_files, voice_scripts, strict=True)):
                audio_file = synthesize_speech(
                    narration=narration,
                    source_language=source_language,
                    user_settings=settings_dict,
                    destination=temp / f"narration_{index:04d}.mp3",
                )
                if audio_file is None:  # Defensive: TTS was checked above.
                    raise RuntimeError("Full-project TTS did not create narration audio")
                voiced_file = temp / f"scene_with_audio_{index:04d}.mp4"
                _mux_audio(
                    video_file=scene_file,
                    audio_file=audio_file,
                    destination=voiced_file,
                    work_dir=temp,
                )
                voiced_files.append(voiced_file)
            local_files = voiced_files
        list_file = temp / "concat_list.txt"

        lines = [f"file '{path}'" for path in local_files]
        list_file.write_text("\n".join(lines), encoding="utf-8")

        dest_path = settings.artifacts_dir / f"{job_id}.mp4"

        cmd = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-y",
            str(dest_path),
        ]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.manim_timeout_seconds,
                check=False,
                preexec_fn=_manim_preexec if os.name == "posix" else None,
                cwd=temp,
                env=_sanitized_subprocess_env(temp),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("FFmpeg concatenation timed out") from exc
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {res.stderr}")

        if settings_dict.get("tts_enabled", False) and not _has_audio_stream(dest_path, temp):
            raise RuntimeError("Full-project TTS render completed without an audio stream")

        return f"file://{dest_path.absolute()}"


def render_full_project(
    job_id: UUID,
    scenes: list[dict],
    user_settings: dict | None = None,
    source_language: str | None = None,
) -> FullProjectRenderResult:
    """Render every scene from approved source and concatenate valid outputs.

    Each scene is isolated in its own Manim subprocess. Invalid source, a bad
    GeneratedScene class, or a TTS failure skips only that scene. A final video
    is published when at least one scene succeeds, with skip reasons retained
    in the render job logs.
    """
    if not scenes:
        raise RuntimeError("Full-project render has no scene sources")

    settings_dict = user_settings or {}
    rendered_urls: list[str] = []
    intermediate_paths: list[Path] = []
    messages: list[str] = []
    ordered = sorted(
        scenes,
        key=lambda item: (int(item.get("scene_order") or 0), str(item.get("scene_id") or "")),
    )
    try:
        for scene in ordered:
            label = f"Scene {scene.get('scene_order') or '?'}"
            code = scene.get("manim_code")
            if not isinstance(code, str) or not code.strip():
                messages.append(f"Skipped {label}: no approved Manim source")
                continue
            intermediate_id = uuid4()
            try:
                url = render_manim_code(
                    intermediate_id,
                    code,
                    settings_dict,
                    scene.get("voice_script"),
                    source_language,
                )
            except (UnsafeManimCode, ManimProcessTimeout, RuntimeError) as exc:
                summary = " ".join(str(exc).split())[:500]
                messages.append(f"Skipped {label}: {summary}")
                continue
            rendered_urls.append(url)
            intermediate_paths.append(Path(url.removeprefix("file://")))
            messages.append(f"Rendered {label} from source")

        if not rendered_urls:
            detail = "; ".join(messages) or "all scene renders failed"
            raise RuntimeError(f"Full-project render has no valid scenes: {detail}")

        # Audio has already been synthesized and muxed exactly once while each
        # scene was rendered. Disable the concat helper's legacy TTS branch.
        concat_settings = {**settings_dict, "tts_enabled": False}
        asset_url = concat_project_videos(
            job_id,
            rendered_urls,
            concat_settings,
        )
        final_path = Path(asset_url.removeprefix("file://"))
        if settings_dict.get("tts_enabled", False) and not _has_audio_stream(
            final_path, settings.artifacts_dir
        ):
            raise RuntimeError("Final project render is missing its TTS audio stream")
        return FullProjectRenderResult(asset_url=asset_url, logs="\n".join(messages))
    finally:
        for path in intermediate_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _materialize_concat_source(url: str, temp_dir: Path, index: int) -> Path:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        artifact_root = settings.artifacts_dir.resolve()
        try:
            source = Path(parsed.path).resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("Local scene artifact is unavailable") from exc
        if not source.is_relative_to(artifact_root) or not source.is_file():
            raise RuntimeError("Local scene artifact path is not allowed")
        return source

    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"Unsupported scene artifact scheme: {parsed.scheme or 'missing'}")

    destination = temp_dir / f"scene_{index:04d}.mp4"
    downloaded = 0
    timeout = httpx.Timeout(settings.concat_download_timeout_seconds)
    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=False) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > settings.concat_source_max_bytes:
                raise RuntimeError("Scene artifact exceeds the configured size limit")
            with destination.open("wb") as output:
                for chunk in response.iter_bytes():
                    downloaded += len(chunk)
                    if downloaded > settings.concat_source_max_bytes:
                        raise RuntimeError("Scene artifact exceeds the configured size limit")
                    output.write(chunk)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise RuntimeError("Unable to download a signed scene artifact") from exc
    if downloaded == 0:
        raise RuntimeError("Downloaded scene artifact is empty")
    return destination


# ---------------------------------------------------------------------------
# Review-loop helpers
# ---------------------------------------------------------------------------


@dataclass
class ManimRenderResult:
    """Result of a validation render (low quality or save-last-frame)."""

    success: bool
    stderr: str
    stdout: str
    image_path: Path | None = None  # set when -s is used
    video_path: Path | None = None
    temp_dir: str | None = None  # caller responsible for cleanup if set


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

    # Manim can very occasionally fail while concatenating its *own* partial
    # clips, even though the exact same source succeeds in a fresh directory.
    # Keep this below the review layer: it is renderer infrastructure, not a
    # scene-code defect and must not spend an LLM repair attempt.
    for render_attempt in range(2):
        temp_dir = tempfile.mkdtemp(prefix="manim_review_")
        temp = Path(temp_dir)
        scene_file = temp / "scene.py"
        scene_file.write_text(code, encoding="utf-8")
        media_dir = temp / "media"

        cmd = [
            *_get_manim_cmd(),
            "render",
            qual,
            "--media_dir",
            str(media_dir),
        ]
        if render_attempt:
            cmd.append("--disable_caching")
        cmd.extend([*flags, str(scene_file), "GeneratedScene"])
        try:
            result = _run_manim(cmd, timeout=tout, work_dir=temp)
        except ManimProcessTimeout as exc:
            # A timeout is still a render failure, not an LLM/service failure.
            # Preserve partial traceback output so the review loop can repair the
            # actual TypeError/NameError that caused the orphaned process chain.
            diagnostics = "\n".join(part for part in (exc.stderr, exc.stdout) if part).strip()
            timeout_message = f"Manim validation timed out after {tout}s"
            return ManimRenderResult(
                success=False,
                stderr=f"{diagnostics}\n{timeout_message}".strip(),
                stdout=exc.stdout,
                temp_dir=temp_dir,
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        if result.returncode != 0 and _is_transient_partial_movie_list_failure(result.stderr or ""):
            recovered = _recover_partial_movie_concat(
                media_dir,
                work_dir=temp,
                renderer_output="\n".join((result.stdout or "", result.stderr or "")),
            )
            if recovered is not None:
                result = subprocess.CompletedProcess(
                    result.args,
                    0,
                    result.stdout,
                    result.stderr,
                )
            elif render_attempt == 0:
                logger.warning("Retrying transient Manim partial-movie concat failure")
                shutil.rmtree(temp_dir, ignore_errors=True)
                continue
            elif "-s" not in flags and "--save_last_frame" not in flags:
                # Scene construction and every animation completed before
                # Manim entered its internal concat step. Code review only
                # needs that execution result; do not spend an LLM attempt on
                # a renderer-infrastructure failure.
                logger.warning("Ignoring Manim partial-movie concat failure during code validation")
                result = subprocess.CompletedProcess(
                    result.args,
                    0,
                    result.stdout,
                    result.stderr,
                )
        elif (
            result.returncode != 0
            and render_attempt == 0
            and _is_transient_frame_allocation_failure(result.stderr or "")
        ):
            logger.warning("Retrying transient Manim frame allocation failure")
            shutil.rmtree(temp_dir, ignore_errors=True)
            continue

        image_path: Path | None = None
        video_path: Path | None = None
        if result.returncode == 0:
            # -s writes images; otherwise look for videos
            images = list(media_dir.rglob("*.png"))
            if images:
                image_path = images[0]
            videos = _final_manim_videos(media_dir)
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

    raise RuntimeError("Validation render retry loop exhausted unexpectedly")


@dataclass
class ManimError:
    """A single error extracted from Manim's stderr."""

    line: int | None
    message: str
    error_type: str | None = None


def parse_manim_errors(stderr: str) -> list[ManimError]:
    """Extract the scene line and terminal exception from plain or Rich tracebacks.

    Manim Community renders tracebacks with Rich, which can wrap ``scene.py``
    across two bordered lines and can wrap the final exception message itself.
    Parsing only the final physical line loses both the exception type and most
    of the message, so we normalise the presentation markup first.
    """
    if not stderr.strip():
        return []

    ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    cleaned = ansi_pattern.sub("", stderr)
    # Rich borders are presentation only. Replacing them with spaces preserves
    # wrapped path/message boundaries for whitespace-normalised regexes.
    cleaned = cleaned.translate(str.maketrans({char: " " for char in "│╭╮╰╯─❱"}))
    compact = " ".join(cleaned.split())

    line_numbers: list[int] = []
    plain_pattern = re.compile(
        r'File\s+"(?P<path>[^"]*[/\\]?scene\.py)"\s*,\s*line\s+(?P<line>\d+)'
    )
    for match in plain_pattern.finditer(cleaned):
        normalised_path = match.group("path").replace("\\", "/")
        if normalised_path.endswith("/manim/scene/scene.py"):
            continue
        line_numbers.append(int(match.group("line")))

    # Exclude Manim's own ``manim/scene/scene.py`` frames. They commonly occur
    # after GeneratedScene.construct and would otherwise replace the actionable
    # generated-source line with an internal line such as 972.
    rich_pattern = re.compile(r"(?:^|[/\\])scene\s*\.py:(\d+)\s+in\b")
    for match in rich_pattern.finditer(compact):
        prefix = re.sub(r"\s+", "", compact[max(0, match.start() - 80) : match.start()])
        if prefix.endswith(("/manim/scene", "\\manim\\scene")):
            continue
        line_numbers.append(int(match.group(1)))
    last_line_no = line_numbers[-1] if line_numbers else None

    error_pattern = re.compile(
        r"(?m)^\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:Error|Exception)):\s*(.*)$"
    )
    matches = list(error_pattern.finditer(cleaned))
    if matches:
        terminal = matches[-1]
        error_type = terminal.group(1)
        message_lines = [terminal.group(2).strip()]
        message_lines.extend(line.strip() for line in cleaned[terminal.end() :].splitlines())
        detail = " ".join(item for item in message_lines if item)
        detail = " ".join(detail.split())
        message = f"{error_type}: {detail}" if detail else error_type
        return [
            ManimError(
                line=last_line_no,
                message=message[:2_000],
                error_type=error_type,
            )
        ]

    # Non-Python failures (for example a TeX process error) do not always end
    # with an ``*Error`` class. Keep a bounded but useful terminal diagnostic.
    meaningful = [line.strip() for line in cleaned.splitlines() if line.strip()]
    fallback = " ".join(meaningful[-8:])[-2_000:]
    return [ManimError(line=last_line_no, message=fallback)] if fallback else []
