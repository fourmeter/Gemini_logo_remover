"""FFmpeg and FFprobe wrapper for audio-preserving muxing and encoding."""

import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

from config import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_AUDIO_CODEC,
    DEFAULT_PIX_FMT,
    DEFAULT_VIDEO_CODEC,
)
from fourframe.models import FFmpegNotFoundError, FourFrameError, ProcessingConfig

logger = logging.getLogger("fourframe")

INSTALL_GUIDANCE = (
    "FFmpeg/FFprobe binaries were not found on your system PATH.\n"
    "Please install FFmpeg to run FourFrame:\n"
    "  Windows: winget install Gyan.FFmpeg   OR   choco install ffmpeg\n"
    "  macOS:   brew install ffmpeg\n"
    "  Linux:   sudo apt-get install ffmpeg\n"
    "After installing, ensure both 'ffmpeg' and 'ffprobe' are in your system PATH."
)


def verify_ffmpeg_installation() -> None:
    """Verify that both ffmpeg and ffprobe are available and functional."""
    for binary in ("ffmpeg", "ffprobe"):
        try:
            result = subprocess.run(
                [binary, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise FFmpegNotFoundError(
                    f"'{binary}' returned non-zero exit code.\n{INSTALL_GUIDANCE}"
                )
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(
                f"Binary '{binary}' is not accessible on PATH.\n{INSTALL_GUIDANCE}"
            ) from exc


def mux_video_with_original_audio(
    processed_video_path: Path,
    original_video_path: Path,
    output_path: Path,
    config: ProcessingConfig,
) -> Path:
    """Mux processed video with original audio stream using libx264 encoding.

    Concept:
    ffmpeg -y \
        -i processed_video.mp4 \
        -i original.mp4 \
        -map 0:v:0 \
        -map 1:a? \
        -c:v libx264 \
        -preset medium \
        -crf 18 \
        -pix_fmt yuv420p \
        -c:a aac \
        -b:a 192k \
        -movflags +faststart \
        output.mp4

    Args:
        processed_video_path: Path to intermediate silent processed video.
        original_video_path: Path to source video file containing original audio.
        output_path: Destination path for final muxed video.
        config: Processing configuration with CRF, preset, etc.

    Returns:
        Path to completed final MP4.

    Raises:
        FourFrameError: If FFmpeg execution encounters an error.
    """
    config.validate()

    proc_path = Path(processed_video_path).resolve()
    orig_path = Path(original_video_path).resolve()
    out_path = Path(output_path).resolve()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd: List[str] = [
        "ffmpeg",
        "-y",  # Overwrite destination if re-running
        "-i",
        str(proc_path),
        "-i",
        str(orig_path),
        "-map",
        "0:v:0",  # Video from processed intermediate
        "-map",
        "1:a?",   # Audio from original (optional '?' avoids error if video has no audio)
        "-c:v",
        DEFAULT_VIDEO_CODEC,
        "-preset",
        config.preset,
        "-crf",
        str(config.crf),
        "-pix_fmt",
        DEFAULT_PIX_FMT,
        "-c:a",
        DEFAULT_AUDIO_CODEC,
        "-b:a",
        DEFAULT_AUDIO_BITRATE,
        "-movflags",
        "+faststart",
        str(out_path),
    ]

    logger.debug("Executing FFmpeg command: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        raise FourFrameError(f"FFmpeg muxing failed (exit code {proc.returncode}):\n{err}")

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise FourFrameError(f"FFmpeg finished but output file is missing or empty at {out_path}")

    logger.info("Final video created successfully at: %s", out_path)
    return out_path


def validate_output_file(output_path: Path) -> Tuple[bool, str]:
    """Verify that the generated video can be opened and parsed cleanly by ffprobe."""
    path = Path(output_path).resolve()
    if not path.is_file():
        return False, f"Output file does not exist: {path}"

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,width,height",
        "-of",
        "json",
        str(path),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode == 0:
            return True, "Valid"
        return False, res.stderr.strip()
    except Exception as exc:
        return False, str(exc)
