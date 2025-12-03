# Application Guides

Complete documentation for all three SVO2 Handler applications: Frame Exporter, Viewer/Annotator, and Annotation Checker.

---

## 1. Frame Exporter (`gui_app.py`)

### Purpose
Extract RGB frames and 32-bit depth data from ZED `.svo2` recordings for training dataset preparation.

### Launch
```bash
python -m svo_handler.gui_app
```

### Features

#### SVO2 File Selection
- **Browse button**: Select `.svo2` file from filesystem
- **Metadata display**: Shows resolution, FPS, total frames, duration after loading
- **Stream selection**: Choose Left or Right camera stream

#### FPS Downsampling
- **Source FPS aware**: Displays original capture FPS
- **Target FPS slider**: Set desired output FPS (1-60)
- **Frame skipping**: Downsamples by skipping frames (no resize/quality loss)
- **Keep-every calculation**: Automatically computes `keep_every = source_fps / target_fps`
- Example: 60 FPS source → 10 FPS target = keep every 6th frame

#### Depth Export (Optional)
- **Enable checkbox**: Toggle depth export on/off
- **Depth mode selection**: Choose processing quality
  - `NEURAL_PLUS` (default): Best quality, slowest
  - `NEURAL`: Good quality, balanced
  - `ULTRA`: High quality
  - `QUALITY`: Standard quality
  - `PERFORMANCE`: Fast, lower quality
  - `NONE`: Disable depth processing
- **Format**: 32-bit float NumPy arrays (`.npy`)
- **Invalid values**: NaN, Inf, <=0 marked as invalid

#### Output Configuration
- **Export root**: Default `/media/angelo/DRONE_DATA1/SVO2_Frame_Export/`
- **Directory structure**: `<source_parent>_RAW_<svo_stem>/`
- **Naming convention**: 
  - RGB: `frame_000000.jpg`, `frame_000001.jpg`, ...
  - Depth: `frame_000000.npy`, `frame_000001.npy`, ...
- **Manifest**: `manifest.json` with metadata (FPS, resolution, depth mode, frame count)

#### Progress Tracking
- **Progress bar**: Shows percentage and current/total frames
- **Frame preview**: Displays last exported frame
- **Status messages**: Real-time feedback on export process
- **Cancel button**: Abort export gracefully

#### Error Handling
- **File validation**: Checks if SVO2 file exists and is readable
- **Filesystem warnings**:
  - FAT32 detection (4GB file size limit warning)
  - Low disk space alert (<500MB)
- **Frame errors**: Log and continue on individual frame decode failures
- **German UI messages**: "Bereit", "Frames exportieren", etc.

### Workflow

1. **Load SVO2**: Click Browse, select file
2. **Review metadata**: Check FPS, resolution, frame count
3. **Configure export**:
   - Select camera stream (Left/Right)
   - Set target FPS
   - Enable depth export if needed
   - Choose depth mode
4. **Start export**: Click "Frames exportieren"
5. **Monitor progress**: Watch progress bar and preview
6. **Complete**: Status shows "Export abgeschlossen"

### Technical Notes
- **Threading**: Uses QThread worker to keep UI responsive
- **Memory management**: Processes frames sequentially to avoid memory overflow
- **Cancellation**: `_cancelled` flag checked each iteration for graceful stop
- **No resizing**: Exports full-resolution frames from source

---

## 2. Viewer/Annotator (`viewer_app.py`)

### Purpose
Annotate extracted frames with YOLO bounding boxes, classify targets by distance/direction/position, and export to organized training buckets.

### Launch
```bash
python -m svo_handler.viewer_app
```

### Features

#### File Management
- **Load folder**: Browse to folder with RGB + depth pairs
- **Auto-pairing**: Matches `frame_NNNNNN.jpg` with `frame_NNNNNN.npy`
- **Frame counter**: Shows `(position) frame_number / max_frame_number`
  - Example: `(1) 138 / 1000` = 1st frame in folder, actual frame 138 of 1000
  - Handles gaps from deleted frames correctly
