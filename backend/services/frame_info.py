from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def extract_end_of_play_jpeg_frame(
    video: Path, 
    timestamp: float | None = None, 
    *, 
    jpeg_width: int = 1024
) -> bytes:
    """Last decoded frame of the preview clip (approx. end of ``Scene.play()`` / file tail)."""
    return extract_frame_at_timestamp(video, timestamp=timestamp, jpeg_width=jpeg_width)


def extract_frame_at_timestamp(
    video: Path, 
    timestamp: float | None = None, 
    *, 
    jpeg_width: int = 1024
) -> bytes:
    """Extract a frame at a specific timestamp. If timestamp is None, extract from the end."""
    args = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    
    if timestamp is not None:
        args.extend(["-ss", f"{timestamp:.3f}"])
    else:
        # Seek relative to the end of the file
        args.extend(["-sseof", "-0.08"])
        
    args.extend([
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
    ])
    
    proc = subprocess.run(
        args,
        capture_output=True,
        check=True,
        timeout=180,
    )
    return proc.stdout


def extract_info_richest_jpeg_frame(
    video: Path,
    *,
    timestamp: float | None = None,
    num_samples: int = 13,
    jpeg_width: int = 1024,
) -> bytes:
    """Alias for end-of-preview frame (Phase 8). ``num_samples`` is ignored."""
    _ = num_samples
    return extract_frame_at_timestamp(video, timestamp=timestamp, jpeg_width=jpeg_width)


def extract_info_richest_jpeg_frame_to_temp(
    video: Path,
    *,
    timestamp: float | None = None,
    num_samples: int = 13,
    jpeg_width: int = 1024,
) -> Path:
    """Write richest frame to a temp ``.jpg`` and return its path (caller should unlink)."""
    data = extract_info_richest_jpeg_frame(
        video, timestamp=timestamp, num_samples=num_samples, jpeg_width=jpeg_width
    )
    tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
    tmp.write_bytes(data)
    return tmp
