"""Utilities for bucketed training export and CSV logging."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Optional, Tuple

Bucket = Tuple[str, str, str]  # (direction, position, distance)
DIRECTIONS = ["S", "SE", "E", "NE", "N", "NW", "W", "SW"]
POSITIONS = ["Bot", "Horizon", "Top"]
DISTANCES = ["near", "mid", "far"]

# Numeric prefixes for folder organization (0_far, 1_S, 2_SE, etc.)
DIRECTION_PREFIXES = {
    "far": "0_far",  # Special case for target_far class
    "S": "1_S",
    "SE": "2_SE",
    "E": "3_E",
    "NE": "4_NE",
    "N": "5_N",
    "NW": "6_NW",
    "W": "7_W",
    "SW": "8_SW",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def bucket_from_meta(direction: str, position: str, mean_depth: float) -> Bucket:
    if mean_depth < 10:
        dist = "near"
    elif mean_depth < 30:
        dist = "mid"
    else:
        dist = "far"
    return direction, position, dist


def target_dir(base: Path, bucket: Bucket) -> Path:
    direction, position, dist = bucket
    # For far-only bucket (target_far class), use simplified structure
    if direction is None and position is None:
        return base / DIRECTION_PREFIXES["far"]
    # Use numeric prefix for direction folder
    dir_folder = DIRECTION_PREFIXES.get(direction, direction)
    return base / dir_folder / position / dist


def ensure_bucket_structure(base: Path) -> None:
    """Ensure all bucket folders exist, plus benchmark/ and negative_samples/."""
    # Create benchmark and negative_samples folders (Phase 1 roadmap)
    benchmark_dir = base / "benchmark"
    negative_samples_dir = base / "negative_samples"
    ensure_dir(benchmark_dir)
    ensure_dir(negative_samples_dir)
    
    # Do not overwrite if any bucket already exists with files
    existing_buckets = [
        base / DIRECTION_PREFIXES[d] / p / dist 
        for d in DIRECTIONS for p in POSITIONS for dist in DISTANCES
    ]
    if any(b.exists() and any(b.iterdir()) for b in existing_buckets):
        return
    for b in existing_buckets:
        ensure_dir(b)


def copy_for_training(src_img: Path, target_root: Path, bucket: Bucket) -> Path:
    out_dir = target_dir(target_root, bucket)
    ensure_dir(out_dir)
    dest = out_dir / src_img.name
    dest.write_bytes(src_img.read_bytes())
    return dest


def append_csv(log_path: Path, row: Dict[str, str]) -> None:
    exists = log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not exists:
            writer.writeheader()
        writer.writerow(row)
