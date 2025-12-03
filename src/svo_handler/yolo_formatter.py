"""Convert 73-bucket YOLO training structure to standard YOLO format.

This module handles the preparation of training data for YOLO model training:
- Copies images from 73-bucket structure to YOLO-compatible layout
- Generates train/val/test splits with configurable ratios
- Creates data.yaml with class definitions
- Handles negative samples as background class
- CRITICAL: Always COPIES files, never modifies the original training folder
"""
from __future__ import annotations

import random
import shutil
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .training_export import DIRECTIONS, POSITIONS, DISTANCES


@dataclass
class YoloFormatConfig:
    """Configuration for YOLO format conversion."""
    
    source_root: Path  # Original 73-bucket training folder
    output_root: Path  # Destination for YOLO-formatted dataset
    train_ratio: float = 0.7  # 70% training
    val_ratio: float = 0.2    # 20% validation
    test_ratio: float = 0.1   # 10% test
    include_negative_samples: bool = True
    shuffle: bool = True
    random_seed: int = 42
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        total = self.train_ratio + self.val_ratio + self.test_ratio
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        
        if not self.source_root.exists():
            raise ValueError(f"Source root does not exist: {self.source_root}")


@dataclass
class YoloDataset:
    """Represents a formatted YOLO dataset."""
    
    images_dir: Path
    labels_dir: Path
    train_images: List[Path]
    val_images: List[Path]
    test_images: List[Path]
    classes: Dict[int, str]
    data_yaml_path: Path


