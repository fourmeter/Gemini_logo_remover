"""Manual watermark region selection and detection strategy architecture."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import cv2
import numpy as np

from fourframe.models import ROI, ROIValidationError, UserCancelledError

logger = logging.getLogger("fourframe")


class DetectionStrategy(ABC):
    """Abstract interface for watermark detection and tracking strategies.

    Designed so V1's manual fixed-ROI strategy can seamlessly be swapped with
    CSRT, KCF, optical flow, or deep learning trackers in future versions.
    """

    @abstractmethod
    def initialize(self, frame: np.ndarray) -> None:
        """Initialize detector/tracker on the first or representative frame."""

    @abstractmethod
    def update(self, frame: np.ndarray) -> ROI:
        """Update tracking for the current frame and return the detected ROI."""

    @abstractmethod
    def get_roi(self) -> ROI:
        """Retrieve current ROI."""


class ManualDetectionStrategy(DetectionStrategy):
    """V1 Detection Strategy: Uses a fixed user-selected ROI across all frames."""

    def __init__(self, roi: Optional[ROI] = None) -> None:
        self._roi = roi

    def set_roi(self, roi: ROI) -> None:
        """Manually assign or update the ROI."""
        self._roi = roi

    def initialize(self, frame: np.ndarray) -> None:
        """Store the configured ROI or prompt selection if not already set."""
        if self._roi is None:
            self._roi = select_watermark_roi(frame)
        else:
            h, w = frame.shape[:2]
            self._roi.validate_bounds(w, h)

    def update(self, frame: np.ndarray) -> ROI:
        """Return the fixed ROI for the given frame."""
        if self._roi is None:
            raise ROIValidationError("ManualDetectionStrategy has not been initialized with an ROI.")
        return self._roi

    def get_roi(self) -> ROI:
        """Return the currently assigned ROI."""
        if self._roi is None:
            raise ROIValidationError("ROI is not set.")
        return self._roi


def select_watermark_roi(
    frame: np.ndarray,
    window_title: str = "FourFrame - Select Watermark Region (SPACE/ENTER to confirm, C/ESC to cancel)",
) -> ROI:
    """Open an interactive OpenCV selection window allowing the user to select the watermark ROI.

    Args:
        frame: BGR representative frame.
        window_title: Title displayed on the OpenCV window.

    Returns:
        Validated ROI instance.

    Raises:
        UserCancelledError: If user cancels selection or closes window without selecting.
        ROIValidationError: If the selected region is invalid or has 0 dimensions.
    """
    frame_h, frame_w = frame.shape[:2]

    # Create resizable window with intuitive banner guidance
    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
    # Resize window to fit comfortably on screen while maintaining aspect ratio
    max_display_w = 1280
    max_display_h = 720
    scale = min(1.0, max_display_w / frame_w, max_display_h / frame_h)
    display_w = int(frame_w * scale)
    display_h = int(frame_h * scale)
    cv2.resizeWindow(window_title, display_w, display_h)

    logger.info("Opening ROI selection window. Drag bounding box around watermark, then press SPACE/ENTER.")
    print("\n" + "=" * 55)
    print(" INSTRUCTIONS FOR WATERMARK SELECTION:")
    print(" 1. Click and drag your mouse around the visible watermark.")
    print(" 2. Press SPACE or ENTER to confirm.")
    print(" 3. Press 'c' or ESC to cancel.")
    print("=" * 55 + "\n")

    # selectROI returns (x, y, w, h)
    try:
        rect = cv2.selectROI(window_title, frame, showCrosshair=True, fromCenter=False)
    except Exception as exc:
        raise ROIValidationError(f"OpenCV GUI selection failed: {exc}") from exc
    finally:
        cv2.destroyWindow(window_title)

    x, y, w, h = rect

    # User pressed cancel (returns all zeros)
    if w == 0 or h == 0:
        logger.warning("Watermark selection cancelled by user (0 dimensions).")
        raise UserCancelledError("Selection cancelled or zero-size region selected.")

    roi = ROI(x=int(x), y=int(y), width=int(w), height=int(h))
    roi.validate_bounds(frame_w, frame_h)

    logger.info(
        "Watermark ROI selected: x=%d y=%d w=%d h=%d (Bounds inside %dx%d)",
        roi.x,
        roi.y,
        roi.width,
        roi.height,
        frame_w,
        frame_h,
    )
    return roi
