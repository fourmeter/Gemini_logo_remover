"""FourFrame: Local-First In-Browser & Python Video Watermark Removal System."""

from fourframe.ffmpeg import (
    mux_video_with_original_audio,
    validate_output_file,
    verify_ffmpeg_installation,
)
from fourframe.inpaint import (
    InpaintBackend,
    OpenCVInpaintBackend,
    compute_diagnostic_metrics,
)
from fourframe.mask import create_mask_from_roi, overlay_mask_on_frame
from fourframe.metadata import extract_metadata
from fourframe.models import (
    FFmpegNotFoundError,
    FourFrameError,
    InpaintError,
    MetadataError,
    ProcessingConfig,
    ProcessingStats,
    ROI,
    ROIValidationError,
    UserCancelledError,
    VideoMetadata,
)
from fourframe.preview import generate_preview
from fourframe.processor import process_video
from fourframe.selection import (
    DetectionStrategy,
    ManualDetectionStrategy,
    select_watermark_roi,
)
from fourframe.video import (
    create_video_writer,
    extract_frame_at_index,
    extract_representative_frame,
    iterate_frames,
    open_video_reader,
)

__version__ = "1.0.0"
__all__ = [
    "ROI",
    "VideoMetadata",
    "ProcessingConfig",
    "ProcessingStats",
    "FourFrameError",
    "FFmpegNotFoundError",
    "MetadataError",
    "ROIValidationError",
    "InpaintError",
    "UserCancelledError",
    "DetectionStrategy",
    "ManualDetectionStrategy",
    "InpaintBackend",
    "OpenCVInpaintBackend",
    "extract_metadata",
    "select_watermark_roi",
    "create_mask_from_roi",
    "overlay_mask_on_frame",
    "generate_preview",
    "process_video",
    "verify_ffmpeg_installation",
    "mux_video_with_original_audio",
    "validate_output_file",
    "open_video_reader",
    "create_video_writer",
    "extract_frame_at_index",
    "extract_representative_frame",
    "iterate_frames",
    "compute_diagnostic_metrics",
]
