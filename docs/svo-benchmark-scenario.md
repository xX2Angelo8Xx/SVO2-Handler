# SVO2 Benchmark Scenario - Implementation Guide

## Overview

Successfully implemented the first advanced benchmark scenario: **SVO2 Pipeline with Depth Extraction**.

This scenario processes entire SVO2 files frame-by-frame, running YOLO inference and extracting depth data only in detection regions, with optional image saving and live preview.

---

## Implementation Details

### 1. **Scenario Architecture** (`benchmark_scenarios.py`)

#### SVOPipelineScenario Class

**Key Features**:
- Opens SVO2 files with NEURAL_PLUS depth mode (best quality)
- Handles lengthy initialization (30-60s for depth neural network)
- Processes entire SVO file sequentially
- Optimized depth extraction (only bbox regions)
- Optional image saving with YOLO annotations
- Component-level timing (grab, inference, depth, save)

**Setup Phase** (`setup()` method):
```python
# Initializes:
1. ZED camera with NEURAL_PLUS depth mode
2. Does test grabs to initialize depth neural network (slow!)
3. Loads YOLO TensorRT model
4. Creates output directories if saving images
5. Reports progress via callback (0-100%)

# Takes 30-60 seconds due to NEURAL_PLUS initialization
```

**Processing Phase** (`run_frame()` method):
```python
# For each frame:
1. Grab frame from SVO (left camera only)
2. Run YOLO inference
3. Extract depth ONLY in detected bbox areas (optimization!)
4. Save raw + annotated images (if enabled)
5. Send preview to GUI (if enabled)
6. Return detections + timings

# Returns None when SVO file ends
```

**Cleanup**:
- Properly closes ZED camera
- Releases YOLO model
- Thread-safe cancellation support

---

### 2. **GUI Integration** (`jetson_benchmark_app.py`)

#### New Components

**Scenario Selection** (Section 1):
- Dropdown: "Pure Inference (Images)" vs "SVO2 Pipeline (with Depth)"
- Dynamically changes UI based on selection

**Input Selection** (Section 3):
- Pure Inference: Browse for folder
- SVO2 Pipeline: Browse for .svo2 file
- Shows file info (size, frame count after loading)

**SVO2 Options** (Section 4, visible only in SVO mode):
- ☑ Save processed frames (raw + annotated)
- ☑ Show live preview (when saving enabled)
- Warning: Saving slows down processing

**Three-Button Workflow** (SVO2 mode):
1. **"Initialize SVO2 File"**: Starts loading (30-60s)
2. **"Start Processing"**: Enabled after loading complete
3. Progress dialog shows initialization status

**Live Preview Window**:
- Shows last processed frame with YOLO annotations
- Bboxes with confidence + depth values
- Updates in real-time during processing
- Hidden in Pure Inference mode

---

### 3. **Workflow**

#### User Workflow (SVO2 Scenario)

```
1. Select "SVO2 Pipeline (with Depth)" from dropdown
   ↓
2. Browse for TensorRT .engine file
   ↓
3. Browse for .svo2 file
   ↓
4. [Optional] Check "Save processed frames"
   ↓
5. Click "🔄 Initialize SVO2 File"
   → Progress dialog appears
   → "Loading NEURAL_PLUS depth (this takes 30-60s)..."
   → ZED initializes depth neural network
   → YOLO model loads
   → Progress: 0% → 100%
   ↓
6. Click "▶ Start Processing" (enabled after loading)
   → Processes entire SVO file
   → Shows live FPS and frame progress
   → [If saving] Shows preview of annotated frames
   → Component timings tracked (grab/inference/depth/save)
   ↓
7. Benchmark complete
   → Summary dialog with statistics
   → Component breakdown shows bottlenecks
   → Images saved to run folder (if enabled)
```

---

### 4. **Output Structure**

#### Benchmark Run Folder

```
~/jetson_benchmarks/svo_run_YYYYMMDD_HHMMSS/
├── benchmark_stats.json       # Complete statistics
└── frames/                     # If "Save images" enabled
    ├── frame_000000_raw.jpg           # Original frame
    ├── frame_000000_annotated.jpg     # With YOLO bboxes
    ├── frame_000001_raw.jpg
    ├── frame_000001_annotated.jpg
    └── ...
```

