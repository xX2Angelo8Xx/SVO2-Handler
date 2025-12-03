# SVO2 Handler & Drone Tracking System - Development Roadmap

**Last Updated**: December 3, 2025

---

## Phase 1: Data Pipeline Enhancements

### 1.1 Viewer App: Benchmark Image Generation
**Priority**: High  
**Estimated Complexity**: Medium

#### Features
- **New Button**: "Create Benchmark Images"
- **Functionality**:
  - Search through entire YOLO training folder structure (all 73 buckets)
  - Identify all frames that have NOT been annotated (no corresponding `.txt` file)
  - Copy unannotated frames to `benchmark/` folder in YOLO training root
  - Preserve source folder information in filename for traceability

#### Implementation Details
- **Benchmark Folder Structure**:
  ```
  yolo_training_root/
  ├── 0_far/
  ├── 1_S/
  ├── ...
  ├── benchmark/          # Auto-created if missing
  │   └── frame_NNNNNN-<source>-unannotated.jpg
  └── negative_samples/   # New folder for training negatives
      └── frame_NNNNNN-<source>-negative.jpg
  ```

- **Initialization Logic**:
  - Check for `benchmark/` folder during YOLO training folder init
  - If missing (legacy folders), create it automatically
  - Same for `negative_samples/` folder

- **Negative Sample Classification**:
  - Add new option to class dropdown: "Negative Sample (No Object)"
  - When selected, copy frame to `negative_samples/` folder
  - No `.txt` annotation file created (indicates no objects present)
  - Use case: Frames with no target visible (clouds, ground, etc.)

#### Technical Considerations
- Use `Path.rglob("*.jpg")` to find all images
- Check for corresponding `.txt` files to determine annotation status
- Progress dialog for long-running operation (could be thousands of frames)
- Duplicate detection: Don't re-copy already benchmarked images

---

## Phase 2: Annotation Workflow Improvements

### 2.1 Checker App: In-Place Reclassification
**Priority**: Medium  
**Estimated Complexity**: Medium

#### Features
- **Edit Current Image**: Button or context menu option
- **Reclassification Workflow**:
  1. View image with current bbox and annotation
  2. Select "Edit/Move to Different Bucket"
  3. Choose new direction, position, distance, or class (close/far)
  4. Confirm → Image moved to new bucket, `.txt` updated accordingly
  5. Auto-advance to next image in current view

#### Implementation Details
- **UI Design**:
  - "Edit Annotation" button in checker toolbar
  - Modal dialog showing current classification
  - Dropdowns for: Direction (8), Position (3), Distance (3), Class (2)
  - Preview of new filename before confirmation

- **Backend Logic**:
  - Parse current filename to extract classification
  - Move file from current bucket to new bucket (shutil.move)
  - Update `.txt` annotation if class changes (target_close ↔ target_far)
  - Refresh current bucket view after move
  - Add undo functionality (optional, nice-to-have)

#### Technical Considerations
- Handle edge cases: Moving from `0_far` to positional buckets (verify depth exists)
- Update statistics after move
- Log all moves for audit trail
- Prevent accidental overwrites (check destination bucket first)

---

## Phase 3: New Application - YOLO Training GUI

### 3.1 YOLO Model Training Interface
**Priority**: High  
**Estimated Complexity**: High  
**Language**: Python (PySide6) initially, evaluate C++ later if needed

#### Core Features

**1. Training Data Preparation**
- Select YOLO training folder (73-bucket structure)
- Auto-format and copy images to YOLO-compatible structure
- Generate `train.txt`, `val.txt`, `test.txt` splits (configurable ratios)
- Create `data.yaml` with class definitions and paths
- Handle negative samples (include in training as background class)
- Optional: Data augmentation settings (flip, rotate, brightness, etc.)

**2. Model Configuration**
- **Model Selection Dropdown**:
  - YOLOv5 (n, s, m, l, x variants)
  - YOLOv8 (n, s, m, l, x variants)
  - YOLOv9 (if available)
  - Custom pretrained weights option
  
- **Training Parameters**:
  - Image size (default: 640x640, options: 416, 512, 640, 1280)
  - Batch size (auto-detect based on GPU memory, allow override)
  - Epochs (default: 100)
  - Learning rate (default: 0.01, with scheduler options)
  - Optimizer (Adam, SGD, AdamW)
  - Augmentation presets (light, moderate, heavy)
  - Multi-GPU support toggle
  - Resume from checkpoint option

