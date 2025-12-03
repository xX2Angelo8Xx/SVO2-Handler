# SVO2 Handler

Complete desktop toolchain for extracting, annotating, and verifying YOLO training data from ZED `.svo2` recordings. Three integrated GUI applications handle the entire workflow from raw drone footage to verified training datasets.

## Overview

This toolkit processes ZED2i camera recordings (`.svo2` files) from Jetson Orin Nano drone captures into YOLO-ready training data with depth information. The workflow consists of:

1. **Frame Exporter** – Extract RGB frames and 32-bit depth from SVO2 recordings
2. **Viewer/Annotator** – Draw bounding boxes, classify targets, export to training buckets
3. **Annotation Checker** – Verify annotations with zoom and hierarchical navigation
4. **Training GUI** – Train YOLO models with comprehensive configuration and real-time monitoring

Source `.svo2` files use LOSSLESS mode from field tests. See `docs/fieldtest-learnings.md` for capture stack details.

## Applications

### 1. Frame Exporter (`gui_app.py`)
Extract frames and depth data from SVO2 recordings.

**Features:**
- Choose left/right camera stream
- FPS downsampling (source-aware, frame skipping only - no resize)
- Optional 32-bit depth export (`.npy` format)
- Configurable depth mode (NEURAL_PLUS, NEURAL, ULTRA, QUALITY, PERFORMANCE)
- Progress tracking with frame preview
- Export to structured directories

**Launch:** `python -m svo_handler.gui_app`

### 2. Viewer/Annotator (`viewer_app.py`)
Annotate extracted frames with YOLO bounding boxes for training.

**Features:**
- Load RGB + depth pairs from exported frames
- Draw/resize/move bounding boxes
- Depth visualization with adjustable range sliders
- CSRT object tracking for faster annotation
- Two YOLO classes: `target_close` (0-40m) and `target_far` (>40m)
- Export to 72-bucket training structure organized by direction/position/distance
- Keyboard shortcuts (Enter to export + advance)
- 10x zoom for precise annotation
- Cross-bucket duplicate detection
- Export-only workflow (source files never modified)

**Launch:** `python -m svo_handler.viewer_app`

### 3. Annotation Checker (`checker_app.py`)
Verify annotated images with advanced navigation.

**Features:**
- Hierarchical navigation: view entire direction or specific buckets
- Bucket statistics: image counts per sub-bucket
- 5x zoom with mouse wheel + drag to pan
- Visual overlay: class name + bucket path on each annotation
- Arrow key navigation (±1 frame, ±5 frames)
- Dual counters for "all direction" mode (global + bucket position)
- Color-coded annotations (green=target_close, red=target_far)

**Launch:** `python -m svo_handler.checker_app`

### 4. Training GUI (`training_app.py`)
Train YOLO models with automated dataset preparation and monitoring.

**Features:**
- Converts 73-bucket structure to YOLO-compatible format (preserves originals)
- Configurable train/val/test splits with shuffling and random seed
- Model selection: YOLOv5/v8 with variants (n/s/m/l/x)
- Comprehensive training parameters: batch size, epochs, learning rate, optimizer
- Augmentation presets (none/light/moderate/heavy) with individual parameter tuning
- Pretrained weights support (COCO, from scratch, or custom)
- Real-time progress monitoring with training logs
- Automatic data.yaml generation
- Negative samples integration as background class
- Resume from checkpoint support

**Recommended Configuration (Jetson Orin Nano Super)**:
- Model: YOLOv8n (nano variant)
- Image Size: 416x416
- Expected Performance: 50-60 FPS with TensorRT FP16

**Launch:** `python -m svo_handler.training_app`

**See:** [`docs/training-guide.md`](docs/training-guide.md) for comprehensive feature guide and Jetson deployment recommendations

## Quick Start

### Installation
```bash
# Requirements: Python 3.10+, ZED SDK 4.0+
pip install -r requirements.txt

# Note: pyzed wheel included for aarch64 (Jetson)
# For x86_64, install from ZED SDK
```

**⚠️ IMPORTANT - Recommended Hardware Setup:**

**Training** (PC with dedicated GPU recommended):
- Desktop/laptop with NVIDIA RTX 2060+ (6GB+ VRAM)
- Standard PyTorch installation (no special wheels needed)
- Sufficient memory for batch training (16-32GB RAM)
- **Expected**: 1-2 hours for 100 epochs @ 640x640
- **See**: [`docs/pc-setup-guide.md`](docs/pc-setup-guide.md) for PC setup

**Jetson Training NOT Feasible**:
- Jetson Orin Nano 8GB runs out of memory during training
- cuDNN compatibility issues require workarounds
- Complex PyTorch installation with custom wheels
- **Conclusion**: Use Jetson for extraction/annotation/inference only
- **See**: [`docs/jetson-setup-guide.md`](docs/jetson-setup-guide.md) for limitations and [`docs/fieldtest-learnings.md`](docs/fieldtest-learnings.md) for detailed analysis

**Recommended Workflow**:
```
Jetson: SVO2 Capture → Frame Export → Annotation
   ↓ (transfer dataset)
PC: YOLO Training (1-2 hours)
   ↓ (transfer model)
Jetson: TensorRT Inference → Drone Deployment
```

