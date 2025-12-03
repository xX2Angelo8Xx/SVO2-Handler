"""Data models for frame export options."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import DEFAULT_OUTPUT_ROOT, STREAM_LEFT, DEFAULT_DEPTH_MODE


@dataclass
class FrameExportOptions:
    svo_path: Path
    output_root: Path = DEFAULT_OUTPUT_ROOT
    stream: str = STREAM_LEFT
    source_fps: Optional[int] = None
    total_frames: Optional[int] = None
    target_fps: int = 10
    export_depth: bool = False
    depth_format: str = "npy"  # future: allow raw/bin
    depth_mode: str = DEFAULT_DEPTH_MODE

    @property
    def keep_every(self) -> int:
        """Calculate keep-every-N interval based on source/target FPS."""
        if not self.source_fps or self.source_fps <= 0:
            return 1
        if self.target_fps <= 0:
            return 1
        interval = max(1, int(round(self.source_fps / self.target_fps)))
        return interval