- **Navigation**: ±1 frame, ±5 frames buttons
- **Keyboard shortcuts**:
  - **Enter/Return**: Export current annotation and advance to next frame

#### Image Display
- **Aspect ratio preservation**: Images scaled to fit while maintaining proportions
- **Dual view**: RGB on left, depth visualization on right
- **Zoom**: Mouse wheel on either view (max 10x zoom)
- **Pan**: Click and drag when zoomed in
- **Frame preview**: Shows current RGB + depth side-by-side

#### Depth Visualization
- **Range sliders**: Set min/max depth in meters
  - Slider 1: 1-10m (near range)
  - Slider 2: 10-40m (far range)
- **Colormap**: Valid depths mapped to Jet colormap (blue=near, red=far)
- **Invalid value handling**: NaN, Inf, <=0, out-of-range shown as black
- **Real-time update**: Changes apply immediately without clearing bbox

#### Bounding Box Annotation
- **Draw**: Click and drag on RGB or depth view to create bbox
- **Resize**: Drag edges or corners (8 resize handles)
- **Move**: Click center and drag to reposition
- **Visual feedback**: Cursor changes for resize/move operations
  - ↔️ Horizontal resize
  - ↕️ Vertical resize  
  - ↗️↖️ Diagonal resize
  - ✋ Move
- **Persistence**: Bbox stays at same pixel location across frame changes
- **Stats display**: Mean depth, min, max, std dev within bbox
- **Clear button**: Remove current bbox

#### CSRT Object Tracking
- **Enable/disable**: Checkbox to toggle tracking
- **Auto-initialization**: Starts after drawing first bbox
- **Prediction**: Estimates bbox position in next frame
- **Reset conditions**:
  - Manual bbox edit
  - Folder change
  - Tracking failure
- **Tracker options** (in code):
  - `TrackerCSRT_create()`: Best accuracy (current default)
  - `TrackerKCF_create()`: Balanced for real-time
  - `TrackerMOSSE_create()`: Fastest, lowest accuracy

#### YOLO Classification
**Two classes based on sensor range:**

- **target_close** (class 0):
  - Target within ZED sensor range (0-40m)
  - Has reliable depth data
  - Exported to 72-bucket structure

- **target_far** (class 1):
  - Target beyond sensor range (>40m)
  - No depth data or unreliable depth
  - Exported to simplified `0_far/` bucket

#### Export to Training Buckets

**For target_close:**
- **Direction** (8 cardinal directions):
  - `1_S` (South), `2_SE`, `3_E`, `4_NE`, `5_N`, `6_NW`, `7_W`, `8_SW`
- **Position** (3 vertical frame positions):
  - `Bot`: Bottom of frame
  - `Horizon`: Middle of frame
  - `Top`: Top of frame
- **Distance** (3 ranges based on depth stats):
  - `near`: <10m
  - `mid`: 10-30m
  - `far`: >30m or no valid depth

**Filename convention:**
- With depth: `frame_NNNNNN-<source_folder>-DIR_POS-depth-XX.XXm-std-X.XXm.jpg`
- Without depth (manual): `frame_NNNNNN-<source_folder>-DIR_POS-depth-XX.XXm-std-0.00m.jpg`
- target_far: `frame_NNNNNN-<source_folder>-far.jpg`

**Export process:**
1. User draws bbox
2. Selects class (target_close or target_far)
3. For target_close: selects direction, position, and distance
4. For target_far: no additional selection needed
5. Clicks "Exportieren" or presses Enter
6. Image copied to appropriate bucket
7. YOLO `.txt` label created (normalized coordinates)
8. Auto-advances to next frame

#### Duplicate Detection
- **Cross-bucket search**: Checks all buckets for existing annotation
- **Pattern matching**: `frame_NNNNNN-<source_folder>-*`
- **User prompt**: Shows all existing locations before overwriting
- **Prevents errors**: Can't have same frame in multiple buckets (e.g., S_Bot and S_Horizon)

#### Manual Depth Entry
**For target_close without depth data:**
- **Dialog prompt**: Asks for depth value
- **Bucket selection**: Choose from predefined or custom distance
- **Validation**: Ensures reasonable depth values
- **Filename**: Uses manually entered depth with `std-0.00m`

