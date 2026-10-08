"""Inpainting backend interface and OpenCV implementations."""

import logging
import math
from abc import ABC, abstractmethod
from typing import Tuple

import cv2
import numpy as np

from fourframe.models import InpaintError, ProcessingConfig, ROI

logger = logging.getLogger("fourframe")


class InpaintBackend(ABC):
    """Abstract base class for frame inpainting engines.

    Allows modular addition of future backends (e.g. OpenCV CUDA, ONNX, PyTorch)
    without modifying video processing loops.
    """

    @abstractmethod
    def inpaint(self, frame: np.ndarray, mask: np.ndarray, config: ProcessingConfig) -> np.ndarray:
        """Inpaint the masked regions of the input frame.

        Args:
            frame: uint8 BGR image.
            mask: uint8 binary mask (255=masked area).
            config: Processing parameters (radius, method, etc.).

        Returns:
            Inpainted BGR image.
        """


class OpenCVInpaintBackend(InpaintBackend):
    """CPU Inpainting implementation using standard OpenCV cv2.inpaint algorithms."""

    METHOD_MAP = {
        "telea": cv2.INPAINT_TELEA,
        "ns": cv2.INPAINT_NS,
    }

    def inpaint(self, frame: np.ndarray, mask: np.ndarray, config: ProcessingConfig) -> np.ndarray:
        """Execute OpenCV inpainting with strict parameter validation."""
        config.validate()

        method_key = config.method.lower().strip()
        if method_key not in self.METHOD_MAP:
            raise InpaintError(
                f"Unknown OpenCV inpaint method: '{config.method}'. "
                f"Available methods: {list(self.METHOD_MAP.keys())}"
            )

        cv_flag = self.METHOD_MAP[method_key]
        radius = float(config.radius)

        try:
            inpainted = cv2.inpaint(frame, mask, radius, cv_flag)
            return inpainted
        except cv2.error as exc:
            raise InpaintError(f"OpenCV inpaint kernel failed: {exc}") from exc


def compute_diagnostic_metrics(
    original_frame: np.ndarray,
    inpainted_frame: np.ndarray,
    roi: ROI,
) -> Tuple[float, float]:
    """Compute diagnostic MAE and PSNR over the selected ROI.

    Important:
    "Diagnostic metric — not a perceptual quality guarantee."
    Provided solely as a mathematical comparison indicator.

    Returns:
        Tuple of (MAE, PSNR_dB).
    """
    orig_crop = original_frame[roi.y : roi.y2, roi.x : roi.x2].astype(np.float64)
    inp_crop = inpainted_frame[roi.y : roi.y2, roi.x : roi.x2].astype(np.float64)

    diff = np.abs(orig_crop - inp_crop)
    mae = float(np.mean(diff))

    mse = float(np.mean((orig_crop - inp_crop) ** 2))
    if mse <= 1e-10:
        psnr = 100.0  # Identical images
    else:
        psnr = 20.0 * math.log10(255.0 / math.sqrt(mse))

    return mae, psnr
