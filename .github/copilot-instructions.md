# Copilot Instructions – SVO2 Handler

## Project Overview
Desktop toolchain for extracting, annotating, and verifying YOLO training data from ZED `.svo2` recordings (ZED2i camera, LOSSLESS mode). Three GUI apps: **Frame Exporter** (`gui_app.py`), **Viewer/Annotator** (`viewer_app.py`), and **Annotation Checker** (`checker_app.py`). Source SVO2 files from Jetson Orin Nano drone captures.

**Full documentation**: See `README.md`, `docs/applications.md`, `docs/architecture.md`, `docs/yolo-training-structure.md`

## Quick Architecture
```
src/svo_handler/
├── gui_app.py          # Frame Exporter (python -m svo_handler.gui_app)
├── viewer_app.py       # Viewer/Annotator (python -m svo_handler.viewer_app)
├── checker_app.py      # Annotation Checker (python -m svo_handler.checker_app)
├── extraction.py       # FrameExportWorker (QThread) – ZED grab loop
├── ingestion.py        # SvoIngestor – opens SVO, reads metadata
├── training_export.py  # Bucket structure with numeric prefixes
├── options.py          # FrameExportOptions dataclass
├── export_paths.py     # Derive output dirs, filesystem checks
└── config.py           # Centralized defaults
```

## Critical Patterns

### ZED SDK (pyzed 5.0)
```python
try:
    import pyzed.sl as sl
except ImportError:
    sl = None  # Allows import without SDK

# Snake_case API
camera.set_from_svo_file(path)
camera.retrieve_image(image, sl.VIEW.LEFT)
info = camera.get_camera_information()
```

### Frame Extraction (Frame Exporter)
1. Load metadata: `SvoIngestor.metadata()` → FPS, resolution, frame count
2. FPS downsample: `keep_every = source_fps / target_fps` (frame skipping, no resize)
3. Worker thread emits progress signals
4. Output: `frame_NNNNNN.jpg` + optional `frame_NNNNNN.npy` (float32 depth)

### YOLO Training Structure (Viewer/Annotator)
**73 Buckets**: 1 far + 8 directions × 3 positions × 3 distances

**Numeric Prefixes**:
**Numeric Prefixes**:
- `0_far`, `1_S`, `2_SE`, `3_E`, `4_NE`, `5_N`, `6_NW`, `7_W`, `8_SW`

**YOLO Classes**:
- `target_close` (0): Within sensor range (0-40m), has depth → 72 buckets
- `target_far` (1): Beyond range (>40m), no depth → `0_far/` only

**Filename Convention**:
```
# target_close with depth
frame_NNNNNN-<source_folder>-DIR_POS-depth-XX.XXm-std-X.XXm.jpg

# target_far
frame_NNNNNN-<source_folder>-far.jpg
```

### Export-Only Workflow (Viewer/Annotator)
**CRITICAL**: Source files NEVER modified. Always copy to training bucket.

```python
# ✅ Correct
shutil.copy2(source_image, bucket / new_filename)  # Copy, don't rename

# ❌ Wrong
source_image.rename(new_filename)  # Don't modify source!
```

### Duplicate Detection
Before export, check ALL buckets with `Path.rglob(f"{base}-{source_folder}-*")`. Prevents same frame in multiple buckets (e.g., S_Bot and S_Horizon).

### Invalid Depth Masking
```python
valid_mask = (
    ~np.isnan(depth) &
    ~np.isinf(depth) &
    (depth > 0) &
    (depth >= min_depth) &
    (depth <= max_depth)
)
depth_masked = np.where(valid_mask, depth, 0.0)  # Invalid → black
```

### Bbox Persistence
Pass `keep_selection=True` through navigation chain:
```python
def _on_depth_range_changed(self):
    self._show_pair(keep_selection=True)  # Don't clear bbox

def _navigate_to_index(self, index: int):
    self._show_pair(keep_selection=True)  # Bbox stays
```