#### Source File Safety
- **Export-only workflow**: Original source files NEVER modified
- **Copy operation**: Images copied to training bucket
- **Original names preserved**: Source folder maintains original frame names
- **Safe experimentation**: Can delete/reorganize training data without affecting sources

#### Configuration & State
- **Training root**: Default `/media/angelo/DRONE_DATA1/YoloTrainingV1/`
- **Persistent settings**: `~/.svo_viewer_config` stores training root path
- **Resume capability**: `~/.svo_viewer_state` remembers last processed image
- **Auto-resume**: On startup, jumps to next frame after last annotation

### Workflow

1. **Load frames**: Browse to exported frame folder
2. **Review frame**: Check RGB + depth visualization
3. **Adjust depth range**: Set sliders for best depth visibility
4. **Draw bbox**: Click and drag around target
5. **Enable tracking** (optional): Check tracking box for auto-prediction
6. **Select class**: target_close or target_far
7. **For target_close**: Select direction, position, distance
8. **Export**: Press Enter or click "Exportieren"
9. **Auto-advance**: Viewer moves to next frame automatically
10. **Repeat**: Continue annotating remaining frames

### Known Issues
- **Window resize**: Images may briefly grow iteratively to final size (~1s delay)
- **Workaround**: Wait for rendering to stabilize after resize

---

## 3. Annotation Checker (`checker_app.py`)

### Purpose
Verify annotated images with hierarchical navigation, zoom capabilities, and bucket statistics for quality assurance.

### Launch
```bash
python -m svo_handler.checker_app
```

### Features

#### Training Root Selection
- **Browse button**: Select YOLO training root folder
- **One-time setup**: Opens folder once, navigates internal structure via GUI
- **Persistent path**: Remembers last used training root

#### View Modes
**Two navigation modes:**

1. **"Alle in Richtung" (All in Direction)**:
   - Loads all images from selected direction
   - Aggregates across all Position/Distance sub-buckets
   - Example: "1_S" loads from Bot/near, Bot/mid, Bot/far, Horizon/near, etc.
   - Dual counter: Shows global position + position within current bucket
   - Automatically flows across bucket boundaries

2. **"Spezifischer Bucket" (Specific Bucket)**:
   - Loads only from selected Position/Distance bucket
   - Example: "1_S/Bot/near" shows only near-range targets at bottom of frame
   - Single counter: Position within specific bucket
   - Focused inspection of particular viewpoint

#### Direction Selection
**9 directions with numeric prefixes:**
- `0_far`: target_far images (beyond sensor range)
- `1_S`: South
- `2_SE`: Southeast
- `3_E`: East
- `4_NE`: Northeast
- `5_N`: North
- `6_NW`: Northwest
- `7_W`: West
- `8_SW`: Southwest

#### Bucket Drill-Down (Specific Mode)
- **Position dropdown**: Bot, Horizon, Top
- **Distance dropdown**: near, mid, far
- **Disabled for 0_far**: No sub-buckets for target_far
- **Auto-disable in "All" mode**: Sub-selectors hidden when viewing entire direction

#### Bucket Statistics
- **Image counts**: Total images in selected direction
- **Sub-bucket breakdown**: Shows count per Position/Distance combination
- **Format**: "Gesamt: 45 Bilder (Bot/near: 12, Bot/mid: 8, Horizon/near: 15, ...)"
- **Real-time update**: Recalculates when direction changes

#### Image Display
- **Annotation overlay**: Bounding boxes drawn on images
- **Color coding**:
  - **Green**: target_close (class 0)
  - **Red**: target_far (class 1)
- **Thickness**: 3-pixel width for visibility
- **Text overlay**: Two-line label on each bbox
  - **Line 1**: Class name in color (larger font)
  - **Line 2**: Bucket path in white (smaller font)
  - **Example**:
    ```
    target_close  (green)
    1_S/Bot/near  (white)
    ```
- **Background**: Black rectangle behind text for readability
- **Smart positioning**: Above bbox, or below if near top edge

