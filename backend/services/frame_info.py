from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def extract_end_of_play_jpeg_frame(video: Path, *, jpeg_width: int = 1024) -> bytes:
    """Last decoded frame of the preview clip (approx. end of ``Scene.play()`` / file tail)."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-sseof",
            "-0.08",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={jpeg_width}:-1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    return proc.stdout


def extract_info_richest_jpeg_frame(
    video: Path,
    *,
    num_samples: int = 13,
    jpeg_width: int = 1024,
) -> bytes:
    """Alias for end-of-preview frame (Phase 8). ``num_samples`` is ignored."""
    _ = num_samples
    return extract_end_of_play_jpeg_frame(video, jpeg_width=jpeg_width)


def extract_info_richest_jpeg_frame_to_temp(
    video: Path,
    *,
    num_samples: int = 13,
    jpeg_width: int = 1024,
) -> Path:
    """Write richest frame to a temp ``.jpg`` and return its path (caller should unlink)."""
    data = extract_info_richest_jpeg_frame(video, num_samples=num_samples, jpeg_width=jpeg_width)
    tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
    tmp.write_bytes(data)
    return tmp