class YoloFormatter:
    """Converts 73-bucket structure to YOLO-compatible format.
    
    Output structure:
        output_root/
        ├── images/
        │   ├── train/
        │   ├── val/
        │   └── test/
        ├── labels/
        │   ├── train/
        │   ├── val/
        │   └── test/
        ├── data.yaml
        ├── train.txt
        ├── val.txt
        └── test.txt
    """
    
    def __init__(self, config: YoloFormatConfig):
        self.config = config
        self.classes = {
            0: "target_close",  # Within sensor range (0-40m), has depth
            1: "target_far",    # Beyond range (>40m), no depth
        }
        
        # Set random seed for reproducibility
        random.seed(config.random_seed)
    
    def format_dataset(self) -> YoloDataset:
        """Convert 73-bucket structure to YOLO format.
        
        Returns:
            YoloDataset with paths to formatted data.
        """
        # Create output directory structure
        self._create_output_dirs()
        
        # Collect all image-label pairs from source
        all_pairs = self._collect_image_pairs()
        
        # Split into train/val/test
        train_pairs, val_pairs, test_pairs = self._split_dataset(all_pairs)
        
        # Copy files to YOLO structure
        train_images = self._copy_split(train_pairs, "train")
        val_images = self._copy_split(val_pairs, "val")
        test_images = self._copy_split(test_pairs, "test")
        
        # Generate data.yaml
        data_yaml_path = self._generate_data_yaml()
        
        # Generate split files (train.txt, val.txt, test.txt)
        self._generate_split_files(train_images, val_images, test_images)
        
        return YoloDataset(
            images_dir=self.config.output_root / "images",
            labels_dir=self.config.output_root / "labels",
            train_images=train_images,
            val_images=val_images,
            test_images=test_images,
            classes=self.classes,
            data_yaml_path=data_yaml_path,
        )
    
    def _create_output_dirs(self) -> None:
        """Create YOLO output directory structure."""
        base = self.config.output_root
        base.mkdir(parents=True, exist_ok=True)
        
        for split in ["train", "val", "test"]:
            (base / "images" / split).mkdir(parents=True, exist_ok=True)
            (base / "labels" / split).mkdir(parents=True, exist_ok=True)
    
    def _collect_image_pairs(self) -> List[Tuple[Path, Optional[Path], int]]:
        """Collect all image-label pairs from 73-bucket structure.
        
        Returns:
            List of (image_path, label_path, class_id) tuples.
        """
        pairs = []
        
        # Collect target_far images (0_far bucket, class 1)
        far_dir = self.config.source_root / "0_far"
        if far_dir.exists():
            for img in sorted(far_dir.glob("*.jpg")):
                label = img.with_suffix(".txt")
                pairs.append((img, label if label.exists() else None, 1))
        
        # Collect target_close images (directional buckets, class 0)
        for direction in DIRECTIONS:
            # Check both with and without numeric prefix
            for prefix in [f"{DIRECTIONS.index(direction) + 1}_{direction}", direction]:
                dir_path = self.config.source_root / prefix
                if dir_path.exists():
                    for position in POSITIONS:
                        for distance in DISTANCES:
                            bucket_path = dir_path / position / distance
                            if bucket_path.exists():
                                for img in sorted(bucket_path.glob("*.jpg")):
                                    label = img.with_suffix(".txt")
                                    pairs.append((img, label if label.exists() else None, 0))
                    break  # Found the directory, no need to check other prefix
        
        # Optionally include negative samples (no object, no label)
        if self.config.include_negative_samples:
            neg_dir = self.config.source_root / "negative_samples"
            if neg_dir.exists():
                for img in sorted(neg_dir.glob("*.jpg")):
                    # Negative samples have no label (indicates no objects)
                    pairs.append((img, None, -1))  # -1 indicates negative sample
        
        return pairs
    
    def _split_dataset(
        self,
        pairs: List[Tuple[Path, Optional[Path], int]]
    ) -> Tuple[
        List[Tuple[Path, Optional[Path], int]],
        List[Tuple[Path, Optional[Path], int]],
        List[Tuple[Path, Optional[Path], int]]
    ]:
        """Split dataset into train/val/test sets.
        
        Args:
            pairs: List of (image, label, class_id) tuples.
        
        Returns:
            Tuple of (train_pairs, val_pairs, test_pairs).
        """
        if self.config.shuffle:
            pairs = pairs.copy()
            random.shuffle(pairs)
        
        total = len(pairs)
        train_count = int(total * self.config.train_ratio)
        val_count = int(total * self.config.val_ratio)
        
        train_pairs = pairs[:train_count]
        val_pairs = pairs[train_count:train_count + val_count]
        test_pairs = pairs[train_count + val_count:]
        
        return train_pairs, val_pairs, test_pairs
    
    def _copy_split(
        self,
        pairs: List[Tuple[Path, Optional[Path], int]],
        split: str
    ) -> List[Path]:
        """Copy images and labels for a specific split.
        
        Args:
            pairs: List of (image, label, class_id) tuples.
            split: One of "train", "val", "test".
        
        Returns:
            List of copied image paths.
        """
        images_dir = self.config.output_root / "images" / split
        labels_dir = self.config.output_root / "labels" / split
        copied_images = []
        
        for img_path, label_path, class_id in pairs:
            # Copy image
            dest_img = images_dir / img_path.name
            shutil.copy2(img_path, dest_img)
            copied_images.append(dest_img)
            
            # Copy or skip label
            if label_path and label_path.exists():
                dest_label = labels_dir / label_path.name
                shutil.copy2(label_path, dest_label)
            # Negative samples have no label (intentionally)
        
        return copied_images
    
    def _generate_data_yaml(self) -> Path:
        """Generate YOLO data.yaml configuration file.
        
        Returns:
            Path to generated data.yaml.
        """
        data_yaml_path = self.config.output_root / "data.yaml"
        
        # Paths must be absolute for YOLO training
        train_path = (self.config.output_root / "images" / "train").resolve()
        val_path = (self.config.output_root / "images" / "val").resolve()
        test_path = (self.config.output_root / "images" / "test").resolve()
        
        data = {
            "path": str(self.config.output_root.resolve()),
            "train": str(train_path),
            "val": str(val_path),
            "test": str(test_path),
            "nc": len(self.classes),  # Number of classes
            "names": list(self.classes.values()),  # Class names in order
        }
        
        with open(data_yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        return data_yaml_path
    
    def _generate_split_files(
        self,
        train_images: List[Path],
        val_images: List[Path],
        test_images: List[Path]
    ) -> None:
        """Generate train.txt, val.txt, test.txt with image paths.
        
        These files are sometimes used by YOLO training scripts.
        """
        def write_split_file(images: List[Path], filename: str) -> None:
            split_file = self.config.output_root / filename
            with open(split_file, 'w') as f:
                for img in images:
                    f.write(f"{img.resolve()}\n")
        
        write_split_file(train_images, "train.txt")
        write_split_file(val_images, "val.txt")
        write_split_file(test_images, "test.txt")


def format_yolo_dataset(
    source_root: Path,
    output_root: Path,
    train_ratio: float = 0.7,
    val_ratio: float = 0.2,
    test_ratio: float = 0.1,
    include_negative_samples: bool = True,
    shuffle: bool = True,
    random_seed: int = 42
) -> YoloDataset:
    """Convenience function to format a YOLO dataset.
    
    Args:
        source_root: Path to 73-bucket training folder.
        output_root: Path to output formatted dataset.
        train_ratio: Fraction of data for training (default 0.7).
        val_ratio: Fraction of data for validation (default 0.2).
        test_ratio: Fraction of data for testing (default 0.1).
        include_negative_samples: Include negative samples as background (default True).
        shuffle: Shuffle data before splitting (default True).
        random_seed: Random seed for reproducibility (default 42).
    
    Returns:
        YoloDataset with paths to formatted data.
    """
    config = YoloFormatConfig(
        source_root=source_root,
        output_root=output_root,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        include_negative_samples=include_negative_samples,
        shuffle=shuffle,
        random_seed=random_seed,
    )
    
    formatter = YoloFormatter(config)
    return formatter.format_dataset()
