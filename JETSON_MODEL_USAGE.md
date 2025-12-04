# Using Trained Models on Jetson

**Date**: December 4, 2025  
**Models Location**: `/media/angelo/DRONE_DATA1/JetsonExport`

---

## Your Trained Models

You have two trained models:

### 1. Model 640 (Downscaled Training)
- **Path**: `svo_model_20251204_112709_640/`
- **Training**: run_001
- **Results**:
  - Overall mAP50: 85.7%
  - Target Close: 99.5% mAP50 (excellent!)
  - Target Far: 71.8% mAP50
- **Files**:
  - `models/best.pt` (6.0MB) - PyTorch weights
  - `models/best.onnx` (12.8MB) - ONNX export

### 2. Model 1280 (Full Resolution Training)
- **Path**: `svo_model_20251204_112724_1280/`
- **Training**: run_0016
- **Results**: (Same metrics - README export bug, but models ARE different)
- **Files**:
  - `models/best.pt` (6.1MB) - PyTorch weights
  - `models/best.onnx` - ONNX export

**Note**: README metrics are identical due to export bug, but model files are different (different timestamps, sizes). We'll fix the export later.

---

## Quick Start: Build TensorRT Engine

### Step 1: Navigate to Model Folder

```bash
cd /media/angelo/DRONE_DATA1/JetsonExport/svo_model_20251204_112709_640/
```

### Step 2: Build TensorRT Engine

```bash
python ~/Projects/SVO2-Handler/scripts/build_tensorrt_engine.py .
```

This will:
- Find `models/best.onnx`
- Build optimized TensorRT engine for Jetson
- Enable FP16 precision (faster)
- Use 4GB workspace (good balance)
- Save as `models/best.engine`
- **Takes 5-15 minutes** (Jetson will appear unresponsive - this is normal)

**Expected output**:
```
======================================================================
TensorRT Engine Builder
======================================================================
ONNX Model: /media/angelo/.../models/best.onnx
Output: /media/angelo/.../models/best.engine
FP16: True
Workspace: 4GB
======================================================================

✓ TensorRT version: 8.6.x
✓ Running on Jetson: JetPack 6.0

🔨 Building TensorRT engine...
   This may take 5-15 minutes depending on model size
   The Jetson may appear unresponsive - this is normal

[... building ...]

======================================================================
✓ TensorRT engine built successfully in 487.3s
✓ Engine file: /media/angelo/.../models/best.engine
✓ Size: 13.5 MB
======================================================================
```

### Step 3: Test Inference

```bash
cd scripts
python ~/Projects/SVO2-Handler/scripts/test_inference.py ../models/best.engine ../test_images/
```

This will:
- Load TensorRT engine
- Run inference on all test images
- Print detection results
- Save annotated images (with bboxes drawn)

**Expected output**:
```
Loading model: ../models/best.engine
✓ Model loaded (TensorRT)

Found 10 test image(s)

frame_000001.jpg:
  Inference time: 45.2ms (22.1 FPS)
  Detections: 1
    - target_close: 0.87
  Saved: frame_000001_detected.jpg

frame_000002.jpg:
  Inference time: 43.8ms (22.8 FPS)
  Detections: 0

[...]
```

---

## Benchmark Mode

Run comprehensive performance benchmarks:

```bash
python ~/Projects/SVO2-Handler/scripts/test_inference.py \
    ../models/best.engine \
    ../test_images/ \
    --benchmark \
    --iterations 100 \
    --warmup 10
```

**Output**:
```
======================================================================
Benchmark Mode
======================================================================
Test images: 10
Warmup: 10 iterations
Benchmark: 100 iterations

Warming up...
Running benchmark (100 iterations)...
  Progress: 10/100 (10%)
  Progress: 20/100 (20%)
  [...]

======================================================================
Benchmark Results
======================================================================
Iterations: 100
Mean time: 44.3ms
Std dev: 2.1ms
Min time: 41.2ms
Max time: 52.7ms
P50 (median): 43.9ms
P95: 47.8ms
P99: 50.3ms

Mean FPS: 22.6
Peak FPS (min time): 24.3
======================================================================
```

---

## Compare Model Formats

Test all three formats to see performance differences:

### PyTorch (.pt)
```bash
python ~/Projects/SVO2-Handler/scripts/test_inference.py \
    models/best.pt \
    test_images/ \
    --benchmark --iterations 100
```

**Expected**: ~5-10 FPS (slowest, most compatible)

### ONNX (.onnx)
```bash
python ~/Projects/SVO2-Handler/scripts/test_inference.py \
    models/best.onnx \
    test_images/ \
    --benchmark --iterations 100
```

**Expected**: ~10-15 FPS (moderate, portable)