#### Zoom and Pan
- **Zoom control**: Mouse wheel (1-5x zoom)
- **Pan**: Click and drag when zoomed in
- **Cursor feedback**: Changes to indicate pan mode
- **Smooth interaction**: Real-time crop/scale rendering
- **Reset**: Zoom out fully with scroll

#### Navigation
- **Navigation buttons**: ±1 frame, ±5 frames
- **Arrow keys**:
  - **Left/Right**: Previous/Next frame (±1)
  - **Up/Down**: Jump ±5 frames
- **Index display**:
  - **All mode**: "Gesamt: X/Y | Bucket: A/B"
  - **Specific mode**: "X / Y"
- **Location label**: Shows current bucket path (e.g., "📁 1_S/Bot/near")

#### Status Information
- **Filename**: Current image name
- **Annotation count**: Number of bounding boxes in current image
- **Missing annotations**: Warning if no `.txt` label file found
- **Usage hints**: "Scroll zum Zoomen, Drag zum Verschieben"

### Workflow

1. **Open training root**: Browse to `/media/angelo/DRONE_DATA1/YoloTrainingV1/`
2. **Select direction**: Choose from dropdown (e.g., "1_S")
3. **Choose view mode**:
   - **All**: Review all images in direction for consistency
   - **Specific**: Focus on particular Position/Distance bucket
4. **Review statistics**: Check image counts per sub-bucket
5. **Navigate images**: Use arrow keys or buttons
6. **Zoom for detail**: Scroll to zoom, drag to pan
7. **Verify annotations**:
   - Check bbox placement
   - Verify class assignment (color)
   - Read bucket path overlay to confirm correct categorization
8. **Spot-check quality**:
   - Look for mislabeled images
   - Check bbox accuracy
   - Ensure balanced distribution across buckets

### Quality Checks

**What to look for:**
- ✅ **Correct class**: Green for close targets, red for far
- ✅ **Accurate bbox**: Fully contains target, minimal excess
- ✅ **Proper bucket**: Direction/position/distance matches actual image content
- ✅ **Consistent labeling**: Similar targets labeled similarly
- ❌ **Mislabeled direction**: S target in N bucket
- ❌ **Wrong position**: Horizon target in Bot bucket
- ❌ **Incorrect distance**: near target in far bucket
- ❌ **Missing annotations**: Images without `.txt` files

**Statistics review:**
- Check for severe imbalances (e.g., 100 images in Bot/near but 0 in Top/far)
- Aim for balanced distribution across buckets for better training
- Use statistics to guide where more annotations are needed

### Technical Notes
- **Font rendering**: Uses DejaVu Sans Mono for crisp text (fallback to default)
- **Font sizes**: 14pt for class name, 12pt for bucket path
- **Image loading**: PIL/Pillow for image + overlay, converted to Qt pixmap
- **Label parsing**: Reads YOLO `.txt` format (class_id, x_center, y_center, width, height)
- **Memory efficient**: Loads images on-demand, not entire dataset

---

## Common Workflows

### Complete Annotation Pipeline

```bash
# 1. Extract frames from SVO2
python -m svo_handler.gui_app
# Select SVO2, set FPS=10, enable depth export, choose NEURAL_PLUS
# Wait for completion

# 2. Annotate first flight
python -m svo_handler.viewer_app
# Load first exported folder
# Draw bbox, select target_close, choose 1_S/Bot/near
# Press Enter to export and advance
# Repeat for all frames in folder

# 3. Annotate remaining flights
# Load next folder, repeat annotation process
# Use tracking to speed up consecutive frames

# 4. Verify annotations
python -m svo_handler.checker_app
# Open training root
# Select direction "1_S", mode "All"
# Review statistics, spot-check images
# Repeat for each direction
```

### Quick Spot-Check

```bash
# Check specific viewpoint for quality
python -m svo_handler.checker_app
# Mode: "Specific"
# Direction: "1_S", Position: "Bot", Distance: "near"
# Zoom in on first image
# Arrow through all images in bucket
# Look for mislabeled or poor-quality annotations
```

### Balance Dataset