**3. Real-Time Training Dashboard**
- **Metrics Display**:
  - Loss curves (box, obj, cls) - live updating line charts
  - mAP@0.5 and mAP@0.5:0.95 progress
  - Precision/Recall curves
  - Current epoch, iteration, ETA
  - GPU utilization, memory usage, temperature
  - Images/second throughput

- **Visualization**:
  - Sample predictions on validation set (updated each epoch)
  - Confusion matrix (updated periodically)
  - Grid of recent training batch images with predictions

- **Controls**:
  - Pause/Resume training
  - Early stopping (manual or automatic on plateau)
  - Save current checkpoint
  - Export best weights

**4. Training Output Management**
- Save training runs with descriptive names
- Export formats: PyTorch (.pt), ONNX, TensorRT, CoreML
- Generate training report (PDF/HTML) with all metrics
- Compare multiple training runs side-by-side

#### Implementation Architecture
```
src/svo_handler/
├── training_app.py          # Main GUI application
├── training_worker.py       # QThread for training loop
├── training_config.py       # Dataclass for training parameters
├── yolo_formatter.py        # Convert 73-bucket → YOLO format
└── training_monitor.py      # Parse training logs, emit signals
```

#### Technical Considerations
- Use `ultralytics` Python package for YOLOv8, or `yolov5` package
- Training runs in separate QThread to avoid blocking UI
- Parse training output (stdout) to extract metrics
- TensorBoard integration for advanced visualization (optional)
- Support for remote training (SSH to Jetson, monitor locally)
- **Performance**: Python sufficient for GUI + training orchestration; actual YOLO training uses optimized C++/CUDA backends

---

## Phase 4: New Application - Benchmark Testing Suite

### 4.1 YOLO Model Benchmarking
**Priority**: Medium  
**Estimated Complexity**: High  
**Language**: Python initially, C++ for tracker algorithms if performance-critical

#### Features

**1. YOLO Model Benchmarks**
- **Speed Testing**:
  - Inference time per frame (mean, std, min, max, P95, P99)
  - FPS calculations at various resolutions
  - Batch size impact analysis
  - Test on: CPU, GPU, TensorRT, ONNX runtime
  - Cold start vs. warm inference timing

- **Accuracy Testing**:
  - Load ground truth annotations from benchmark folder
  - Calculate mAP@0.5, mAP@0.5:0.95
  - Per-class precision/recall
  - IoU distribution
  - False positive/negative rates by distance category (close/far)
  - Confusion matrix

- **Resource Usage**:
  - GPU memory consumption
  - CPU/GPU utilization
  - Power consumption (if available on Jetson)
  - Thermal behavior under sustained load

**2. Mathematical Tracker Benchmarks**
- **Supported Trackers**:
  - CSRT (current implementation)
  - KCF (Kernelized Correlation Filters)
  - MOSSE (Minimum Output Sum of Squared Error)
  - Custom Kalman filter implementations
  - Optical flow-based trackers

- **Metrics**:
  - Tracking accuracy (IoU with ground truth over time)
  - Drift rate (pixels/frame when target stationary)
  - Re-acquisition latency after occlusion
  - Failure rate (when tracker diverges beyond threshold)
  - Tracking speed (FPS)

**3. Combined YOLO + Tracker Benchmarks**
- **Workflow**:
  1. YOLO detects target (every N frames, configurable)
  2. Tracker takes over between YOLO detections
  3. Confidence-based handoff logic
  4. Re-detection trigger on low confidence or tracker failure

- **Metrics**:
  - End-to-end tracking accuracy
  - YOLO detection frequency vs. accuracy trade-off
  - Tracker confidence correlation with accuracy
  - System throughput (combined FPS)
  - Failure recovery time

#### Implementation Details
- **Test Data**:
  - Use benchmark folder images
  - Generate synthetic sequences (moving target, occlusions)
  - Record real drone flight test sequences

- **Output Reports**:
  - Per-model comparison tables
  - Interactive plots (Plotly/Matplotlib)
  - Export to CSV, JSON, or PDF
  - Shareable HTML dashboard

#### Technical Considerations
- **Performance-Critical Code**: 
  - Tracker implementations may benefit from C++ (OpenCV native)
  - Kalman filter: C++ via Eigen library for speed
  - Python sufficient for orchestration and UI
- Parallel benchmark execution (test multiple models/configs)
- Reproducible results (fixed random seeds, environment capture)

---

## Phase 5: Main Tracking Algorithm (Jetson Deployment)