### TensorRT (.engine)
```bash
python ~/Projects/SVO2-Handler/scripts/test_inference.py \
    models/best.engine \
    test_images/ \
    --benchmark --iterations 100
```

**Expected**: ~20-30 FPS (fastest, Jetson-optimized)

---

## Advanced TensorRT Build Options

### With Custom Workspace (if OOM)
```bash
python ~/Projects/SVO2-Handler/scripts/build_tensorrt_engine.py . --workspace 2
```

### Without FP16 (more accurate, slower)
```bash
python ~/Projects/SVO2-Handler/scripts/build_tensorrt_engine.py . --no-fp16
```

### From Specific ONNX File
```bash
python ~/Projects/SVO2-Handler/scripts/build_tensorrt_engine.py \
    --onnx-path models/best.onnx \
    --output models/best_fp32.engine \
    --no-fp16
```

### Verbose Build Log
```bash
python ~/Projects/SVO2-Handler/scripts/build_tensorrt_engine.py . --verbose
```

---

## Benchmark GUI (Coming Soon)

Launch the benchmark application:

```bash
cd ~/Projects/SVO2-Handler
python -m svo_handler.benchmark_app
```

**Current Status**: UI placeholder created, execution not yet implemented.

**Planned Features**:
- Load PyTorch, ONNX, or TensorRT models
- Select test dataset folder
- Configure benchmark parameters
- Run comprehensive benchmarks:
  * Speed & latency distribution
  * Accuracy metrics (mAP, precision, recall)
  * Resource usage (GPU memory, CPU)
- Export results to CSV/JSON
- Compare multiple models side-by-side

---

## Performance Expectations

Based on YOLOv8n on Jetson Orin Nano:

| Format | Resolution | FPS | Latency | Use Case |
|--------|-----------|-----|---------|----------|
| PyTorch FP32 | 640x640 | 5-8 | ~150ms | Development/debug |
| PyTorch FP32 | 1280x1280 | 2-3 | ~400ms | High accuracy testing |
| ONNX | 640x640 | 10-15 | ~80ms | Cross-platform |
| ONNX | 1280x1280 | 3-5 | ~250ms | Accuracy validation |
| **TensorRT FP16** | **640x640** | **20-30** | **~40ms** | **Production** ✅ |
| **TensorRT FP16** | **1280x1280** | **8-12** | **~100ms** | **High accuracy** ✅ |

**Recommendations**:
- **For 10Hz flight controller**: Use TensorRT FP16 @ 640x640 (20-30 FPS)
- **For accuracy**: Use TensorRT FP16 @ 1280x1280 (8-12 FPS, still above 10Hz)
- **For close targets only**: 640x640 sufficient
- **For far targets**: 1280x1280 recommended (better small object detection)

---

## Troubleshooting

### TensorRT Build Fails with OOM
```bash
# Reduce workspace
python build_tensorrt_engine.py . --workspace 2

# Or reboot and try again
sudo reboot
```

### Inference Returns No Detections
- Check confidence threshold: `--conf 0.1` (lower threshold)
- Verify image preprocessing (BGR vs RGB)
- Test with training images first (should detect)

### Low FPS
- Verify TensorRT engine is being used (not .pt)
- Check GPU usage: `tegrastats`
- Ensure power mode: `sudo nvpmodel -m 0`
- Enable jetson_clocks: `sudo jetson_clocks`

### Import Errors
```bash
# Install ultralytics if needed
pip install ultralytics

# Or use system-wide
pip3 install --user ultralytics
```

---

## Next Steps

1. **Build TensorRT engines** for both models (640 and 1280)
2. **Run benchmarks** on both to compare performance
3. **Test on real drone footage** (if available)
4. **Choose best model** for deployment:
   - 640 if FPS more important (close-range only)
   - 1280 if accuracy more important (far target detection)
5. **Integrate into flight controller** (next phase)

---

## Files Reference

```
JetsonExport/
├── svo_model_20251204_112709_640/
│   ├── models/
│   │   ├── best.pt          # PyTorch weights
│   │   ├── best.onnx        # ONNX export
│   │   └── best.engine      # TensorRT (build with script)
│   ├── scripts/
│   │   ├── build_tensorrt.sh
│   │   └── test_inference.py
│   ├── test_images/
│   └── README.md
│
└── svo_model_20251204_112724_1280/
    └── (same structure)
```

**SVO2-Handler Tools**:
- `scripts/build_tensorrt_engine.py` - Build TensorRT engines
- `scripts/test_inference.py` - Test and benchmark models
- `src/svo_handler/benchmark_app.py` - Benchmark GUI (coming soon)

---

**Last Updated**: December 4, 2025  
**Status**: TensorRT build and testing tools ready, benchmark GUI placeholder created
