"""Comprehensive test suite for FourFrame models, masking, inpainting, and validation."""

import math
import sys
from pathlib import Path
import unittest

import numpy as np

# Ensure fourframe root is on Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fourframe.inpaint import OpenCVInpaintBackend, compute_diagnostic_metrics
from fourframe.mask import create_mask_from_roi, overlay_mask_on_frame
from fourframe.metadata import parse_fraction_fps
from fourframe.models import (
    InpaintError,
    ProcessingConfig,
    ROI,
    ROIValidationError,
)
from fourframe.selection import ManualDetectionStrategy


class TestROIValidation(unittest.TestCase):
    """Test Region Of Interest initialization and bounds checks."""

    def test_valid_roi(self) -> None:
        roi = ROI(x=100, y=200, width=50, height=30)
        self.assertEqual(roi.x, 100)
        self.assertEqual(roi.y, 200)
        self.assertEqual(roi.width, 50)
        self.assertEqual(roi.height, 30)
        self.assertEqual(roi.x2, 150)
        self.assertEqual(roi.y2, 230)

    def test_roi_inside_frame(self) -> None:
        roi = ROI(x=0, y=0, width=1920, height=1080)
        # Should not raise
        roi.validate_bounds(1920, 1080)

    def test_roi_outside_frame_width(self) -> None:
        roi = ROI(x=1800, y=100, width=150, height=50)  # x2=1950 > 1920
        with self.assertRaises(ROIValidationError):
            roi.validate_bounds(1920, 1080)

    def test_roi_outside_frame_height(self) -> None:
        roi = ROI(x=100, y=1050, width=50, height=50)  # y2=1100 > 1080
        with self.assertRaises(ROIValidationError):
            roi.validate_bounds(1920, 1080)

    def test_negative_coordinates(self) -> None:
        with self.assertRaises(ROIValidationError):
            ROI(x=-10, y=50, width=100, height=50)
        with self.assertRaises(ROIValidationError):
            ROI(x=50, y=-5, width=100, height=50)

    def test_zero_width(self) -> None:
        with self.assertRaises(ROIValidationError):
            ROI(x=100, y=100, width=0, height=50)

    def test_zero_height(self) -> None:
        with self.assertRaises(ROIValidationError):
            ROI(x=100, y=100, width=50, height=0)

    def test_with_padding(self) -> None:
        roi = ROI(x=100, y=100, width=50, height=50)
        padded = roi.with_padding(padding=10, frame_width=1000, frame_height=1000)
        self.assertEqual(padded.x, 90)
        self.assertEqual(padded.y, 90)
        self.assertEqual(padded.width, 70)
        self.assertEqual(padded.height, 70)

    def test_with_padding_clamped_at_origin(self) -> None:
        roi = ROI(x=5, y=5, width=50, height=50)
        padded = roi.with_padding(padding=10, frame_width=1000, frame_height=1000)
        self.assertEqual(padded.x, 0)
        self.assertEqual(padded.y, 0)
        self.assertEqual(padded.width, 65)  # 0 to 65
        self.assertEqual(padded.height, 65)

    def test_with_padding_clamped_at_boundary(self) -> None:
        roi = ROI(x=950, y=950, width=45, height=45)
        padded = roi.with_padding(padding=10, frame_width=1000, frame_height=1000)
        self.assertEqual(padded.x, 940)
        self.assertEqual(padded.y, 940)
        self.assertEqual(padded.x2, 1000)
        self.assertEqual(padded.y2, 1000)


class TestMaskGeneration(unittest.TestCase):
    """Test uint8 mask generation from ROI."""

    def test_rectangular_mask(self) -> None:
        roi = ROI(x=10, y=20, width=30, height=40)
        mask = create_mask_from_roi((100, 100), roi, padding=0, shape="rectangle")

        self.assertEqual(mask.shape, (100, 100))
        self.assertEqual(mask.dtype, np.uint8)

        # Region inside ROI should be 255
        self.assertEqual(mask[25, 15], 255)
        self.assertEqual(mask[20, 10], 255)
        self.assertEqual(mask[59, 39], 255)

        # Background should be 0
        self.assertEqual(mask[0, 0], 0)
        self.assertEqual(mask[99, 99], 0)
        self.assertEqual(mask[19, 9], 0)

    def test_mask_padding(self) -> None:
        roi = ROI(x=50, y=50, width=20, height=20)
        # Without padding: 50..70
        mask_nopad = create_mask_from_roi((200, 200), roi, padding=0)
        self.assertEqual(np.count_nonzero(mask_nopad), 20 * 20)

        # With 5px padding: 45..75 (30x30 = 900 px)
        mask_pad = create_mask_from_roi((200, 200), roi, padding=5)
        self.assertEqual(np.count_nonzero(mask_pad), 30 * 30)

    def test_elliptical_mask(self) -> None:
        roi = ROI(x=20, y=20, width=60, height=60)
        mask = create_mask_from_roi((100, 100), roi, padding=0, shape="ellipse")
        self.assertEqual(mask.shape, (100, 100))
        # Center should be 255
        self.assertEqual(mask[50, 50], 255)
        # Top-left corner of bounding box (20, 20) should be 0 in ellipse
        self.assertEqual(mask[20, 20], 0)

    def test_mask_overlay(self) -> None:
        frame = np.ones((50, 50, 3), dtype=np.uint8) * 128
        mask = np.zeros((50, 50), dtype=np.uint8)
        mask[10:20, 10:20] = 255
        blended = overlay_mask_on_frame(frame, mask, color=(0, 0, 255), alpha=0.5)
        self.assertEqual(blended.shape, (50, 50, 3))
        # Outside mask remains 128
        self.assertEqual(blended[0, 0, 0], 128)
        # Inside mask has blended color
        self.assertNotEqual(blended[15, 15, 2], 128)


