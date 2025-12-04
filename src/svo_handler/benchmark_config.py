"""
Configuration for benchmark testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class BenchmarkConfig:
    """Configuration for model benchmarking."""

    model_path: Path
    model_format: Literal["pytorch", "onnx", "tensorrt"]
    test_images_path: Path
    has_ground_truth: bool
    image_size: int  # -1 for source resolution
    warmup_iterations: int
    test_iterations: int
    conf_threshold: float
    iou_threshold: float
    test_speed: bool
    test_accuracy: bool
    test_resources: bool
