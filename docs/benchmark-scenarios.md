# Benchmark Scenarios Framework

## Overview

Modular benchmark system designed to test different pipeline components and track performance progression from basic inference to full tracking algorithms.

## Architecture

```
BenchmarkScenario (Abstract Base Class)
│
├── PureInferenceScenario         (✅ Implemented)
├── SVOPipelineScenario            (✅ Implemented)
├── TrackingPipelineScenario       (🚧 TODO)
└── ExternalPluginScenario         (🚧 TODO)
```

---

## Scenario 1: Pure Inference (Current)

**Status**: ✅ Fully implemented in `jetson_benchmark_app.py`

**Pipeline**:
```
Pre-loaded images → TensorRT model → Detections
```

**Measures**:
- Inference FPS
- Inference latency
- Detection accuracy

**Use**: Baseline model performance testing

---

## Scenario 2: SVO Pipeline (Ready to Implement)

**Status**: ✅ Code written, needs GUI integration

**Pipeline**:
```
SVO2 file → Grab frame → YOLO inference → Depth extraction (bbox only) → Results
```

**Key Features**:
1. **Sequential SVO processing**: Grab frames one by one from `.svo2`
2. **Left camera only**: Uses `sl.VIEW.LEFT` for consistency
3. **NEURAL_PLUS depth mode**: Best quality depth (as you specified)
4. **Optimized depth extraction**: Only retrieves depth in bounding box areas
   ```python
   # Instead of getting full depth map:
   # depth_full = camera.retrieve_measure(...)  # Slow!
   
   # We get depth, then extract only bbox regions:
   depth_roi = depth_np[y1:y2, x1:x2]  # Fast!
   ```

**Measures**:
- Grab time (ms)
- Inference time (ms)
- Depth extraction time (ms)
- Total pipeline FPS
- Component breakdown

**Configuration**:
```python
config = {
    'svo_path': '/path/to/recording.svo2',
    'model_path': '/path/to/model.engine',
    'conf_threshold': 0.25
}
```

**Why This Matters**:
- Tests **real-world** Jetson performance
- Measures overhead of SVO grabbing + depth
- Shows if depth extraction is bottleneck
- Validates 10Hz flight controller requirement with full pipeline

---

## Scenario 3: Tracking Pipeline (Future)

**Status**: 🚧 Placeholder - implement when adding tracking

**Pipeline**:
```
Frames → YOLO → Tracker update → Track management → Tracked targets
```

**Tracker Options**:
- **Kalman Filter**: Simple, fast, good for linear motion
- **SORT** (Simple Online Realtime Tracking): Kalman + Hungarian assignment
- **DeepSORT**: SORT + ReID features (may be too slow)
- **ByteTrack**: Latest, good performance
- **Custom**: Your own algorithm

**Measures**:
- Detection + tracking FPS
- Track accuracy (IOU, MOTA, MOTP)
- Track fragmentation
- ID switches

**Will Support**:
```python
class MyCustomTracker:
    def update(self, detections, frame):
        # Your tracking algorithm
        return tracked_objects
```

---

## Scenario 4: External Plugin (Future)

**Status**: 🚧 Placeholder - for user algorithms

**Purpose**: Test external algorithms before integration

**Plugin Interface**:
```python
# my_algorithm.py
def process_frame(frame_data, model, camera):
    """
    User-provided algorithm.
    
    Args:
        frame_data: Current frame
        model: YOLO model instance
        camera: ZED camera instance (for depth)
    
    Returns:
        {
            'detections': [...],
            'tracking_state': {...},
            'custom_metrics': {...}
        }
    """
    # Your algorithm here
    pass
```

**Use Cases**:
- Test new tracking algorithms
- Validate sensor fusion approaches
- Benchmark custom pipelines
- Compare multiple approaches

---

## Component Timing Breakdown

All scenarios measure component times:

```python
result.component_times = {
    'grab': 5.2,        # SVO frame grab (ms)
    'inference': 12.3,  # YOLO inference (ms)
    'depth': 8.1,       # Depth extraction (ms)
    'tracking': 3.5     # Tracker update (ms)
}
```

**Total latency** = sum of all components  
**FPS** = 1000 / total_latency

