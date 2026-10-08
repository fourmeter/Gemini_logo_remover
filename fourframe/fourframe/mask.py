"""Binary mask generation and visualization utilities."""

from typing import Tuple

import cv2
import numpy as np

from fourframe.models import ROI, ROIValidationError


def create_mask_from_roi(
    frame_shape: Tuple[int, ...],
    roi: ROI,
    padding: int = 5,
    shape: str = "rectangle",
    dilation_iterations: int = 0,
) -> np.ndarray:
    """Generate a uint8 binary mask from a region of interest.

    Watermark pixels are 255; background is 0.

    Args:
        frame_shape: (height, width, ...) of target frame.
        roi: Selected Region of Interest.
        padding: Pixels to expand boundary in each direction (clamped to frame).
        shape: 'rectangle' or 'ellipse'.
        dilation_iterations: Morphological dilation passes to ensure full coverage.

    Returns:
        uint8 numpy array of shape (height, width).
    """
    height, width = frame_shape[:2]
    roi.validate_bounds(width, height)

    padded_roi = roi.with_padding(padding=padding, frame_width=width, frame_height=height)

    # Initialize black mask
    mask = np.zeros((height, width), dtype=np.uint8)

    if shape == "ellipse":
        center = (
            padded_roi.x + padded_roi.width // 2,
            padded_roi.y + padded_roi.height // 2,
        )
        axes = (padded_roi.width // 2, padded_roi.height // 2)
        cv2.ellipse(
            mask,
            center,
            axes,
            angle=0,
            startAngle=0,
            endAngle=360,
            color=255,
            thickness=-1,
        )
    elif shape == "rectangle":
        mask[padded_roi.y : padded_roi.y2, padded_roi.x : padded_roi.x2] = 255
    else:
        raise ROIValidationError(f"Unsupported mask shape: {shape}. Expected 'rectangle' or 'ellipse'")

    if dilation_iterations > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.dilate(mask, kernel, iterations=dilation_iterations)

    return mask


def overlay_mask_on_frame(
    frame: np.ndarray,
    mask: np.ndarray,
    color: Tuple[int, int, int] = (0, 0, 255),
    alpha: float = 0.5,
) -> np.ndarray:
    """Overlay a colored translucent mask on a BGR frame for visual inspection.

    Args:
        frame: BGR frame.
        mask: uint8 single-channel mask (255=watermark).
        color: BGR highlight color (default Red).
        alpha: Blending opacity (0.0 to 1.0).

    Returns:
        Blended BGR frame.
    """
    overlay = frame.copy()
    mask_indices = mask > 0
    overlay[mask_indices] = color
    return cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0)