```bash
# Review distribution
python -m svo_handler.checker_app
# Mode: "All", Direction: "1_S"
# Note statistics: "Bot/near: 50, Bot/mid: 5, Bot/far: 2, ..."
# Identify buckets needing more annotations

# Annotate underrepresented buckets
python -m svo_handler.viewer_app
# Load folders, focus on targets matching underrepresented viewpoints
# Export to sparse buckets to balance distribution
```

---

## Tips & Best Practices

### Frame Exporter
- ✅ **Use NEURAL_PLUS** for best depth quality (if time permits)
- ✅ **Export depth** to enable distance-based bucketing
- ✅ **Target 10-15 FPS** balances dataset size and temporal coverage
- ⚠️ **Check disk space** before large exports (10GB+ typical)
- ⚠️ **Avoid FAT32** for large SVO2 files (use exFAT/NTFS)

### Viewer/Annotator
- ✅ **Use tracking** for consecutive frames with same target
- ✅ **Press Enter** for fast annotation (no mouse needed)
- ✅ **Adjust depth range** before drawing bbox for better target visibility
- ✅ **Zoom in** (10x) for small/distant targets
- ✅ **Enable tracking** after first bbox for faster workflow
- ⚠️ **Source files safe**: Experiment freely, originals never change
- ⚠️ **Check duplicates**: Heed warnings about existing annotations
- 💡 **Bbox persists**: Draw once, navigate to similar frames, fine-tune, export

### Annotation Checker
- ✅ **Start with "All" mode** to get overview of direction
- ✅ **Use statistics** to identify imbalanced buckets
- ✅ **Zoom frequently** to verify bbox accuracy
- ✅ **Spot-check random** samples, not just first images
- ✅ **Review each direction** before training
- 💡 **Bucket overlay** lets you spot mislabeled images instantly
- 💡 **Arrow keys** faster than clicking buttons

---

## Keyboard Shortcuts Reference

### Viewer/Annotator
- **Enter/Return**: Export current annotation and advance to next frame
- **Escape**: (planned) Cancel bbox drawing

### Annotation Checker
- **Left Arrow**: Previous frame (±1)
- **Right Arrow**: Next frame (±1)
- **Up Arrow**: Jump back 5 frames (±5)
- **Down Arrow**: Jump forward 5 frames (±5)

### All Applications
- **Mouse Wheel**: Zoom in/out (on image views)
- **Click + Drag**: Pan when zoomed in

---

## Troubleshooting

### Frame Exporter
- **"Cannot open SVO2"**: Check ZED SDK installation, verify file path
- **"Low disk space"**: Free up space or change export root
- **"FAT32 detected"**: Switch to exFAT/NTFS for large files
- **Slow export**: Normal for high FPS/NEURAL_PLUS mode (GPU-intensive)

### Viewer/Annotator
- **"No depth file found"**: Re-export with depth enabled
- **Bbox disappears**: Known issue, check "known issues" section
- **Tracking fails**: Disable tracking, draw bbox manually
- **Can't export**: Check training root path exists and is writable
- **Duplicate warning**: Frame already in bucket, choose replace or cancel

### Annotation Checker
- **No images load**: Verify training root path, check folder structure
- **Stats show 0**: No images in selected direction/bucket
- **Zoom not working**: Click on image first to focus
- **Pan jumpy**: Zoom in more (pan only works when zoomed >1x)

---

## German UI Labels Reference

### Frame Exporter
- "Bereit" = Ready
- "Frames exportieren" = Export frames
- "Abbrechen" = Cancel
- "Export abgeschlossen" = Export completed

### Viewer/Annotator
- "Ordner laden" = Load folder
- "Exportieren" = Export
- "BBox löschen" = Clear bbox
- "Tracking aktivieren" = Enable tracking

### Annotation Checker
- "Alle in Richtung" = All in direction
- "Spezifischer Bucket" = Specific bucket
- "Gesamt" = Total
- "Keine Bilder gefunden" = No images found
- "Keine Annotation!" = No annotation!
- "Scroll zum Zoomen" = Scroll to zoom
- "Drag zum Verschieben" = Drag to pan