### CSRT Tracking (Viewer/Annotator)
```python
import cv2

tracker = cv2.legacy.TrackerCSRT_create()  # Best accuracy
tracker.init(frame, bbox)
success, new_bbox = tracker.update(next_frame)
```

## UI/Threading (PySide6)
- **Never block UI**: Use `QThread` workers with signals/slots
- **Worker cancellation**: Check `_cancelled` flag each loop iteration
- **Aspect ratio**: Scale to fit container while preserving proportions
- **Zoom widgets**: Custom QLabel with wheelEvent (1-10x max), pan with drag

## Developer Commands
```bash
python -m svo_handler.gui_app       # Frame Exporter
python -m svo_handler.viewer_app    # Annotator
python -m svo_handler.checker_app   # Verification

pip install -r requirements.txt
# Note: pyzed wheel for aarch64 in repo; x86_64 needs SDK install
```

## Conventions
- **Type hints required** (Python 3.10+); run `mypy --strict`
- **Dataclasses** for config/state (`FrameExportOptions`, `SvoMetadata`)
- **Domain exceptions**: `OutputPathError` for path/permission issues
- **Recoverable errors**: Log and continue (e.g., `CORRUPTED_FRAME` in field)
- **Filesystem guards**: Warn FAT32 (4GB limit), low space (<500MB)

## Testing Notes
When adding tests:
- **Mock ZED SDK**: Patch `pyzed.sl` to return fake metadata/frames
- **Synthetic depth**: float32 arrays with NaN, <=0 for mask tests
- **FPS math**: Test `keep_every` (e.g., 60→10 FPS = keep every 6th)
- **Path derivation**: Test `derive_export_dir()` with various inputs
- **Viewer coords**: Test view rect → image coords, YOLO `.txt` format

## Viewer/Annotator Quick Reference
- **Source immutable**: Never modifies source files, export-only
- **Export workflow**: Draw bbox → select class → Enter (or "Exportieren")
- **Keyboard**: Enter = export + auto-advance
- **Zoom**: Mouse wheel (10x max), drag to pan
- **Frame counter**: `(position) frame_number / max_frame_number`
- **Tracking**: Checkbox enabled after bbox drawn, predicts next frame
- **Cursor feedback**: Resize handles show appropriate cursors (↔️ ↕️ ↗️)
- **Duplicates**: Cross-bucket check, shows all existing locations
- **State**: `~/.svo_viewer_config` (training root), `~/.svo_viewer_state` (last frame)

## Annotation Checker Quick Reference
- **Purpose**: Verify annotations with zoom and hierarchical navigation
- **Modes**: "All direction" (aggregate all buckets) vs. "Specific bucket"
- **Statistics**: Shows image counts per sub-bucket
- **Overlay**: Class name + bucket path drawn on each bbox
- **Colors**: Green = target_close, Red = target_far
- **Zoom**: Mouse wheel (5x max), drag to pan
- **Navigation**: Arrow keys (Left/Right ±1, Up/Down ±5)
- **Counters**: Dual display in "All" mode (global + bucket position)

## Critical Context
- **Source files**: Large (~26 MB/s for HD720@60, ~10GB per 4min)
- **Depth**: Raw float32 with NaN/Inf/<=0 as invalid – mask before stats
- **German UI**: "Frames exportieren", "Bereit", "Exportieren", etc.
- **Storage**: Avoid FAT32, use exFAT/NTFS/ext4

## Documentation Structure
- `README.md`: Project overview, quick start, three apps
- `docs/applications.md`: Detailed guides for all three apps
- `docs/architecture.md`: System design, data flow, patterns
- `docs/yolo-training-structure.md`: Bucket organization, filenames, classes
- `docs/coding-guidelines.md`: Development standards
- `docs/fieldtest-learnings.md`: Field capture insights

**For detailed information, always refer to the full documentation in `docs/`.**

