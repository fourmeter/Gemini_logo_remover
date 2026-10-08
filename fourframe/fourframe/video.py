"""Video I/O and frame extraction utilities."""

import logging
from pathlib import Path
from typing import Generator, Tuple

import cv2
import numpy as np

from fourframe.models import FourFrameError, VideoMetadata

logger = logging.getLogger("fourframe")


def open_video_reader(video_path: Path) -> cv2.VideoCapture:
    """Open an OpenCV VideoCapture stream with validation."""
    path_str = str(Path(video_path).resolve())
    cap = cv2.VideoCapture(path_str)
    if not cap.isOpened():
        raise FourFrameError(f"Could not open video file for reading: {path_str}")
    return cap


def extract_frame_at_index(video_path: Path, frame_index: int) -> np.ndarray:
    """Extract a specific frame from the video by its index.

    Args:
        video_path: Path to video.
        frame_index: Target 0-based frame index.

    Returns:
        BGR numpy frame.
    """
    cap = open_video_reader(video_path)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_index))
        ret, frame = cap.read()
        if not ret or frame is None:
            # Fallback: rewind and read first frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret or frame is None:
                raise FourFrameError(f"Failed to read frame at index {frame_index} from {video_path.name}")
        return frame
    finally:
        cap.release()


def extract_representative_frame(video_path: Path, metadata: VideoMetadata) -> np.ndarray:
    """Extract an informative representative frame for watermark selection.

    Selects a frame at ~10% into the video (or middle if short) to avoid black intro/fade-in frames.
    """
    target_idx = 0
    if metadata.frame_count > 10:
        target_idx = min(int(metadata.frame_count * 0.1), metadata.frame_count - 1)
    elif metadata.frame_count > 1:
        target_idx = metadata.frame_count // 2

    logger.debug("Extracting representative frame at index %d / %d", target_idx, metadata.frame_count)
    return extract_frame_at_index(video_path, target_idx)


def create_video_writer(
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    fourcc_code: str = "mp4v",
) -> cv2.VideoWriter:
    """Create an OpenCV VideoWriter for intermediate frame storage."""
    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*fourcc_code)
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        # Fallback to alternate codecs if mp4v fails on platform
        for alt_codec in ("avc1", "XVID", "MJPG"):
            fourcc_alt = cv2.VideoWriter_fourcc(*alt_codec)
            writer = cv2.VideoWriter(str(out_path), fourcc_alt, fps, (width, height))
            if writer.isOpened():
                break

    if not writer.isOpened():
        raise FourFrameError(f"Failed to initialize video writer at: {out_path}")

    return writer


def iterate_frames(
    cap: cv2.VideoCapture,
    start_frame: int = 0,
    max_frames: int | None = None,
) -> Generator[Tuple[int, np.ndarray], None, None]:
    """Stream frames lazily from a VideoCapture object.

    Yields:
        Tuple of (frame_index, bgr_frame).
    """
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    current_idx = start_frame
    count = 0

    while True:
        if max_frames is not None and count >= max_frames:
            break

        ret, frame = cap.read()
        if not ret or frame is None:
            break

        yield current_idx, frame
        current_idx += 1
        count += 1
