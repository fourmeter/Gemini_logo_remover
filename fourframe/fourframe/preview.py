"""Preview generation and visual inspection module."""

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from config import TEMP_DIR
from fourframe.inpaint import InpaintBackend
from fourframe.mask import create_mask_from_roi, overlay_mask_on_frame
from fourframe.models import ProcessingConfig, ROI, VideoMetadata
from fourframe.video import create_video_writer, iterate_frames, open_video_reader

logger = logging.getLogger("fourframe")


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS format."""
    total_sec = max(0, int(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def create_comparison_composite(
    original: np.ndarray,
    mask: np.ndarray,
    inpainted: np.ndarray,
    label_text: str = "",
) -> np.ndarray:
    """Create a side-by-side comparison tile: [Original | Mask Overlay | Inpainted]."""
    h, w = original.shape[:2]

    # Mask visualization: overlay red on original
    mask_visual = overlay_mask_on_frame(original, mask, color=(0, 0, 255), alpha=0.6)

    # Label banners at top
    def add_label(img: np.ndarray, text: str) -> np.ndarray:
        labeled = img.copy()
        cv2.rectangle(labeled, (0, 0), (w, 36), (20, 20, 20), -1)
        cv2.putText(
            labeled,
            text,
            (14, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return labeled

    img1 = add_label(original, "1. ORIGINAL")
    img2 = add_label(mask_visual, "2. MASK OVERLAY")
    img3 = add_label(inpainted, "3. INPAINTED (PREVIEW)")

    # Stack horizontally
    composite = np.hstack([img1, img2, img3])

    if label_text:
        bar = np.zeros((40, composite.shape[1], 3), dtype=np.uint8)
        cv2.putText(
            bar,
            label_text,
            (20, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (100, 255, 100),
            1,
            cv2.LINE_AA,
        )
        composite = np.vstack([bar, composite])

    return composite


def generate_preview(
    video_path: Path,
    metadata: VideoMetadata,
    roi: ROI,
    config: ProcessingConfig,
    inpaint_backend: InpaintBackend,
    start_time_seconds: float = 0.0,
    preview_output_dir: Optional[Path] = None,
    interactive_display: bool = True,
) -> Tuple[Path, Path]:
    """Generate and display a short reconstruction preview before full video processing.

    Args:
        video_path: Source video path.
        metadata: Video metadata.
        roi: Watermark region.
        config: Processing configuration.
        inpaint_backend: Selected inpainting backend.
        start_time_seconds: Starting offset in video.
        preview_output_dir: Directory for temporary preview artifacts.
        interactive_display: Whether to open OpenCV display window.

    Returns:
        Tuple of (preview_video_path, preview_image_path).
    """
    config.validate()

    out_dir = Path(preview_output_dir or TEMP_DIR).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    fps = metadata.fps if metadata.fps > 0 else 30.0
    start_frame = int(round(start_time_seconds * fps))
    total_preview_frames = int(round(config.preview_seconds * fps))

    # Ensure bounds
    if metadata.frame_count > 0:
        start_frame = min(start_frame, max(0, metadata.frame_count - 1))
        end_frame = min(start_frame + total_preview_frames, metadata.frame_count)
    else:
        end_frame = start_frame + total_preview_frames

    actual_frames = max(1, end_frame - start_frame)
    end_time_seconds = start_time_seconds + (actual_frames / fps)

    # Print exact requested preview report
    print("\nPreview:")
    print(f"Start:  {format_timestamp(start_time_seconds)}")
    print(f"End:    {format_timestamp(end_time_seconds)}")
    print(f"Frames: {actual_frames}\n")

    logger.info(
        "Rendering preview (%d frames, %s to %s)",
        actual_frames,
        format_timestamp(start_time_seconds),
        format_timestamp(end_time_seconds),
    )

    cap = open_video_reader(video_path)
    preview_video_path = out_dir / "preview_reconstruction.mp4"
    preview_image_path = out_dir / "preview_comparison.png"

    writer = create_video_writer(
        preview_video_path,
        metadata.width,
        metadata.height,
        fps,
    )

    representative_composite: Optional[np.ndarray] = None
    processed_count = 0

    try:
        for idx, frame in iterate_frames(cap, start_frame=start_frame, max_frames=actual_frames):
            mask = create_mask_from_roi(
                frame.shape,
                roi,
                padding=config.padding,
                shape=config.mask_shape,
                dilation_iterations=config.dilation_iterations,
            )

            inpainted = inpaint_backend.inpaint(frame, mask, config)
            writer.write(inpainted)

            # Capture middle frame as comparison composite image
            if representative_composite is None or processed_count == actual_frames // 2:
                info_text = (
                    f"FourFrame Preview | Method: {config.method.upper()} | "
                    f"Radius: {config.radius} | Padding: {config.padding}px | ROI: {roi.to_dict()}"
                )
                representative_composite = create_comparison_composite(
                    frame, mask, inpainted, label_text=info_text
                )

            processed_count += 1
    finally:
        cap.release()
        writer.release()

    if representative_composite is not None:
        cv2.imwrite(str(preview_image_path), representative_composite)
        logger.info("Saved comparison preview image: %s", preview_image_path)

    # Interactive GUI display window if supported
    if interactive_display and representative_composite is not None:
        win_name = "FourFrame Preview - [1. Original | 2. Mask | 3. Inpainted] - Press ANY KEY to close"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        # Scale window for display
        comp_h, comp_w = representative_composite.shape[:2]
        max_w = 1600
        max_h = 750
        scale = min(1.0, max_w / comp_w, max_h / comp_h)
        cv2.resizeWindow(win_name, int(comp_w * scale), int(comp_h * scale))
        cv2.imshow(win_name, representative_composite)
        cv2.waitKey(0)
        cv2.destroyWindow(win_name)

    logger.info("Preview completed.")
    return preview_video_path, preview_image_path