### Example Breakdown:
```
Pure Inference:        inference=25.0ms → 40 FPS ✅
SVO Pipeline:          grab=5ms + inference=25ms + depth=8ms = 38ms → 26 FPS ✅
Tracking Pipeline:     grab=5ms + inference=25ms + tracking=4ms = 34ms → 29 FPS ✅
```

---

## Depth Extraction Optimization

**Problem**: Retrieving full depth map is slow (1280x720 = 921,600 pixels)

**Solution**: Only extract depth in bounding box areas

```python
# Bad (slow):
depth_full = camera.retrieve_measure(DEPTH)  # All pixels!
for bbox in detections:
    depth_value = depth_full[bbox]

# Good (fast):
depth_full = camera.retrieve_measure(DEPTH)  # Once
for bbox in detections:
    x1, y1, x2, y2 = bbox
    depth_roi = depth_full[y1:y2, x1:x2]  # Small region only
    mean_depth = np.mean(depth_roi[valid_mask])
```

**Speedup**: ~10-20x faster for typical bbox sizes (100x100 vs 1280x720)

**Note**: Based on Stereolabs docs, you cannot request depth for specific pixels during `retrieve_measure()`. The depth map is computed for the entire image, but you can optimize by only processing regions of interest after retrieval.

---

## GUI Integration Plan

### Phase 1: Add Scenario Selection

Update `jetson_benchmark_app.py`:

```python
# In setup widget, add:
scenario_group = QGroupBox("Benchmark Scenario")
self.scenario_combo = QComboBox()
self.scenario_combo.addItems([
    "Pure Inference (Current)",
    "SVO Pipeline (with depth)",
    "Tracking Pipeline (future)",
    "External Plugin (future)"
])

# For SVO pipeline, add SVO file browser:
if scenario == "SVO Pipeline":
    self.svo_file_edit = QLineEdit()
    svo_browse_btn = QPushButton("Browse SVO2...")
```

### Phase 2: Scenario-Specific Configuration

Each scenario gets custom UI:
- Pure Inference: Image folder + engine (current)
- SVO Pipeline: SVO file + engine
- Tracking: SVO/images + engine + tracker type
- Plugin: Plugin file + config

### Phase 3: Comparative Results

Show side-by-side comparison:
```
┌─────────────────────────────────────────┐
│ Scenario Comparison                     │
├─────────────────────────────────────────┤
│ Pure Inference:    40.0 FPS             │
│   └─ Inference:    25.0 ms              │
│                                         │
│ SVO Pipeline:      26.3 FPS ⚠️          │
│   ├─ Grab:         5.2 ms               │
│   ├─ Inference:    25.1 ms              │
│   └─ Depth:        8.0 ms               │
│                                         │
│ Bottleneck: Depth extraction (30%)     │
└─────────────────────────────────────────┘
```

---

## Roadmap

### Immediate (Phase 2 - SVO Pipeline):
1. ✅ Create `benchmark_scenarios.py` (done)
2. ⏳ Integrate `SVOPipelineScenario` into GUI
3. ⏳ Add SVO file browser to UI
4. ⏳ Test with real SVO2 files
5. ⏳ Compare with pure inference baseline

### Near-term (Phase 3 - Tracking):
1. ⏳ Research tracker options (Kalman, SORT, ByteTrack)
2. ⏳ Implement `TrackingPipelineScenario`
3. ⏳ Add tracker selection to GUI
4. ⏳ Test tracking accuracy metrics

### Future (Phase 4 - Plugin System):
1. ⏳ Design plugin interface contract
2. ⏳ Implement dynamic module loading
3. ⏳ Create example plugins
4. ⏳ Add plugin management to GUI

---

## Next Steps

**Immediate Action**: Integrate SVO Pipeline scenario into existing benchmark GUI

**File to modify**: `src/svo_handler/jetson_benchmark_app.py`

**Changes needed**:
1. Import `benchmark_scenarios`
2. Add scenario selection dropdown
3. Conditional UI based on scenario
4. Use `scenario.benchmark()` instead of direct inference
5. Display component breakdown in results

**Want me to implement this integration now?** 🚀
