"""FFprobe-based video metadata extraction module."""

import json
import logging
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Optional

import cv2

from fourframe.models import FFmpegNotFoundError, MetadataError, VideoMetadata

logger = logging.getLogger("fourframe")


def parse_fraction_fps(fps_str: Optional[str]) -> Optional[float]:
    """Parse rational framerate string (e.g. '30/1' or '30000/1001') to float."""
    if not fps_str or fps_str == "0/0":
        return None
    try:
        val = float(Fraction(fps_str))
        if val > 0:
            return val
    except (ValueError, ZeroDivisionError):
        pass
    return None


def extract_metadata(video_path: Path) -> VideoMetadata:
    """Extract comprehensive video metadata using FFprobe with OpenCV fallback.

    Args:
        video_path: Path to the target video file.

    Returns:
        VideoMetadata dataclass instance.

    Raises:
        FileNotFoundError: If input file does not exist.
        FFmpegNotFoundError: If ffprobe is not installed or available on PATH.
        MetadataError: If the file is corrupted or contains no valid video stream.
    """
    path = Path(video_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input video file not found: {path}")

    # Build ffprobe command safely as an argument list (no shell=True)
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,pix_fmt,duration",
        "-show_entries",
        "format=duration,size,bit_rate",
        "-of",
        "json",
        str(path),
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FFmpegNotFoundError(
            "ffprobe binary was not found on your system PATH.\n"
            "Please install FFmpeg to use FourFrame:\n"
            "  Windows: winget install Gyan.FFmpeg   OR   choco install ffmpeg\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt-get install ffmpeg\n"
            "Ensure 'ffmpeg' and 'ffprobe' are accessible from your terminal."
        ) from exc

    if result.returncode != 0:
        err_msg = result.stderr.strip() or "Unknown ffprobe error"
        raise MetadataError(f"Failed to inspect video metadata for {path.name}: {err_msg}")

    try:
        data: Dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MetadataError(f"Failed to parse ffprobe JSON output for {path.name}") from exc

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    video_stream: Optional[Dict[str, Any]] = None
    audio_stream: Optional[Dict[str, Any]] = None

    for stream in streams:
        c_type = stream.get("codec_type")
        if c_type == "video" and video_stream is None:
            video_stream = stream
        elif c_type == "audio" and audio_stream is None:
            audio_stream = stream

    if not video_stream:
        raise MetadataError(f"No video stream found in {path.name}. File may be audio-only or corrupted.")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)

    if width <= 0 or height <= 0:
        # Fallback to OpenCV inspect
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

    if width <= 0 or height <= 0:
        raise MetadataError(f"Invalid frame dimensions detected for {path.name}: {width}x{height}")

    # Determine FPS: check r_frame_rate, then avg_frame_rate, then OpenCV
    fps = parse_fraction_fps(video_stream.get("r_frame_rate"))
    if fps is None or fps <= 0:
        fps = parse_fraction_fps(video_stream.get("avg_frame_rate"))

    if fps is None or fps <= 0:
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            cv_fps = cap.get(cv2.CAP_PROP_FPS)
            if cv_fps and cv_fps > 0:
                fps = float(cv_fps)
            cap.release()

    if fps is None or fps <= 0:
        fps = 30.0  # safe standard fallback for strange containers
        logger.warning("Framerate could not be detected; defaulted to 30.0 FPS")

    # Duration parsing
    duration: float = 0.0
    if "duration" in format_info and format_info["duration"] is not None:
        try:
            duration = float(format_info["duration"])
        except ValueError:
            duration = 0.0

    if duration <= 0 and "duration" in video_stream and video_stream["duration"] is not None:
        try:
            duration = float(video_stream["duration"])
        except ValueError:
            duration = 0.0

    # Frame count parsing
    frame_count: int = 0
    if "nb_frames" in video_stream and video_stream["nb_frames"] is not None:
        try:
            frame_count = int(video_stream["nb_frames"])
        except ValueError:
            frame_count = 0

    if frame_count <= 0 and duration > 0 and fps > 0:
        frame_count = int(round(duration * fps))

    if frame_count <= 0:
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            cv_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if cv_count and cv_count > 0:
                frame_count = int(cv_count)
            cap.release()

    if duration <= 0 and frame_count > 0 and fps > 0:
        duration = float(frame_count / fps)

    video_codec = video_stream.get("codec_name")
    audio_codec = audio_stream.get("codec_name") if audio_stream else None
    has_audio = audio_stream is not None
    pixel_format = video_stream.get("pix_fmt")

    metadata = VideoMetadata(
        path=path,
        filename=path.name,
        width=width,
        height=height,
        fps=float(fps),
        frame_count=int(frame_count),
        duration=float(duration),
        has_audio=has_audio,
        video_codec=video_codec,
        audio_codec=audio_codec,
        pixel_format=pixel_format,
    )

    logger.debug("Extracted metadata: %s", metadata.to_dict())
    return metadata
