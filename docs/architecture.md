# Architecture Overview# Architecture Overview



Current implementation architecture for the SVO2 Handler toolchain: Frame Exporter, Viewer/Annotator, and Annotation Checker.## Scope

GUI-driven SVO2 extraction tool for ZED2i recordings. Users pick an `.svo2` file, choose left/right stream, set output FPS (with awareness of the original capture FPS), and optionally export raw 32-bit depth using a selected depth model. Outputs target dataset creation for training computer vision models. Upstream capture stack details (Jetson Orin Nano + ZED2i, LOSSLESS-only) and field lessons are summarized in `docs/fieldtest-learnings.md`.

---

## Assumptions

## System Overview- Python 3.10+ environment.

- ZED SDK installed locally (for `.svo2` decoding and depth access).

### Purpose- Local, desktop-first GUI (PySide6/Qt). Headless/CLI mode can be added later for automation.

Desktop toolchain for extracting, annotating, and verifying YOLO training data from ZED `.svo2` recordings captured by Jetson Orin Nano + ZED2i drone stack.- Outputs written to user-selected directories; no bundled sample binaries in the repo.



### Scope## Proposed modules

- **Input**: ZED `.svo2` recordings (LOSSLESS mode, HD720@60 FPS typical)- **UI (PySide6)**: Main window, file picker, stream selection (left/right), FPS slider (shows source FPS), depth model dropdown, progress reporting, and error surface. Emits intents to the application layer.

- **Processing**: Frame extraction → Manual annotation → Quality verification- **App/Controller**: Orchestrates user intents, validates options (e.g., target FPS <= source FPS), and coordinates extraction pipelines. Handles long-running tasks with worker threads to keep UI responsive.

- **Output**: YOLO-ready training dataset organized into 73 balanced buckets- **Ingestion**: Opens `.svo2`, reads metadata (resolution, original FPS, duration, available depth modes), and exposes frame iterators for RGB and depth.

- **Extraction Pipelines**: 

### Three-Application Architecture  - RGB extraction: choose stream, downsample via frame skipping, write images (configurable format/quality), optionally store frame index + timestamp manifests.

1. **Frame Exporter** (`gui_app.py`): Extract RGB + depth from SVO2  - Depth extraction: choose depth model, export raw 32-bit depth per frame, optional normalization/visualization, same FPS downsampling.

2. **Viewer/Annotator** (`viewer_app.py`): Draw bounding boxes, classify, export to buckets- **Storage/IO**: Encapsulates writing frames, manifests, and depth arrays to disk; enforces output folder structure and naming.

3. **Annotation Checker** (`checker_app.py`): Verify annotations with zoom and hierarchical navigation- **Config**: Centralized defaults (paths, image format, thread counts, depth model defaults) loaded from `config/` templates.

- **Logging/Telemetry**: Structured logs for runs (source path, chosen options, errors). Progress updates routed back to UI.

---- **Tests**: Unit tests for option validation, FPS downsampling math, manifest generation; integration tests with small stub `.svo2` clips or mocked ingestion.



## Technology Stack## Data flow

1) User selects `.svo2` in UI.  

### Core Dependencies2) Ingestion reads metadata (including source FPS) and surfaces it to UI.  

- **Python 3.10+**: Type hints, dataclasses, pattern matching3) User configures stream (L/R), target FPS, and optional depth model.  

- **PySide6 (Qt 6)**: Cross-platform GUI framework4) Controller validates and spins up extraction pipeline workers.  

- **ZED SDK 4.0+**: SVO2 decoding, depth processing5) Pipelines pull frames from ingestion, downsample (skip every `n`), and pass to IO for disk writes.  

- **OpenCV 4.12+** (contrib): CSRT tracking, image processing6) UI shows progress and completion summary (frames written, duration, any dropped frames/errors).

- **NumPy**: Depth array operations, statistical computations

- **Pillow (PIL)**: Image manipulation, annotation overlay## Configuration & outputs

- Default config templates live in `config/` (JSON/YAML; final format TBD).

### Platform- Suggested output layout when exporting:

- **Primary**: Jetson Orin Nano (aarch64)  - `export/session_name/rgb_left/` or `rgb_right/` for images.

- **Development**: x86_64 Linux (Ubuntu 22.04+)  - `export/session_name/depth_raw/` for 32-bit depth (e.g., `.npy` or `.bin`) plus optional `.png` preview.

- **GUI**: PySide6 (Qt 6) for native look and feel  - `export/session_name/manifest.json` with metadata (source FPS, target FPS, frame count, depth model, timestamps, source capture info).

- Warn when the output target is FAT32 or low on space (field tests showed corruption beyond ~4GB on FAT32; prefer NTFS/exFAT).

---

## Threading and performance

## Module Structure- Use worker threads/process pool for decoding vs. disk writes to keep UI responsive.

- Avoid unbounded queues; apply backpressure to prevent memory blow-ups on long clips.