#### Statistics JSON

```json
{
  "scenario": "SVO2 Pipeline",
  "total_frames": 3600,
  "total_time_seconds": 145.3,
  "mean_fps": 24.8,
  "mean_latency_ms": 40.3,
  "component_times_ms": {
    "grab": 5.2,
    "inference": 25.1,
    "depth": 8.0,
    "save": 2.0
  },
  "total_detections": 2847,
  "frames_with_detections": 2401,
  "frames_empty": 1199,
  "avg_detections_per_frame": 0.79,
  "conf_threshold": 0.25,
  "engine_path": "/path/to/model.engine",
  "svo_path": "/path/to/recording.svo2",
  "images_saved": true
}
```

---

### 5. **Performance Characteristics**

#### Component Timing Breakdown

Based on expected performance:

| Component | Time (ms) | % of Total | Notes |
|-----------|-----------|------------|-------|
| **Grab** | ~5 | 12% | SVO frame retrieval |
| **Inference** | ~25 | 60% | YOLO TensorRT (640 model) |
| **Depth** | ~8 | 20% | Depth extraction in bboxes only |
| **Save** | ~2 | 5% | Writing JPEGs (if enabled) |
| **Total** | ~40 | 100% | → **25 FPS** |

**Without Save**: ~38ms → **26 FPS**  
**Pure Inference**: ~25ms → **40 FPS**

#### Bottleneck Analysis

The GUI shows which component is slowest:
- **Inference dominant**: Normal (YOLO is compute-heavy)
- **Depth > 30%**: Depth extraction taking too long
- **Grab > 20%**: SVO I/O bottleneck (slow storage?)
- **Save > 10%**: Disk write bottleneck

---

### 6. **Depth Extraction Optimization**

#### Key Optimization

**Problem**: Full depth map is 1280×720 = 921,600 pixels

**Solution**: Only extract depth in bbox regions

```python
# Instead of:
for bbox in detections:
    depth_value = full_depth_map[bbox]  # Processes all 921k pixels!

# We do:
for bbox in detections:
    depth_roi = full_depth_map[y1:y2, x1:x2]  # Only ~10k pixels per bbox
    mean_depth = np.mean(depth_roi[valid_mask])
```

**Speedup**: 10-20× faster for typical bbox sizes (100×100 vs 1280×720)

**Note**: ZED SDK computes full depth map internally, but we only process relevant regions.

---

### 7. **Image Annotations**

Saved annotated images include:

```
┌─────────────────────────────────┐
│  [Green bbox for target_close]  │
│  Conf:0.87 Depth:12.34m         │ ← Label with confidence + depth
│                                  │
│  [Red bbox for target_far]      │
│  Conf:0.92 No depth              │ ← No depth if invalid
└─────────────────────────────────┘
```

**Colors**:
- Green: Class 0 (target_close)
- Red: Class 1 (target_far)

**Label Format**:
- `Conf:X.XX Depth:Y.YYm` - Valid depth
- `Conf:X.XX No depth` - Invalid/missing depth

---

### 8. **Threading Architecture**

#### SVOScenarioWorker (QThread)

**Two Phases**:

1. **Loading Phase** (`run()` method):
   - Runs automatically when thread starts
   - Initializes ZED with NEURAL_PLUS (slow!)
   - Emits `loading_progress` signals
   - Emits `loading_complete` when done
   - Blocks thread but UI remains responsive

2. **Processing Phase** (`run_benchmark()` method):
   - Called manually after user clicks "Start Processing"
   - Processes all SVO frames
   - Emits `progress_updated` signals
   - Emits `frame_processed` for preview
   - Emits `benchmark_complete` when done

**Signals**:
```python
loading_progress(progress: int, message: str)
loading_complete()
loading_failed(error: str)
progress_updated(current: int, total: int, status: str, fps: float)
frame_processed(img_rgb: np.ndarray)
benchmark_complete(run_folder: str, time: float, stats: dict)
benchmark_failed(error: str)
```

---

### 9. **Error Handling**

#### Graceful Degradation