### Basic Workflow
```bash
# 1. Extract frames from SVO2
python -m svo_handler.gui_app
# → Select .svo2 file, choose FPS, enable depth export
# → Frames saved to /media/angelo/DRONE_DATA1/SVO2_Frame_Export/

# 2. Annotate frames
python -m svo_handler.viewer_app
# → Load exported folder, draw bounding boxes
# → Press Enter to export to training bucket
# → Annotations saved to /media/angelo/DRONE_DATA1/YoloTrainingV1/

# 3. Verify annotations
python -m svo_handler.checker_app
# → Open training root, select direction
# → Zoom to inspect, navigate with arrow keys

# 4. Train YOLO model
python -m svo_handler.training_app
# → Select 73-bucket training folder as source
# → Configure model (YOLOv8n recommended for Jetson)
# → Set image size (416 for real-time, 512 for accuracy)
# → Start training, monitor progress
# → Export to TensorRT for Jetson deployment
```

## YOLO Training Structure

Annotations are organized into 72 buckets + 1 far bucket for balanced training:

- **Directions** (9): `0_far`, `1_S`, `2_SE`, `3_E`, `4_NE`, `5_N`, `6_NW`, `7_W`, `8_SW`
- **Positions** (3): `Bot`, `Horizon`, `Top` (vertical frame position)
- **Distances** (3): `near` (<10m), `mid` (10-30m), `far` (>30m or no depth)

**Classes:**
- `target_close` (class 0): Within sensor range, has depth data
- `target_far` (class 1): Beyond sensor range, no reliable depth

See `docs/yolo-training-structure.md` for detailed bucket organization and filename conventions.

## Project Structure
```
src/svo_handler/
├── gui_app.py          # Frame Exporter
├── viewer_app.py       # Viewer/Annotator  
├── checker_app.py      # Annotation Checker
├── training_app.py     # Training GUI (Phase 3)
├── extraction.py       # Frame export worker
├── ingestion.py        # SVO2 reader
├── training_export.py  # Bucket management
├── training_config.py  # Training configuration dataclass
├── training_worker.py  # Background training thread
├── yolo_formatter.py   # Convert to YOLO format
├── options.py          # Export configuration
├── export_paths.py     # Path utilities
└── config.py           # Default settings

docs/
├── applications.md              # Detailed app guides
├── architecture.md              # System design
├── training-guide.md            # Comprehensive training feature guide
├── yolo-training-structure.md   # Training bucket organization
├── coding-guidelines.md         # Development conventions
└── fieldtest-learnings.md       # Field capture insights

tests/                  # Unit tests (in progress)
config/                 # Configuration templates
scripts/                # Automation helpers
```

## Documentation

### Setup Guides
- **[PC Setup Guide](docs/pc-setup-guide.md)** – **RECOMMENDED FOR TRAINING!** PyTorch + CUDA setup for desktop/laptop with NVIDIA GPU
- **[Jetson Setup Guide](docs/jetson-setup-guide.md)** – PyTorch installation for Jetson (extraction/annotation/inference only, training not feasible)

### Feature Guides
- **[Training Feature Guide](docs/training-guide.md)** – Comprehensive Training GUI guide with hardware recommendations
- **[Application Guides](docs/applications.md)** – Detailed documentation for all four apps
- **[YOLO Training Structure](docs/yolo-training-structure.md)** – 73-bucket organization and filename conventions

### Technical Documentation
- **[Architecture](docs/architecture.md)** – System design and implementation
- **[Coding Guidelines](docs/coding-guidelines.md)** – Development standards
- **[Field Test Learnings](docs/fieldtest-learnings.md)** – Jetson training analysis and workflow recommendations

## Technology Stack

- **Python 3.10+** with type hints
- **PySide6** – GUI framework
- **ZED SDK 4.0+** – SVO2 decoding and depth processing
- **OpenCV 4.12+** (contrib) – CSRT tracking, image processing
- **NumPy** – Depth array operations
- **Pillow** – Image manipulation and annotation overlay
- **Ultralytics** – YOLOv5/v8 training and inference
- **PyYAML** – YOLO configuration files

## Key Features

- **Source File Safety**: Viewer never modifies source files, export-only workflow
- **Smart Tracking**: CSRT tracker predicts bbox position across frames
- **Depth Integration**: 32-bit depth data with invalid value masking
- **Balanced Training**: 72-bucket structure enforces viewpoint distribution
- **Fast Annotation**: Enter key export + auto-advance, bbox persistence
- **Quality Assurance**: Checker app with zoom and hierarchical navigation
- **German UI**: Labels in German for field deployment

## Development

```bash
# Type checking
mypy --strict src/

# Run tests (when available)
pytest tests/

# Launch specific app
python -m svo_handler.gui_app       # Frame Exporter
python -m svo_handler.viewer_app    # Annotator
python -m svo_handler.checker_app   # Checker
python -m svo_handler.training_app  # Training GUI
```

## Configuration

- **Export root**: `/media/angelo/DRONE_DATA1/SVO2_Frame_Export/`
- **Training root**: `/media/angelo/DRONE_DATA1/YoloTrainingV1/`
- **State persistence**: `~/.svo_viewer_config`, `~/.svo_viewer_state`

Both roots are configurable via GUI settings.

## Field Deployment Notes

- Designed for Jetson Orin Nano (aarch64) + ZED2i camera
- Source recordings: HD720@60 FPS, LOSSLESS compression
- Typical file sizes: ~26 MB/s, ~10 GB per 4-minute flight
- Avoid FAT32 (4GB limit) – use exFAT/NTFS for storage

## License

[Your license here]

