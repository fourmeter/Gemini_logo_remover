"""Configuration constants and default settings for FourFrame."""

from pathlib import Path
from typing import Tuple

# Directory structure
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"

# Inpainting defaults & validation bounds
DEFAULT_METHOD: str = "telea"
ALLOWED_METHODS: Tuple[str, ...] = ("telea", "ns")

DEFAULT_RADIUS: int = 3
MIN_RADIUS: int = 1
MAX_RADIUS: int = 20

DEFAULT_PADDING: int = 5
MIN_PADDING: int = 0
MAX_PADDING: int = 100

# Video preview defaults
DEFAULT_PREVIEW_SECONDS: float = 3.0
DEFAULT_PREVIEW_START: float = 0.0

# FFmpeg Encoding Defaults
DEFAULT_CRF: int = 18
MIN_CRF: int = 16
MAX_CRF: int = 28

DEFAULT_PRESET: str = "medium"
ALLOWED_PRESETS: Tuple[str, ...] = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)

DEFAULT_VIDEO_CODEC: str = "libx264"
DEFAULT_AUDIO_CODEC: str = "aac"
DEFAULT_AUDIO_BITRATE: str = "192k"
DEFAULT_PIX_FMT: str = "yuv420p"

# Logging format
LOG_FORMAT: str = "%(levelname)s: %(message)s"
