# Jetson Benchmark Suite

Two new applications for TensorRT model building and comprehensive benchmarking on Jetson.

## Applications

### 1. TensorRT Builder (`tensorrt_builder_app.py`)

Simple GUI for converting exported PyTorch models to optimized TensorRT engines.

**Launch:**
```bash
python -m svo_handler.tensorrt_builder_app
```

**Workflow:**
1. Select exported model folder (contains `models/best.pt`)
2. Configure build options:
   - FP16 precision (recommended: ON)
   - Workspace size (default: 4GB)
3. Click "Build TensorRT Engine"
4. Wait 5-15 minutes for build to complete
5. Engine saved as `models/best.engine`

**Features:**
- Real-time build output streaming
- Automatic cuDNN compatibility handling
- Validates folder structure before build
- Progress indication during build

---

### 2. Jetson Benchmark & Validation (`jetson_benchmark_app.py`)

Comprehensive benchmarking tool with manual validation workflow.

**Launch:**
```bash
python -m svo_handler.jetson_benchmark_app
```

**Complete Workflow:**

#### Phase 1: Inference Run
1. Select TensorRT `.engine` file
2. Select test images folder (unseen images for validation)
3. Click "Run Inference on All Images"
4. App creates timestamped benchmark folder:
   ```
   ~/jetson_benchmarks/run_20251204_183045/
   ├── images/           # Copied test images
   ├── labels/           # Detection results (.txt files)
   ├── inference_stats.json
   └── (validation files created in Phase 2)
   ```
5. Inference completes, showing:
   - Total time
   - Mean FPS
   - Mean latency

#### Phase 2: Manual Validation
1. App switches to validation mode
2. View each image with detection overlays
3. For each image, mark as:
   - **✓ Correct**: Target detected correctly
   - **✗ Missed**: Target present but not detected
   - **⚠ False**: False positive detection
4. Navigate:
   - Previous/Next buttons
   - Validation status shown by box color:
     - 🟢 Green = Correct
     - 🟠 Orange = Missed
     - 🔴 Red = False
     - 🔵 Blue = Pending

#### Phase 3: Report Generation
1. Click "Finish Validation & Generate Report"
2. Reports created:
   ```
   validation_report.json     # Full detailed data
   validation_summary.txt     # Human-readable summary
   validations.json           # Per-image validation state
   ```

**Report Contents:**
```
VALIDATION RESULTS:
Total Images:         95
Correct Detections:   82 (86.3%)
Missed Detections:    10 (10.5%)
False Detections:     3 (3.2%)

INFERENCE PERFORMANCE:
Mean FPS:             39.8
Mean Latency:         25.1ms
Total Time:           2.4s
```

**Features:**
- Non-destructive: Copies images, never modifies originals
- Resume support: Validation state saved, can continue later
- Color-coded visualization
- Keyboard shortcuts (arrow keys for navigation)
- Comprehensive statistics
- JSON + text report formats

---

## Quick Start Example

### Build TensorRT Engine:
```bash
# Terminal 1: Build 640 model
python -m svo_handler.tensorrt_builder_app
# Select: /media/angelo/DRONE_DATA1/JetsonExport/svo_model_..._640/
# Enable FP16, click Build
# Wait ~7 minutes
```

### Run Benchmark:
```bash
# Terminal 2: Benchmark with unseen images
python -m svo_handler.jetson_benchmark_app
# Select engine: .../models/best.engine
# Select test folder: /path/to/unseen/images/
# Run Inference
# Manually validate results
# Generate report
```

---

## Performance Targets

| Model | Resolution | Mean FPS | P95 Latency | Target Use Case |
|-------|-----------|----------|-------------|----------------|
| 640   | 640×640   | 39.8     | 33.5ms      | ✅ **Production** (10Hz flight controller) |
| 1280  | 1280×1280 | ~10-15   | ~80ms       | High accuracy (optional) |

**Recommended:** Use 640 model for deployment (4x headroom above 10Hz requirement)

---

## File Formats

### Detection Files (`.txt`)
YOLO format with confidence:
```
class_id x_center y_center width height confidence
0 0.512345 0.623456 0.134567 0.089012 0.8542
1 0.712345 0.323456 0.084567 0.069012 0.7231
```

- **class_id**: 0=target_close, 1=target_far
- **Coordinates**: Normalized 0-1 (relative to image size)
- **Confidence**: Detection confidence score

### Validation Report JSON
```json
{
  "validation_summary": {
    "total_images": 95,
    "correct_detections": 82,
    "missed_detections": 10,
    "false_detections": 3,
    "accuracy_percent": 86.32
  },
  "inference_performance": {
    "mean_fps": 39.8,
    "mean_latency_ms": 25.1,
    ...
  },
  "detailed_results": [
    {
      "image_name": "frame_000123.jpg",
      "status": "correct",
      "notes": ""
    },
    ...
  ]
}
```

---

## Tips

### TensorRT Builder:
- ✅ Run ON the Jetson (not PC) for optimal hardware-specific optimization
- ✅ Use FP16 for 2x speed improvement with minimal accuracy loss
- ✅ 4GB workspace sufficient for YOLOv8n
- ⚠️ Build takes 5-15 minutes - be patient!
- ⚠️ Jetson may appear unresponsive during build (normal)

### Benchmark App:
- ✅ Use images Jetson has NEVER seen (from different captures)
- ✅ Include edge cases: far targets, occlusions, different lighting
- ✅ Validate in batches: do 20-30 images, take break, resume later
- ✅ Review statistics to identify failure patterns
- ⚠️ Missed detections → may need more training data for that scenario
- ⚠️ False positives → may need to increase confidence threshold

---

## Troubleshooting

### TensorRT Builder Issues:

**"Models directory not found"**
- Solution: Ensure you selected the TOP-LEVEL export folder (contains `models/` subdirectory)

**cuDNN errors during build**
- Solution: Script automatically disables cuDNN, uses CUDA fallback
- This is normal and expected on Jetson

**Out of memory during build**
- Solution: Close other applications, reduce workspace size to 2GB

### Benchmark Issues:

**"No images found"**
- Solution: Test folder must contain `.jpg` or `.png` files directly

**Inference very slow**
- Solution: Ensure you're using `.engine` file (not `.pt` or `.onnx`)
- PyTorch models hit cuDNN issues on Jetson

**Can't see detection boxes**
- Solution: Check if `.txt` files exist in `labels/` folder
- If empty, no detections found (adjust confidence threshold?)

---

## Next Steps

After benchmarking:
1. **Analyze results**: Review missed/false detections
2. **Identify patterns**: What scenarios cause failures?
3. **Improve dataset**: Add more training data for weak scenarios
4. **Retrain**: Run new training iteration on PC
5. **Re-benchmark**: Build new engine, validate improvements
6. **Deploy**: When accuracy acceptable, deploy to drone!

---

**Documentation:** See main README.md and docs/ folder for complete system documentation.
