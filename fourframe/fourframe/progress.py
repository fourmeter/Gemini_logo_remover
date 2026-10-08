"""Terminal progress tracker and performance estimator."""

import sys
import time
from typing import Optional


class ProgressTracker:
    """Tracks frame processing throughput, percentage completion, and ETA."""

    def __init__(self, total_frames: int, description: str = "Processing") -> None:
        self.total_frames = max(1, total_frames)
        self.description = description
        self.processed_frames = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_frames = 0
        self.current_fps: float = 0.0

    def update(self, count: int = 1) -> None:
        """Increment processed frames count and periodically display progress."""
        self.processed_frames += count
        now = time.time()

        # Update metrics every ~0.25 seconds or at completion
        if (now - self.last_update_time >= 0.25) or (self.processed_frames >= self.total_frames):
            delta_time = now - self.last_update_time
            delta_frames = self.processed_frames - self.last_frames
            if delta_time > 0:
                self.current_fps = delta_frames / delta_time

            self.last_update_time = now
            self.last_frames = self.processed_frames
            self._render()

    @property
    def percent(self) -> float:
        """Percentage of completion (0.0 to 100.0)."""
        return min(100.0, (self.processed_frames / self.total_frames) * 100.0)

    @property
    def eta_seconds(self) -> Optional[int]:
        """Estimated seconds remaining until completion."""
        elapsed = time.time() - self.start_time
        if self.processed_frames <= 0 or elapsed <= 0:
            return None
        rate = self.processed_frames / elapsed
        remaining = self.total_frames - self.processed_frames
        return max(0, int(remaining / rate)) if rate > 0 else None

    def _render(self) -> None:
        """Render clean terminal progress line."""
        pct = self.percent
        eta_str = f"{self.eta_seconds}s" if self.eta_seconds is not None else "--"
        fps_str = f"{self.current_fps:.1f}" if self.current_fps > 0 else "--"

        bar_len = 24
        filled = int(bar_len * (pct / 100.0))
        bar = "=" * filled + "-" * (bar_len - filled)

        line = (
            f"\r{self.description}: [{bar}] {pct:5.1f}% | "
            f"{self.processed_frames}/{self.total_frames} frames | "
            f"FPS: {fps_str} | ETA: {eta_str}"
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    def close(self) -> None:
        """Finalize progress bar and print summary newline."""
        self._render()
        sys.stdout.write("\n")
        sys.stdout.flush()