```- Provide cancellation hooks in UI to abort extraction.

src/svo_handler/

├── gui_app.py          # Frame Exporter main window## Error handling

├── viewer_app.py       # Viewer/Annotator main window- Validate input (file exists, readable; target FPS > 0; target FPS <= source FPS).

├── checker_app.py      # Annotation Checker main window- Gracefully handle missing depth models or SDK errors with clear UI messages.

├── extraction.py       # Frame export worker (QThread)- Treat per-frame decode errors as recoverable where possible (log and continue), mirroring field tolerance for `CORRUPTED_FRAME`.

├── ingestion.py        # SVO2 reader, metadata extraction- Record recoverable errors in logs; halt on unrecoverable ingest failures.

├── training_export.py  # Bucket management, CSV logging

├── options.py          # FrameExportOptions dataclass## Next steps for implementation

├── export_paths.py     # Path derivation, validation- Define dependency set (`requirements.txt`) and bootstrap PySide6 + ZED SDK bindings.

└── config.py           # Default settings, constants- Implement ingestion metadata reader and stub extraction pipeline interfaces.

```- Wire basic GUI skeleton with mocked data for FPS slider and stream selection.

- Add test harness for option validation and FPS downsampling calculation (e.g., mapping source 60 FPS → target 10 FPS as `keep_every=6`).

### Module Responsibilities- Specify depth export format (float32 + header or .npy) and include model provenance in manifests.


#### `gui_app.py` – Frame Exporter
- **UI**: PySide6 main window with file picker, FPS slider, depth options
- **Orchestration**: Launches `FrameExportWorker` thread, handles progress signals
- **Validation**: Checks source FPS, validates target FPS <= source FPS, filesystem checks
- **Preview**: Displays last exported frame during processing

#### `viewer_app.py` – Viewer/Annotator
- **UI**: Dual-pane (RGB + depth), bbox drawing, dropdowns, navigation buttons
- **Annotation**: SelectableLabel widget for bbox interaction, resize/move handles
- **Tracking**: CSRT tracker integration for bbox prediction across frames
- **Export**: Copy image to bucket, write YOLO `.txt` label, CSV logging
- **State**: Persistent config (`~/.svo_viewer_config`), resume state (`~/.svo_viewer_state`)

#### `checker_app.py` – Annotation Checker
- **UI**: ZoomableLabel widget, mode selection, bucket dropdowns, statistics display
- **Navigation**: Hierarchical (all direction vs. specific bucket), arrow key shortcuts
- **Overlay**: Draws class name + bucket path on each bbox for verification
- **Statistics**: Real-time image counts per sub-bucket

#### `extraction.py` – Frame Export Worker
- **Threading**: QThread worker to prevent UI blocking
- **Grab loop**: Iterates SVO2 frames, applies keep-every logic, writes to disk
- **Depth**: Optional 32-bit depth export, invalid value handling (NaN, Inf, <=0)
- **Signals**: `progress`, `frame_saved`, `finished`, `error` for UI communication
- **Cancellation**: Checks `_cancelled` flag each iteration for graceful stop

#### `ingestion.py` – SVO2 Reader
- **ZED SDK Wrapper**: Opens SVO2, configures depth mode, retrieves frames
- **Metadata**: Extracts resolution, FPS, total frames, duration
- **API Compatibility**: pyzed 5.0 snake_case API (`set_from_svo_file`, `retrieve_image`)
- **Error Handling**: Graceful degradation if SDK unavailable (for testing/dev)

#### `training_export.py` – Bucket Management
- **Constants**: DIRECTION_PREFIXES, POSITIONS, DISTANCES
- **Path Construction**: Builds bucket paths with numeric prefixes
- **Directory Creation**: `ensure_bucket_structure()` creates on-demand
- **CSV Logging**: Appends annotation metadata to `annotations.csv`
- **Validation**: Checks write permissions, warns on duplicates

#### `options.py` – Export Configuration
- **Dataclass**: FrameExportOptions with type hints
- **Validation**: Ensures target_fps <= source_fps, positive frame counts
- **FPS Math**: `keep_every = source_fps / target_fps` calculation
- **Serialization**: JSON-friendly for manifest export

#### `export_paths.py` – Path Utilities
- **Derivation**: Constructs output dirs from SVO2 path
- **Pattern**: `<source_parent>_RAW_<svo_stem>/`
- **Validation**: Checks filesystem type (FAT32 warning), disk space (<500MB warning)
- **Exception**: Raises `OutputPathError` for permission/space issues

#### `config.py` – Default Settings
- **Export Root**: `/media/angelo/DRONE_DATA1/SVO2_Frame_Export/`
- **Training Root**: `/media/angelo/DRONE_DATA1/YoloTrainingV1/`
- **Depth Modes**: NEURAL_PLUS, NEURAL, ULTRA, QUALITY, PERFORMANCE, NONE
- **FPS Range**: 1-60 FPS, default 10
- **German Labels**: UI text constants

---

## Data Flow

