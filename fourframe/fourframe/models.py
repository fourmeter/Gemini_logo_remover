"""Domain models and dataclasses for the FourFrame video watermark removal system."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from config import (
    ALLOWED_METHODS,
    ALLOWED_PRESETS,
    DEFAULT_CRF,
    DEFAULT_METHOD,
    DEFAULT_PADDING,
    DEFAULT_PRESET,
    DEFAULT_PREVIEW_SECONDS,
    DEFAULT_RADIUS,
    MAX_CRF,
    MAX_PADDING,
    MAX_RADIUS,
    MIN_CRF,
    MIN_PADDING,
    MIN_RADIUS,
)


class FourFrameError(Exception):
    """Base exception for all FourFrame errors."""


class FFmpegNotFoundError(FourFrameError):
    """Raised when ffmpeg or ffprobe binaries are not found on the system."""


class MetadataError(FourFrameError):
    """Raised when video metadata cannot be read or validated."""


class ROIValidationError(FourFrameError):
    """Raised when a selected region of interest is invalid or outside frame bounds."""


class InpaintError(FourFrameError):
    """Raised when inpainting parameters or execution fail."""


class UserCancelledError(FourFrameError):
    """Raised when user cancels interactive selection or workflow."""


@dataclass(frozen=True)
class ROI:
    """Represents a rectangular Region Of Interest on a video frame."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Validate non-negative coordinates and positive dimensions."""
        if self.x < 0:
            raise ROIValidationError(f"ROI x coordinate cannot be negative: {self.x}")
        if self.y < 0:
            raise ROIValidationError(f"ROI y coordinate cannot be negative: {self.y}")
        if self.width <= 0:
            raise ROIValidationError(f"ROI width must be strictly positive (>0), got: {self.width}")
        if self.height <= 0:
            raise ROIValidationError(f"ROI height must be strictly positive (>0), got: {self.height}")

    @property
    def x2(self) -> int:
        """Right edge coordinate."""
        return self.x + self.width

    @property
    def y2(self) -> int:
        """Bottom edge coordinate."""
        return self.y + self.height

    def validate_bounds(self, frame_width: int, frame_height: int) -> None:
        """Verify the ROI is fully contained within the frame dimensions."""
        if self.x >= frame_width or self.y >= frame_height:
            raise ROIValidationError(
                f"ROI origin ({self.x}, {self.y}) lies outside frame boundary ({frame_width}x{frame_height})"
            )
        if self.x2 > frame_width or self.y2 > frame_height:
            raise ROIValidationError(
                f"ROI extends beyond frame boundary: right={self.x2} (max {frame_width}), "
                f"bottom={self.y2} (max {frame_height})"
            )

    def with_padding(self, padding: int, frame_width: int, frame_height: int) -> "ROI":
        """Return a new ROI expanded by padding and clamped to frame boundaries."""
        if padding < 0:
            raise ROIValidationError(f"Padding cannot be negative: {padding}")

        x1 = max(0, self.x - padding)
        y1 = max(0, self.y - padding)
        x2 = min(frame_width, self.x2 + padding)
        y2 = min(frame_height, self.y2 + padding)

        return ROI(x=x1, y=y1, width=max(1, x2 - x1), height=max(1, y2 - y1))

    def to_dict(self) -> Dict[str, int]:
        """Convert ROI to standard dictionary format."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class VideoMetadata:
    """Comprehensive video file metadata parsed via FFprobe."""

    path: Path
    filename: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float
    has_audio: bool
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    pixel_format: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata for logging and reporting."""
        return {
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 3),
            "frame_count": self.frame_count,
            "duration": round(self.duration, 3),
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "has_audio": self.has_audio,
            "pixel_format": self.pixel_format,
        }


@dataclass
class ProcessingConfig:
    """Parameters governing watermark inpainting and encoding."""

    padding: int = DEFAULT_PADDING
    radius: int = DEFAULT_RADIUS
    method: str = DEFAULT_METHOD
    crf: int = DEFAULT_CRF
    preset: str = DEFAULT_PRESET
    preview_seconds: float = DEFAULT_PREVIEW_SECONDS
    mask_shape: str = "rectangle"  # 'rectangle' or 'ellipse'
    dilation_iterations: int = 0

    def validate(self) -> None:
        """Validate all configuration attributes strictly."""
        if self.method.lower() not in ALLOWED_METHODS:
            raise InpaintError(
                f"Invalid inpaint method '{self.method}'. Allowed: {', '.join(ALLOWED_METHODS)}"
            )

        if not (MIN_RADIUS <= self.radius <= MAX_RADIUS):
            raise InpaintError(
                f"Inpainting radius must be between {MIN_RADIUS} and {MAX_RADIUS}, got {self.radius}"
            )

        if not (MIN_PADDING <= self.padding <= MAX_PADDING):
            raise InpaintError(
                f"Padding must be between {MIN_PADDING} and {MAX_PADDING}, got {self.padding}"
            )

        if not (MIN_CRF <= self.crf <= MAX_CRF):
            raise InpaintError(
                f"CRF must be between {MIN_CRF} and {MAX_CRF}, got {self.crf}"
            )

        if self.preset.lower() not in ALLOWED_PRESETS:
            raise InpaintError(
                f"Invalid FFmpeg preset '{self.preset}'. Allowed: {', '.join(ALLOWED_PRESETS)}"
            )

        if self.preview_seconds <= 0:
            raise InpaintError(
                f"Preview duration must be positive, got {self.preview_seconds}"
            )

        if self.mask_shape not in ("rectangle", "ellipse"):
            raise InpaintError(
                f"Invalid mask shape '{self.mask_shape}'. Allowed: 'rectangle', 'ellipse'"
            )


@dataclass
class ProcessingStats:
    """Comparative metrics and quality diagnostics collected after processing."""

    input_path: Path
    output_path: Path
    input_resolution: str
    output_resolution: str
    input_fps: float
    output_fps: float
    input_duration: float
    output_duration: float
    input_size_bytes: int
    output_size_bytes: int
    total_frames_processed: int
    elapsed_seconds: float
    average_processing_fps: float
    diagnostic_mae: Optional[float] = None
    diagnostic_psnr: Optional[float] = None

    def format_summary(self) -> str:
        """Format an informative summary table."""
        in_mb = self.input_size_bytes / (1024 * 1024)
        out_mb = self.output_size_bytes / (1024 * 1024)

        diag_text = ""
        if self.diagnostic_mae is not None:
            diag_text += (
                f"\nDiagnostic MAE (ROI delta):    {self.diagnostic_mae:.2f}\n"
                f"Diagnostic PSNR:              {self.diagnostic_psnr:.2f} dB\n"
                "Note: Diagnostic metric -- not a perceptual quality guarantee."
            )

        return (
            "==================================================\n"
            "FourFrame Processing Summary\n"
            "==================================================\n"
            f"Input file:                   {self.input_path.name}\n"
            f"Output file:                  {self.output_path.name}\n"
            f"Resolution:                   {self.input_resolution} -> {self.output_resolution}\n"
            f"Frame Rate:                   {self.input_fps:.2f} -> {self.output_fps:.2f} FPS\n"
            f"Duration:                     {self.input_duration:.2f}s -> {self.output_duration:.2f}s\n"
            f"File Size:                    {in_mb:.2f} MB -> {out_mb:.2f} MB\n"
            f"Frames Processed:             {self.total_frames_processed}\n"
            f"Processing Time:              {self.elapsed_seconds:.2f}s ({self.average_processing_fps:.1f} FPS)\n"
            f"{diag_text}\n"
            "=================================================="
        )
