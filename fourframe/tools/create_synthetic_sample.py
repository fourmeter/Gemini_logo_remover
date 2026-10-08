"""Utility to generate a synthetic test video with a visible watermark for demonstration."""

import argparse
from pathlib import Path

import cv2
import numpy as np


def generate_synthetic_video(output_path: Path, duration_sec: int = 3, fps: int = 30) -> Path:
    """Generate an MP4 with gradient animation and a simulated corner watermark."""
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1280, 720
    total_frames = duration_sec * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_file), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(str(out_file), fourcc, float(fps), (width, height))

    wm_x, wm_y, wm_w, wm_h = 1050, 620, 180, 60

    for i in range(total_frames):
        # Create subtle moving color gradient
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        shift = int((i / total_frames) * 255)
        for y in range(0, height, 8):
            color = ((y // 3 + shift) % 255, 120, (255 - y // 3) % 255)
            frame[y : y + 8, :] = color

        # Draw a moving foreground circle to test background texture continuity
        circ_x = int(200 + 800 * (i / total_frames))
        cv2.circle(frame, (circ_x, 360), 60, (0, 220, 255), -1)

        # Draw simulated visible watermark badge in bottom-right corner
        cv2.rectangle(
            frame,
            (wm_x, wm_y),
            (wm_x + wm_w, wm_y + wm_h),
            (240, 240, 240),
            -1,
        )
        cv2.putText(
            frame,
            "WATERMARK",
            (wm_x + 12, wm_y + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )

        writer.write(frame)

    writer.release()
    print(f"Generated synthetic test video ({width}x{height}, {duration_sec}s, {total_frames} frames):")
    print(f"  Path:          {out_file}")
    print(f"  Watermark ROI: x={wm_x}, y={wm_y}, width={wm_w}, height={wm_h}")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Create synthetic test video with watermark.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("input/sample.mp4"),
        help="Destination path for test video",
    )
    parser.add_argument("--duration", "-d", type=int, default=3, help="Duration in seconds")
    args = parser.parse_args()

    generate_synthetic_video(args.output, duration_sec=args.duration)


if __name__ == "__main__":
    main()
