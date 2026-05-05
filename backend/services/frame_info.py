import subprocess
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def extract_frame_at_timestamp(
    video: str | Path,
    timestamp: float | None = None,
    jpeg_width: int = 1024,
) -> bytes:
    """
    Extract a single frame from a video at a specific timestamp or at the end of the file.
    Uses ffmpeg to extract the frame and returns the raw bytes of the JPEG image.
    Supports local paths or URLs (Supabase signed URLs).
    """
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    
    video_path = str(video)
    
    # Position seek
    if timestamp is not None:
        # Fast seek before -i
        args.extend(["-ss", f"{timestamp:.3f}"])
    else:
        # Seek relative to the end of the file
        # Using a larger offset (-0.5s) to ensure we don't hit the absolute end
        args.extend(["-sseof", "-0.5"])
        
    args.extend([
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-vf",
        f"scale={jpeg_width}:-2",
        "-strict",
        "unofficial",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-",
    ])
    
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(timeout=30)
        
        if process.returncode != 0:
            err_msg = stderr.decode()
            logger.error(f"FFmpeg failed with code {process.returncode}: {err_msg}")
            
            # Retry logic for very short videos if sseof fails
            if "-sseof" in args:
                logger.info("Retrying frame extraction from start (0s) due to sseof failure")
                args_retry = [a for a in args if a not in ["-sseof", "-0.5"]]
                # Insert -ss 0 before -i
                try:
                    idx = args_retry.index("-i")
                    args_retry.insert(idx, "-ss")
                    args_retry.insert(idx+1, "0")
                    
                    process = subprocess.Popen(args_retry, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate(timeout=30)
                    if process.returncode == 0:
                        return stdout
                except ValueError:
                    pass
            
            raise RuntimeError(f"FFmpeg frame extraction failed: {err_msg}")
            
        if not stdout:
            raise RuntimeError("FFmpeg produced empty output")
            
        return stdout
        
    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("FFmpeg frame extraction timed out")
        raise RuntimeError("FFmpeg frame extraction timed out")
    except Exception as e:
        logger.exception(f"Unexpected error during frame extraction: {e}")
        raise

# Alias for backward compatibility
extract_end_of_play_jpeg_frame = extract_frame_at_timestamp