### 1. Frame Extraction (gui_app.py → extraction.py → ingestion.py)
```
User selects .svo2
    ↓
gui_app reads metadata via ingestion.py
    ↓
User configures FPS, depth mode, stream
    ↓
gui_app validates options (target_fps <= source_fps)
    ↓
gui_app spawns FrameExportWorker (QThread)
    ↓
Worker opens SVO2 via ingestion.py
    ↓
Worker iterates frames:
  - Apply keep_every logic (frame skipping)
  - Retrieve RGB via ZED SDK
  - Optional: retrieve depth, mask invalid values
  - Write frame_NNNNNN.jpg (OpenCV)
  - Optional: write frame_NNNNNN.npy (NumPy)
  - Emit progress signal → UI updates
    ↓
Worker writes manifest.json
    ↓
Worker emits finished signal → UI shows completion
```

### 2. Annotation (viewer_app.py → training_export.py)
```
User loads exported folder
    ↓
viewer_app scans for .jpg + .npy pairs
    ↓
User navigates to frame
    ↓
viewer_app displays RGB + depth visualization
    ↓
User draws bbox on SelectableLabel
    ↓
Optional: enable CSRT tracking (predicts bbox in next frame)
    ↓
User selects class:
  - target_close: chooses direction, position, distance
  - target_far: no additional selection
    ↓
User clicks Export (or presses Enter)
    ↓
viewer_app checks for duplicates (Path.rglob across all buckets)
    ↓
If duplicate: prompt user (replace or cancel)
    ↓
training_export.py constructs bucket path with numeric prefix
    ↓
training_export.py ensures bucket exists (create if needed)
    ↓
Copy frame_NNNNNN.jpg → bucket with metadata filename
    ↓
Write YOLO .txt label (normalized bbox coordinates)
    ↓
Append to annotations.csv
    ↓
viewer_app auto-advances to next frame
```

### 3. Verification (checker_app.py)
```
User opens training root
    ↓
checker_app scans directory structure (9 directions, 73 buckets)
    ↓
User selects direction (e.g., "1_S")
    ↓
checker_app calculates statistics (image counts per sub-bucket)
    ↓
User selects mode:
  - All: load images from all Position/Distance in direction
  - Specific: load only selected bucket
    ↓
checker_app loads AnnotationPair list (image + label + bucket_path)
    ↓
User navigates with arrows or buttons
    ↓
checker_app displays image with overlays:
  - Draw bbox from .txt (YOLO coordinates → pixel)
  - Color: green (target_close), red (target_far)
  - Text: class name + bucket path on black background
    ↓
User zooms (mouse wheel) and pans (drag) for detailed inspection
    ↓
User repeats for all directions/buckets to verify quality
```

---

## Key Design Patterns

### 1. Export-Only Workflow
**Problem**: Renaming source files caused cumulative naming issues and lost original references.

**Solution**: Never modify source files; always copy to training bucket.

### 2. Invalid Depth Masking
**Problem**: ZED depth arrays contain NaN, Inf, and out-of-range values.

**Solution**: Mask invalid values before any processing.

### 3. Bbox Persistence
**Problem**: Bbox disappeared when adjusting depth sliders or navigating frames.

**Solution**: Pass `keep_selection=True` through navigation chain.

### 4. CSRT Tracking Integration
**Problem**: Annotating consecutive frames with same target is tedious.

**Solution**: OpenCV CSRT tracker predicts bbox position in next frame.

### 5. Duplicate Detection
**Problem**: Same frame could be exported to multiple buckets.

**Solution**: Cross-bucket search with Path.rglob before export.

---

## Configuration & State Management

### Viewer/Annotator Config Files

**`~/.svo_viewer_config`** (JSON):
```json
{
  "training_root": "/media/angelo/DRONE_DATA1/YoloTrainingV1"
}
```

**`~/.svo_viewer_state`** (JSON):
```json
{
  "last_folder": "/media/angelo/DRONE_DATA1/SVO2_Frame_Export/Flight001_RAW_recording1",
  "last_index": 123
}
```

---

## Performance Considerations

### Frame Exporter
- Sequential processing prevents memory overflow
- JPEG quality=95 balances size and visual quality
- NumPy binary write (`.npy`) very fast (~10ms per frame)

### Viewer/Annotator
- Lazy loading (only current frame)
- Depth caching
- CSRT update typically <20ms

### Annotation Checker
- On-demand image loading
- Pixmap caching for zoom
- Statistics cached per directory change

---

## Summary

The SVO2 Handler architecture prioritizes:
- **Reliability**: Export-only workflow, duplicate detection
- **Usability**: Fast annotation with tracking, keyboard shortcuts
- **Quality**: Verification tool with hierarchical navigation
- **Maintainability**: Clear module separation, type hints
- **Performance**: Threaded extraction, lazy loading

For detailed implementation patterns and code examples, see the source files. For application usage, see `docs/applications.md`. For YOLO structure details, see `docs/yolo-training-structure.md`.
