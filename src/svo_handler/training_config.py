"""Training configuration for YOLO model training."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional


@dataclass
class TrainingConfig:
    """Configuration for YOLO model training.
    
    This dataclass contains all parameters needed to configure and run
    a YOLO training session, including model selection, hyperparameters,
    augmentation settings, and hardware configuration.
    """
    
    # === Data Configuration ===
    source_training_root: Path  # Original 73-bucket training folder
    output_dataset_root: Path   # Where to create YOLO-formatted dataset
    
    # Data split ratios (must sum to 1.0)
    train_ratio: float = 0.7
    val_ratio: float = 0.2
    test_ratio: float = 0.1
    
    # Include negative samples as background class
    include_negative_samples: bool = True
    
    # Shuffle data before splitting
    shuffle_data: bool = True
    random_seed: int = 42
    
    # === Model Configuration ===
    # YOLO version and variant
    model_type: Literal["yolov5", "yolov8"] = "yolov8"
    model_variant: Literal["n", "s", "m", "l", "x"] = "n"  # nano, small, medium, large, xlarge
    
    # Pretrained weights (None = from scratch, "default" = COCO pretrained, or path to .pt file)
    pretrained_weights: Optional[str] = "default"
    
    # Resume training from checkpoint
    resume_checkpoint: Optional[Path] = None
    
    # === Training Hyperparameters ===
    # Image size (square images)
    image_size: int = 640  # Options: 416, 512, 640, 1280
    
    # Batch size (-1 = auto-detect based on GPU memory)
    batch_size: int = 16
    
    # Number of training epochs
    epochs: int = 100
    
    # Learning rate
    learning_rate: float = 0.01
    
    # Optimizer
    optimizer: Literal["Adam", "SGD", "AdamW"] = "Adam"
    
    # Learning rate scheduler
    lr_scheduler: Literal["cosine", "linear", "step", "none"] = "cosine"
    
    # Momentum (for SGD)
    momentum: float = 0.937
    
    # Weight decay
    weight_decay: float = 0.0005
    
    # === Augmentation Settings ===
    augmentation_preset: Literal["none", "light", "moderate", "heavy"] = "moderate"
    
    # Individual augmentation parameters (override preset if specified)
    aug_hsv_h: float = 0.015  # HSV-Hue augmentation
    aug_hsv_s: float = 0.7    # HSV-Saturation augmentation
    aug_hsv_v: float = 0.4    # HSV-Value augmentation
    aug_degrees: float = 0.0  # Rotation (+/- deg)
    aug_translate: float = 0.1  # Translation (+/- fraction)
    aug_scale: float = 0.5    # Scale (+/- gain)
    aug_shear: float = 0.0    # Shear (+/- deg)
    aug_perspective: float = 0.0  # Perspective (+/- fraction)
    aug_flipud: float = 0.0   # Vertical flip probability
    aug_fliplr: float = 0.5   # Horizontal flip probability
    aug_mosaic: float = 1.0   # Mosaic augmentation probability
    aug_mixup: float = 0.0    # Mixup augmentation probability
    
    # === Hardware Configuration ===
    device: str = "0"  # GPU device (e.g., "0" for cuda:0, "cpu" for CPU, "0,1" for multi-GPU)
    workers: int = 8   # Number of dataloader workers
    
    # === Training Behavior ===
    # Save checkpoint every N epochs
    save_period: int = 10
    
    # Patience for early stopping (0 = disabled)
    patience: int = 50
    
    # Confidence threshold for NMS during validation
    conf_threshold: float = 0.001
    
    # IoU threshold for NMS during validation
    iou_threshold: float = 0.6
    
    # === Output Configuration ===
    # Project name for organizing runs
    project_name: str = "yolo_training"
    
    # Run name (unique identifier for this training session)
    run_name: str = "run_001"
    
    # Save directory (usually derived from project + run name)
    save_dir: Optional[Path] = None
    
    # === Advanced Options ===
    # Cache images for faster training ("ram", "disk", or None)
    cache_images: Optional[Literal["ram", "disk"]] = None
    
    # Use mixed precision training (faster on modern GPUs)
    amp: bool = True
    
    # Perform final evaluation on test set
    eval_test_set: bool = True
    
    # Export formats after training
    export_formats: List[str] = field(default_factory=lambda: ["pt", "onnx"])
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Validate split ratios
        total_ratio = self.train_ratio + self.val_ratio + self.test_ratio
        if abs(total_ratio - 1.0) > 0.001:
            raise ValueError(f"Split ratios must sum to 1.0, got {total_ratio}")
        
        # Validate paths
        if not self.source_training_root.exists():
            raise ValueError(f"Source training root does not exist: {self.source_training_root}")
        
        # Validate image size
        if self.image_size not in [416, 512, 640, 1280]:
            raise ValueError(f"Image size must be one of [416, 512, 640, 1280], got {self.image_size}")
        
        # Validate epochs
        if self.epochs <= 0:
            raise ValueError(f"Epochs must be positive, got {self.epochs}")
        
        # Set default save directory if not specified
        if self.save_dir is None:
            self.save_dir = Path("runs") / self.project_name / self.run_name
    
    def to_yolo_args(self) -> Dict[str, any]:
        """Convert config to YOLO training arguments dictionary.
        
        Returns:
            Dictionary of arguments compatible with ultralytics YOLO API.
        """
        args = {
            # Data
            "data": str(self.output_dataset_root / "data.yaml"),
            "imgsz": self.image_size,
            
            # Model
            "model": self._get_model_path(),
            "pretrained": self.pretrained_weights == "default",
            
            # Training
            "epochs": self.epochs,
            "batch": self.batch_size,
            "optimizer": self.optimizer,
            "lr0": self.learning_rate,
            "momentum": self.momentum,
            "weight_decay": self.weight_decay,
            
            # Augmentation
            "hsv_h": self.aug_hsv_h,
            "hsv_s": self.aug_hsv_s,
            "hsv_v": self.aug_hsv_v,
            "degrees": self.aug_degrees,
            "translate": self.aug_translate,
            "scale": self.aug_scale,
            "shear": self.aug_shear,
            "perspective": self.aug_perspective,
            "flipud": self.aug_flipud,
            "fliplr": self.aug_fliplr,
            "mosaic": self.aug_mosaic,
            "mixup": self.aug_mixup,
            
            # Hardware
            "device": self.device,
            "workers": self.workers,
            
            # Behavior
            "save_period": self.save_period,
            "patience": self.patience,
            "conf": self.conf_threshold,
            "iou": self.iou_threshold,
            
            # Output
            "project": self.project_name,
            "name": self.run_name,
            
            # Advanced
            "cache": self.cache_images,
            "amp": self.amp,
        }
        
        # Add resume if specified
        if self.resume_checkpoint:
            args["resume"] = str(self.resume_checkpoint)
        
        return args
    
    def _get_model_path(self) -> str:
        """Get the model path/name for YOLO training.
        
        Returns:
            Model identifier string (e.g., "yolov8n.pt", "yolov5s.pt").
        """
        if self.resume_checkpoint:
            return str(self.resume_checkpoint)
        
        if self.pretrained_weights and self.pretrained_weights != "default":
            return self.pretrained_weights
        
        # Default: Use model type + variant
        return f"{self.model_type}{self.model_variant}.pt"
    
    def get_summary(self) -> str:
        """Get a human-readable summary of the configuration.
        
        Returns:
            Multi-line string summarizing key configuration parameters.
        """
        lines = [
            "=== YOLO Training Configuration ===",
            f"Model: {self.model_type}{self.model_variant}",
            f"Image Size: {self.image_size}x{self.image_size}",
            f"Batch Size: {self.batch_size}",
            f"Epochs: {self.epochs}",
            f"Learning Rate: {self.learning_rate}",
            f"Optimizer: {self.optimizer}",
            f"Device: {self.device}",
            f"Augmentation: {self.augmentation_preset}",
            "",
            "Dataset:",
            f"  Train: {self.train_ratio:.0%}",
            f"  Val:   {self.val_ratio:.0%}",
            f"  Test:  {self.test_ratio:.0%}",
            f"  Negative Samples: {'Yes' if self.include_negative_samples else 'No'}",
            "",
            f"Output: {self.save_dir}",
        ]
        return "\n".join(lines)


def get_augmentation_preset(preset: Literal["none", "light", "moderate", "heavy"]) -> Dict[str, float]:
    """Get augmentation parameters for a given preset.
    
    Args:
        preset: One of "none", "light", "moderate", "heavy".
    
    Returns:
        Dictionary of augmentation parameters.
    """
    presets = {
        "none": {
            "aug_hsv_h": 0.0,
            "aug_hsv_s": 0.0,
            "aug_hsv_v": 0.0,
            "aug_degrees": 0.0,
            "aug_translate": 0.0,
            "aug_scale": 0.0,
            "aug_shear": 0.0,
            "aug_perspective": 0.0,
            "aug_flipud": 0.0,
            "aug_fliplr": 0.0,
            "aug_mosaic": 0.0,
            "aug_mixup": 0.0,
        },
        "light": {
            "aug_hsv_h": 0.005,
            "aug_hsv_s": 0.3,
            "aug_hsv_v": 0.2,
            "aug_degrees": 0.0,
            "aug_translate": 0.05,
            "aug_scale": 0.25,
            "aug_shear": 0.0,
            "aug_perspective": 0.0,
            "aug_flipud": 0.0,
            "aug_fliplr": 0.5,
            "aug_mosaic": 0.5,
            "aug_mixup": 0.0,
        },
        "moderate": {
            "aug_hsv_h": 0.015,
            "aug_hsv_s": 0.7,
            "aug_hsv_v": 0.4,
            "aug_degrees": 0.0,
            "aug_translate": 0.1,
            "aug_scale": 0.5,
            "aug_shear": 0.0,
            "aug_perspective": 0.0,
            "aug_flipud": 0.0,
            "aug_fliplr": 0.5,
            "aug_mosaic": 1.0,
            "aug_mixup": 0.0,
        },
        "heavy": {
            "aug_hsv_h": 0.03,
            "aug_hsv_s": 0.9,
            "aug_hsv_v": 0.6,
            "aug_degrees": 10.0,
            "aug_translate": 0.2,
            "aug_scale": 0.9,
            "aug_shear": 2.0,
            "aug_perspective": 0.001,
            "aug_flipud": 0.1,
            "aug_fliplr": 0.5,
            "aug_mosaic": 1.0,
            "aug_mixup": 0.1,
        },
    }
    
    return presets.get(preset, presets["moderate"])
