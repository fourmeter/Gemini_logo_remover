"""Main frame-by-frame video processing engine."""

import logging
import shutil
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from config import TEMP_DIR
from fourframe.ffmpeg import mux_video_with_original_audio, validate_output_file
from fourframe.inpaint import InpaintBackend, OpenCVInpaintBackend, compute_diagnostic_metrics
from fourframe.mask import create_mask_from_roi
from fourframe.metadata import extract_metadata
from fourframe.models import (
    FourFrameError,
    ProcessingConfig,
    ProcessingStats,
    VideoMetadata,
)
from fourframe.progress import ProgressTracker
from fourframe.selection import DetectionStrategy, ManualDetectionStrategy
from fourframe.video import create_video_writer, iterate_frames, open_video_reader

logger = logging.getLogger("fourframe")


def check_disk_space(target_dir: Path, required_mb: int = 100) -> None:
    """Verify sufficient disk space is available before processing."""
    try:
        total, used, free = shutil.disk_usage(target_dir)
        free_mb = free // (1024 * 1024)
        if free_mb < required_mb:
            raise FourFrameError(
                f"Insufficient disk space in {target_dir}. Available: {free_mb} MB, Required: {required_mb} MB"
            )
    except Exception as exc:
        if isinstance(exc, FourFrameError):
            raise
        logger.debug("Disk space check skipped or failed: %s", exc)


def process_video(
    input_path: Path,
    output_path: Path,
    detection_strategy: DetectionStrategy,
    config: ProcessingConfig,
    metadata: Optional[VideoMetadata] = None,
    inpaint_backend: Optional[InpaintBackend] = None,
    temp_dir: Optional[Path] = None,
    keep_temp: bool = False,
) -> ProcessingStats:
    """Execute complete end-to-end watermark removal workflow on a video file.

    Frame-by-frame processing pipeline:
      1. Read frame.
      2. Update ROI / mask.
      3. Inpaint with OpenCV.
      4. Write frame to intermediate MP4.
      5. Mux with original audio via FFmpeg.
      6. Validate output and clean temp files.

    Args:
        input_path: Input video path.
        output_path: Final output destination path.
        detection_strategy: Initialized detection/tracking strategy.
        config: Processing configuration parameters.
        metadata: Pre-extracted metadata (optional).
        inpaint_backend: Inpainting backend (default OpenCVInpaintBackend).
        temp_dir: Directory for temporary files.
        keep_temp: If True, intermediate files are not deleted.

    Returns:
        ProcessingStats object with full metrics summary.
    """
    in_path = Path(input_path).resolve()
    out_path = Path(output_path).resolve()
    t_dir = Path(temp_dir or TEMP_DIR).resolve()
    t_dir.mkdir(parents=True, exist_ok=True)

    if in_path == out_path:
        raise FourFrameError(
            f"Safety error: Output file cannot be the same as input file ({in_path}). "
            "FourFrame never overwrites input files."
        )

    check_disk_space(t_dir, required_mb=150)
    config.validate()

    if metadata is None:
        metadata = extract_metadata(in_path)

    backend = inpaint_backend or OpenCVInpaintBackend()

    # Unique temporary video name to avoid collisions
    timestamp_id = int(time.time() * 1000)
    temp_video_path = t_dir / f"temp_processed_{timestamp_id}.mp4"

    logger.info("Starting full video processing...")
    logger.info("Resolution: %dx%d", metadata.width, metadata.height)
    logger.info("FPS: %.2f", metadata.fps)
    logger.info("Duration: %.1f seconds (%d frames)", metadata.duration, metadata.frame_count)

    cap = open_video_reader(in_path)
    writer = create_video_writer(
        temp_video_path,
        metadata.width,
        metadata.height,
        metadata.fps,
    )

    tracker = ProgressTracker(
        total_frames=metadata.frame_count,
        description="Inpainting frames",
    )

    diagnostic_maes: List[float] = []
    diagnostic_psnrs: List[float] = []
    start_proc_time = time.time()
    frames_processed = 0

    try:
        for idx, frame in iterate_frames(cap):
            # 1. Update detection strategy for current frame
            current_roi = detection_strategy.update(frame)

            # 2. Generate mask for frame
            mask = create_mask_from_roi(
                frame.shape,
                current_roi,
                padding=config.padding,
                shape=config.mask_shape,
                dilation_iterations=config.dilation_iterations,
            )

            # 3. Perform inpainting
            inpainted = backend.inpaint(frame, mask, config)

            # 4. Write processed frame
            writer.write(inpainted)

            # Periodically compute diagnostic metrics (sample every ~30 frames)
            if idx % 30 == 0:
                mae, psnr = compute_diagnostic_metrics(frame, inpainted, current_roi)
                diagnostic_maes.append(mae)
                diagnostic_psnrs.append(psnr)

            frames_processed += 1
            tracker.update(1)

        tracker.close()

    except Exception as exc:
        tracker.close()
        logger.error("Processing aborted due to error: %s", exc)
        # Clean incomplete temp outputs safely
        if temp_video_path.exists():
            try:
                temp_video_path.unlink()
            except OSError:
                pass
        if out_path.exists():
            try:
                out_path.unlink()
            except OSError:
                pass
        raise FourFrameError(f"Video processing failed during frame loop: {exc}") from exc

    finally:
        cap.release()
        writer.release()

    elapsed_time = time.time() - start_proc_time
    avg_fps = frames_processed / elapsed_time if elapsed_time > 0 else 0.0

    # 5. Mux with original audio using FFmpeg
    logger.info("Running FFmpeg muxer to combine inpainting with original audio...")
    try:
        mux_video_with_original_audio(
            processed_video_path=temp_video_path,
            original_video_path=in_path,
            output_path=out_path,
            config=config,
        )
    finally:
        # Clean temporary raw video unless explicitly kept
        if not keep_temp and temp_video_path.exists():
            try:
                temp_video_path.unlink()
            except OSError:
                pass

    # 6. Quality validation check
    valid, check_msg = validate_output_file(out_path)
    if not valid:
        raise FourFrameError(f"Final video validation check failed on {out_path}: {check_msg}")

    # 7. Collect output statistics
    out_meta = extract_metadata(out_path)
    in_size = in_path.stat().st_size if in_path.exists() else 0
    out_size = out_path.stat().st_size if out_path.exists() else 0

    avg_mae = float(np.mean(diagnostic_maes)) if diagnostic_maes else None
    avg_psnr = float(np.mean(diagnostic_psnrs)) if diagnostic_psnrs else None

    stats = ProcessingStats(
        input_path=in_path,
        output_path=out_path,
        input_resolution=f"{metadata.width}x{metadata.height}",
        output_resolution=f"{out_meta.width}x{out_meta.height}",
        input_fps=metadata.fps,
        output_fps=out_meta.fps,
        input_duration=metadata.duration,
        output_duration=out_meta.duration,
        input_size_bytes=in_size,
        output_size_bytes=out_size,
        total_frames_processed=frames_processed,
        elapsed_seconds=elapsed_time,
        average_processing_fps=avg_fps,
        diagnostic_mae=avg_mae,
        diagnostic_psnr=avg_psnr,
    )

    logger.info("Final output created successfully.")
    return stats