- **Corrupted frames**: Skipped, processing continues
- **End of SVO**: Returns None, ends gracefully
- **Invalid depth**: Marked as -1.0, bbox still saved
- **Cancellation**: Thread-safe, cleans up properly

#### User Feedback

- Progress dialog during 30-60s loading
- Real-time FPS display
- Frame counter (current/total)
- Component timing breakdown in output
- Detailed error messages with stack traces

---

### 10. **Comparison with Pure Inference**

| Feature | Pure Inference | SVO2 Pipeline |
|---------|----------------|---------------|
| **Input** | Image folder | .svo2 file |
| **Sampling** | Random selection | Sequential (all frames) |
| **Depth** | ❌ No | ✅ Yes (NEURAL_PLUS) |
| **FPS** | ~40 FPS | ~25 FPS |
| **Latency** | ~25 ms | ~40 ms |
| **Setup** | Instant | 30-60s loading |
| **Preview** | ❌ No | ✅ Optional |
| **Depth Data** | ❌ No | ✅ Per detection |
| **Component Timing** | Inference only | Grab/Inference/Depth/Save |

---

### 11. **Next Steps**

#### Testing Checklist

- [ ] Test with real SVO2 file from drone
- [ ] Verify NEURAL_PLUS initialization time
- [ ] Check depth extraction accuracy
- [ ] Validate saved images quality
- [ ] Test preview window performance
- [ ] Measure component timings
- [ ] Compare with Pure Inference baseline

#### Future Enhancements

- [ ] Add depth visualization (colormap overlay)
- [ ] Support frame skipping (downsample FPS)
- [ ] Add depth statistics to output
- [ ] Export depth maps as .npy files
- [ ] Add comparison view (SVO vs Pure Inference)

---

### 12. **Usage Example**

```bash
# Launch app
python -m svo_handler.jetson_benchmark_app

# In GUI:
1. Select "SVO2 Pipeline (with Depth)"
2. Browse → Select "best.engine"
3. Browse → Select "flight_recording.svo2"
4. Check "Save processed frames" (if you want images)
5. Click "🔄 Initialize SVO2 File"
   → Wait 30-60s (progress dialog)
6. Click "▶ Start Processing"
   → Watch live FPS and preview
7. Review summary dialog when complete

# Output:
~/jetson_benchmarks/svo_run_YYYYMMDD_HHMMSS/
  - benchmark_stats.json (detailed metrics)
  - frames/ (if saving enabled)
```

---

### 13. **Key Code Locations**

| Component | File | Lines |
|-----------|------|-------|
| **SVOPipelineScenario** | `benchmark_scenarios.py` | 232-500 |
| **SVOScenarioWorker** | `jetson_benchmark_app.py` | 193-355 |
| **GUI Scenario Selection** | `jetson_benchmark_app.py` | 794-911 |
| **SVO Loading Workflow** | `jetson_benchmark_app.py` | 1000-1080 |
| **Preview Display** | `jetson_benchmark_app.py` | 1133-1143 |

---

### 14. **Technical Notes**

#### NEURAL_PLUS Initialization

- Loads neural network weights (~50MB)
- Compiles CUDA kernels
- Pre-allocates GPU memory
- Requires 2-3 test grabs to fully initialize
- One-time cost per SVO file

#### Depth Valid Mask

```python
valid_depth = depth_roi[
    ~np.isnan(depth_roi) &      # Not NaN
    ~np.isinf(depth_roi) &      # Not Inf
    (depth_roi > 0) &           # Positive values
    (depth_roi >= 0.3) &        # Within min range
    (depth_roi <= 40.0)         # Within max range
]
```

#### Thread Safety

- Worker has `_cancelled` flag
- Checks before each frame
- Cleans up ZED camera properly
- No race conditions on scenario object

---

## Conclusion

You now have a complete SVO2 benchmark scenario that:

✅ Loads SVO2 files with NEURAL_PLUS depth  
✅ Shows loading progress (30-60s initialization)  
✅ User clicks "Start" after loading complete  
✅ Processes entire SVO file sequentially  
✅ Saves raw + annotated images (optional)  
✅ Shows live preview of processed frames  
✅ Tracks component-level timings  
✅ Identifies performance bottlenecks  
✅ Exports detailed statistics  

**Ready to test on real drone SVO2 files!** 🚀