### 5.1 State Machine-Based Target Tracking
**Priority**: Highest (Core Mission Logic)  
**Estimated Complexity**: Very High  
**Language**: **C++** (performance-critical, real-time requirements)

#### System Architecture

**State Machine States**:

1. **SEARCH**: No target detected
   - Rotate/scan pattern
   - YOLO running continuously (max FPS possible)
   - Transition: Target detected → APPROACH_FAR

2. **APPROACH_FAR**: Target detected beyond sensor range (>40m)
   - No depth data available (class: `target_far`)
   - Direct straight-line flight toward last known position
   - YOLO detection every 5-10 frames
   - Transition: Target within sensor range → APPROACH_CLOSE

3. **APPROACH_CLOSE**: Target within sensor range (0-40m)
   - Depth data available (class: `target_close`)
   - Switch to path-optimized tracking (initial: carrot-on-stick)
   - YOLO hands off to mathematical tracker
   - Transition: Tracker initialized → TRACK

4. **TRACK**: Mathematical tracker active
   - Tracker runs every frame (high FPS, low latency)
   - YOLO re-detection trigger:
     - Option A: Tracker confidence drops below threshold
     - Option B: Periodic re-initialization every N frames
     - Option C: Tracker reports failure
   - Calculate target position (x, y, z) from depth map
   - Send coordinates to flight controller @ 5-10 Hz
   - Transition: Tracker fails → APPROACH_CLOSE or SEARCH

#### Core Components

**1. YOLO Detection Module** (C++)
```cpp
class YoloDetector {
    // TensorRT-optimized inference
    std::vector<Detection> detect(cv::Mat frame);
    float getConfidence(Detection det);
    BBox getBBox(Detection det);
    TargetClass getClass(Detection det); // target_close or target_far
};
```

**2. Mathematical Tracker** (C++)
```cpp
class TargetTracker {
    // OpenCV tracker or custom Kalman
    bool init(cv::Mat frame, BBox bbox);
    bool update(cv::Mat frame, BBox& predicted_bbox, float& confidence);
    float getConfidence();
    void reset();
};
```

**3. Depth Processing Module** (C++)
```cpp
class DepthProcessor {
    // ZED SDK integration
    void openDepthMap(BBox roi); // Only open region around bbox
    cv::Mat filterBackground(cv::Mat depth, BBox roi); // Remove ground
    Point3D calculateTargetPosition(cv::Mat depth, BBox bbox);
    float getAverageDistance(cv::Mat depth, BBox bbox);
};
```

**4. UART Communication Module** (C++)
```cpp
class FlightControllerComm {
    void sendTargetCoordinates(float x, float y, float z);
    void sendAtRate(float hz); // 5-10 Hz target
    void sendNoTargetSignal();
};
```

**5. State Machine Controller** (C++)
```cpp
class TrackingStateMachine {
    State currentState;
    void update(); // Main loop - called every frame
    void transitionTo(State newState);
    void processSearch();
    void processApproachFar();
    void processApproachClose();
    void processTrack();
};
```

#### Performance Requirements

**Target**: 5-10 Hz coordinate output to flight controller

**Optimization Strategies**:
- **YOLO Inference**: TensorRT optimization, INT8 quantization
- **Tracker**: Run at full camera FPS (60 Hz possible), lightweight
- **Depth Processing**: 
  - Only open depth map ROI (not full frame)
  - Use GPU for filtering (CUDA kernel)
  - Downsample depth if needed for speed
- **Pipeline**: Asynchronous processing (detection in parallel with tracking)

**Hardware Target**: Jetson Orin Nano
- 8-core ARM CPU
- 1024-core NVIDIA Ampere GPU
- 8 GB RAM
- CUDA, cuDNN, TensorRT support

#### Implementation Plan

**Phase 5.1**: Core C++ Framework
- Set up CMake build system
- Integrate ZED SDK (C++ API)
- TensorRT YOLO inference pipeline
- Basic state machine structure

**Phase 5.2**: Detection & Tracking
- YOLO detection module with confidence thresholding
- Mathematical tracker integration (OpenCV CSRT or custom Kalman)
- Handoff logic between YOLO and tracker

**Phase 5.3**: Depth Processing
- ROI-based depth map extraction
- Background filtering algorithm (plane fitting, statistical outlier removal)
- 3D position calculation (x, y, z in camera frame)