class TestConfigValidation(unittest.TestCase):
    """Test ProcessingConfig parameter boundaries and error handling."""

    def test_default_config_valid(self) -> None:
        cfg = ProcessingConfig()
        cfg.validate()

    def test_invalid_method(self) -> None:
        cfg = ProcessingConfig(method="invalid_algorithm")
        with self.assertRaises(InpaintError):
            cfg.validate()

    def test_invalid_radius_low(self) -> None:
        cfg = ProcessingConfig(radius=0)
        with self.assertRaises(InpaintError):
            cfg.validate()

    def test_invalid_radius_high(self) -> None:
        cfg = ProcessingConfig(radius=25)
        with self.assertRaises(InpaintError):
            cfg.validate()

    def test_invalid_crf_low(self) -> None:
        cfg = ProcessingConfig(crf=10)
        with self.assertRaises(InpaintError):
            cfg.validate()

    def test_invalid_crf_high(self) -> None:
        cfg = ProcessingConfig(crf=35)
        with self.assertRaises(InpaintError):
            cfg.validate()

    def test_invalid_preset(self) -> None:
        cfg = ProcessingConfig(preset="ludicrous_speed")
        with self.assertRaises(InpaintError):
            cfg.validate()

    def test_invalid_padding_negative(self) -> None:
        cfg = ProcessingConfig(padding=-5)
        with self.assertRaises(InpaintError):
            cfg.validate()


class TestInpainting(unittest.TestCase):
    """Test inpainting algorithms and diagnostic metrics."""

    def setUp(self) -> None:
        self.backend = OpenCVInpaintBackend()
        # Synthetic 100x100 BGR image with a blue rectangle
        self.frame = np.full((100, 100, 3), 200, dtype=np.uint8)
        # Add simulated watermark: red text/box
        self.frame[40:60, 40:60] = [0, 0, 255]

        self.roi = ROI(x=40, y=40, width=20, height=20)
        self.mask = create_mask_from_roi((100, 100), self.roi, padding=2)

    def test_telea_inpaint(self) -> None:
        cfg = ProcessingConfig(method="telea", radius=3)
        result = self.backend.inpaint(self.frame, self.mask, cfg)
        self.assertEqual(result.shape, self.frame.shape)
        self.assertEqual(result.dtype, np.uint8)

        # Inpainted center should no longer be pure bright red [0, 0, 255]
        center_color = result[50, 50]
        self.assertFalse(np.array_equal(center_color, [0, 0, 255]))

    def test_ns_inpaint(self) -> None:
        cfg = ProcessingConfig(method="ns", radius=3)
        result = self.backend.inpaint(self.frame, self.mask, cfg)
        self.assertEqual(result.shape, self.frame.shape)

    def test_diagnostic_metrics(self) -> None:
        cfg = ProcessingConfig(method="telea", radius=3)
        inpainted = self.backend.inpaint(self.frame, self.mask, cfg)
        mae, psnr = compute_diagnostic_metrics(self.frame, inpainted, self.roi)
        self.assertGreater(mae, 0.0)
        self.assertFalse(math.isnan(psnr))


class TestDetectionStrategy(unittest.TestCase):
    """Test tracking-ready strategy pattern."""

    def test_manual_strategy(self) -> None:
        roi = ROI(x=10, y=10, width=20, height=20)
        strategy = ManualDetectionStrategy(roi)
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        strategy.initialize(dummy_frame)

        # Returns identical ROI across multiple frames
        frame1_roi = strategy.update(dummy_frame)
        frame2_roi = strategy.update(dummy_frame)
        self.assertEqual(frame1_roi, roi)
        self.assertEqual(frame2_roi, roi)


class TestMetadataUtilities(unittest.TestCase):
    """Test metadata fraction parsing."""

    def test_fps_fractions(self) -> None:
        self.assertEqual(parse_fraction_fps("30/1"), 30.0)
        self.assertAlmostEqual(parse_fraction_fps("30000/1001"), 29.970, places=3)
        self.assertAlmostEqual(parse_fraction_fps("60000/1001"), 59.940, places=3)
        self.assertIsNone(parse_fraction_fps("0/0"))
        self.assertIsNone(parse_fraction_fps(None))
        self.assertIsNone(parse_fraction_fps("invalid"))


if __name__ == "__main__":
    unittest.main()
