"""Shared configuration defaults for the SVO2 Handler."""
from pathlib import Path
from typing import List

# Prefer the actual mounted path (DRONE_DATA1) but allow fallback to DRONE_DATA.
CANDIDATE_OUTPUT_BASES: List[Path] = [
    Path("/media/angelo/DRONE_DATA1"),
    Path("/media/angelo/DRONE_DATA"),
]


def pick_default_output_root() -> Path:
    """Return the default export root based on existing mount points."""
    for base in CANDIDATE_OUTPUT_BASES:
        if base.exists():
            return base / "SVO2_Frame_Export"
    return CANDIDATE_OUTPUT_BASES[0] / "SVO2_Frame_Export"


# Default export root on the USB stick
DEFAULT_OUTPUT_ROOT = pick_default_output_root()

# Supported stream labels for clarity across UI and manifests
STREAM_LEFT = "left"
STREAM_RIGHT = "right"

# Default target FPS fallback when source metadata is not yet loaded
DEFAULT_TARGET_FPS = 10

# Depth mode options (string identifiers to map to pyzed.sl.DEPTH_MODE)
DEPTH_MODES = [
    "NEURAL_PLUS",
    "NEURAL",
    "ULTRA",
    "QUALITY",
    "PERFORMANCE",
    "NONE",
]
DEFAULT_DEPTH_MODE = "NEURAL_PLUS"

# Default training root (can be overridden in UI; persisted)
DEFAULT_TRAINING_ROOT = "/media/angelo/DRONE_DATA1/YoloTrainingV1"