**Phase 5.4**: Flight Controller Integration
- UART communication (MAVLink or custom protocol)
- Coordinate transformation (camera frame → body frame → NED frame)
- 5-10 Hz update loop with latency guarantees

**Phase 5.5**: State Machine Logic
- Implement all state transitions
- Add telemetry/logging for debugging
- Field testing and parameter tuning

---

## Technology Stack Summary

| Component | Language | Rationale |
|-----------|----------|-----------|
| Frame Exporter | Python | File I/O, ZED SDK wrapper sufficient |
| Viewer/Annotator | Python | Qt GUI, not performance-critical |
| Annotation Checker | Python | Qt GUI, low-frequency operations |
| YOLO Training GUI | Python | Training orchestration, dashboard |
| Benchmark Testing (orchestration) | Python | Flexibility, plotting, reports |
| Benchmark Testing (trackers) | C++ (optional) | If tracker speed critical for tests |
| Main Tracking Algorithm | **C++** | Real-time, low-latency, embedded target |
| Mathematical Trackers | C++ | OpenCV native, performance-critical |
| Depth Processing | C++ + CUDA | GPU acceleration essential |
| Flight Controller Comm | C++ | Low-latency serial communication |

---

## Development Priorities

### Immediate (Next Sprint)
1. ✅ Zoom/pan in viewer (COMPLETED)
2. ✅ Statistics button in checker (COMPLETED)
3. ✅ Export settings overlay (COMPLETED)
4. ✅ Annotation status indicator (COMPLETED)
5. **Viewer: Benchmark image generation** ← NEXT
6. **Viewer: Negative sample classification** ← NEXT

### Short-Term (1-2 Months)
7. Checker: In-place reclassification
8. YOLO Training GUI (prototype)
9. Begin C++ main tracking algorithm framework

### Mid-Term (3-6 Months)
10. YOLO Training GUI (full features + dashboard)
11. Benchmark testing suite (Python orchestration)
12. Main tracking algorithm (core detection + tracking)
13. Depth processing module

### Long-Term (6-12 Months)
14. Flight controller integration
15. Field testing on Jetson Orin Nano
16. Parameter optimization for 5-10 Hz performance
17. Advanced path planning (beyond carrot-on-stick)
18. Benchmark testing suite (C++ tracker implementations if needed)

---

## Notes & Considerations

### Path Planning Evolution
- **Phase 1**: Carrot-on-stick (direct pursuit)
- **Phase 2**: Predictive intercept (constant velocity assumption)
- **Phase 3**: Kalman filter state estimation
- **Phase 4**: Model predictive control (MPC) with constraints
- **Phase 5**: Learning-based planning (if data available)

### YOLO Training Best Practices
- Include negative samples to reduce false positives
- Balance dataset: Ensure all 73 buckets have similar sample counts
- Use benchmark images for validation set (never train on them)
- Test on real flight footage before deployment

### C++ vs. Python Decision Points
- **Use C++** if: Real-time constraints (<100ms latency), embedded deployment, high-frequency loops
- **Use Python** if: Rapid prototyping, GUI, data pipeline, non-real-time analysis
- **Hybrid approach**: Python for orchestration, C++ for hot paths (YOLO inference, tracking loops)

### Jetson Optimization Tips
- Use TensorRT for YOLO (2-5x speedup vs. PyTorch)
- Enable GPU for depth processing (CUDA kernels)
- Pin critical threads to specific CPU cores
- Use Zero-copy memory (CUDA + OpenCV interop)
- Profile with Nsight Systems to find bottlenecks

---

## Open Questions / Future Research

1. **Tracker Confidence Metric**: How to quantify tracker confidence robustly?
   - Template matching score?
   - Prediction error variance?
   - Feature point quality?

2. **Background Filtering**: Best algorithm for ground plane removal in depth maps?
   - RANSAC plane fitting?
   - Statistical outlier removal?
   - Learning-based segmentation?

3. **YOLO Re-detection Frequency**: Optimal N frames between detections?
   - Trade-off: Accuracy vs. computational cost
   - Adaptive based on tracker confidence?

4. **Coordinate Frame Transformations**: Camera → Body → NED
   - Need precise calibration data
   - Handle gimbal motion if camera is gimballed

5. **Occlusion Handling**: What if target goes behind obstacle?
   - Keep last known position?
   - Predictive trajectory extrapolation?
   - Search pattern resumption?

6. **Multi-Target Scenarios**: Track multiple targets or focus on one?
   - ID re-association after occlusion
   - Priority/threat assessment

---

**End of Roadmap**
