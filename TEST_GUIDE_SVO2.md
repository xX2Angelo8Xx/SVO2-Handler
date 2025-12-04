# Quick Test Guide - SVO2 Benchmark

## Fixed Issues ✅

1. **GUI Freeze** - Worker thread now properly waits for start signal
2. **Depth Range** - Updated to 1.0m - 40.0m as requested
3. **Mean Depth** - Averages all valid pixels in bbox area

---

## Testing Steps

### 1. Launch App

```bash
python -m svo_handler.jetson_benchmark_app
```

### 2. Select SVO2 Scenario

- **Dropdown**: Select "SVO2 Pipeline (with Depth)"
- UI should change to show SVO-specific options

### 3. Select Files

- **Engine**: Browse for `best.engine` (640 or 1280 model)
- **SVO2 File**: Browse for `.svo2` recording from drone

### 4. Configure Options (Optional)

- **☑ Save processed frames**: Check if you want to inspect images
- **☑ Show live preview**: Uncheck if you want faster processing

### 5. Initialize SVO2

- Click **"🔄 Initialize SVO2 File"**
- Progress dialog appears
- Watch for these messages:
  ```
  [0%] Initializing ZED camera...
  [10%] Opening SVO2 file...
  [30%] Loading NEURAL_PLUS depth (this takes 30-60s)...
  [45%] Initializing depth neural network...
  [60%] Initializing depth neural network...
  [75%] Initializing depth neural network...
  [80%] Loading YOLO model...
  [95%] Finalizing setup...
  [100%] Ready! SVO has XXXX frames.
  ```
- **Expected**: 30-60 seconds total
- **GUI**: Should remain responsive (can click things)

### 6. Start Processing

- Click **"▶ Start Processing"** (enabled after loading)
- Watch for:
  - **FPS counter** updating in real-time
  - **Frame counter** showing progress
  - **Preview window** (if enabled) showing annotated frames
- **Expected**: ~25 FPS for 640 model
- **GUI**: Should remain responsive throughout

### 7. Verify Output

After completion, check:

```bash
~/jetson_benchmarks/svo_run_YYYYMMDD_HHMMSS/
├── benchmark_stats.json
└── frames/  (if saving enabled)
    ├── frame_000000_raw.jpg
    ├── frame_000000_annotated.jpg
    └── ...
```

**Statistics JSON**:
```json
{
  "scenario": "SVO2 Pipeline",
  "total_frames": 3600,
  "mean_fps": 25.8,
  "mean_latency_ms": 38.7,
  "component_times_ms": {
    "grab": 5.2,
    "inference": 24.8,
    "depth": 7.9,
    "save": 1.8
  }
}
```

---

## Expected Behavior

### ✅ Good Signs

- Progress dialog updates smoothly during loading
- "Start Processing" button enables after loading
- FPS counter updates every frame
- Status bar shows "Frame X/Y | FPS: Z.Z"
- Preview updates (if enabled)
- GUI never freezes
- Can cancel at any time

### ❌ Bad Signs

- GUI becomes unresponsive
- FPS counter stuck at 0
- No progress updates
- Preview not updating
- Can't click anything

---

## Performance Targets

### 640 Model

| Metric | Target | Acceptable |
|--------|--------|------------|
| **Mean FPS** | >25 | >20 |
| **Grab** | <10ms | <15ms |
| **Inference** | <30ms | <40ms |
| **Depth** | <10ms | <15ms |
| **Total** | <50ms | <70ms |

### 1280 Model

| Metric | Target | Acceptable |
|--------|--------|------------|
| **Mean FPS** | >10 | >8 |
| **Grab** | <10ms | <15ms |
| **Inference** | <80ms | <100ms |
| **Depth** | <15ms | <20ms |
| **Total** | <110ms | <140ms |

---

## Depth Validation

Open saved annotated images and check:

1. **Valid Detections**:
   - Should show `Conf:0.XX Depth:Y.YYm`
   - Depth values between 1.0m and 40.0m
   - Green bboxes for target_close (class 0)

2. **Invalid Detections**:
   - Should show `Conf:0.XX No depth`
   - Happens when all pixels in bbox are invalid
   - Red bboxes for target_far (class 1)

3. **Mean Depth Accuracy**:
   - Should be reasonable for scene
   - Close objects: 5-15m
   - Medium objects: 15-30m
   - Far objects: 30-40m or "No depth"

---

## Troubleshooting

### GUI Still Freezes

**Check**:
```python
# In jetson_benchmark_app.py, line ~1125
def _start_svo_processing(self):
    ...
    # Should be:
    self.svo_worker.start_processing.emit()  # ✅
    
    # NOT:
    self.svo_worker.run_benchmark()  # ❌
```

### No Depth Values

**Check**:
- SVO2 file has depth data (not just RGB)
- NEURAL_PLUS initialized (check logs)
- Depth range 1.0-40.0m appropriate for scene

### Low FPS

**Expected**:
- 640 model: ~25 FPS
- 1280 model: ~10 FPS
- With save images: -2 to -3 FPS

**Check**:
- TensorRT engine matches resolution
- Not running other heavy processes
- Storage not bottlenecked (if saving)

### "No depth" on All Detections

**Possible causes**:
- All objects beyond 40m (use target_far class)
- All objects closer than 1m (rare in flight)
- Depth map quality issues (check NEURAL_PLUS init)

---

## Success Criteria

### Minimum Requirements

✅ GUI remains responsive throughout  
✅ Loading completes in 30-60s  
✅ Processing starts when button clicked  
✅ FPS updates in real-time  
✅ Mean FPS > 10 (for flight controller)  
✅ Depth values reasonable for scene  
✅ Statistics saved correctly  

### Ideal Performance

✅ Mean FPS > 25 (640 model)  
✅ Component times balanced  
✅ Depth values for most detections  
✅ Saved images show correct annotations  
✅ Preview updates smoothly  
✅ Can run multiple benchmarks  

---

## Next Test After Success

1. **Compare Scenarios**:
   - Run Pure Inference on same frames
   - Compare FPS (should be ~40 vs ~25)
   - Identify depth extraction overhead

2. **Test Different Models**:
   - Try 1280 model
   - Should get ~10 FPS
   - Better accuracy vs speed tradeoff

3. **Real Flight Test**:
   - Use actual drone SVO2 recording
   - Verify depth values match real distances
   - Check detection accuracy on real targets

---

## Quick Command Reference

```bash
# Launch app
python -m svo_handler.jetson_benchmark_app

# Check benchmark results
ls -lh ~/jetson_benchmarks/

# View statistics
cat ~/jetson_benchmarks/svo_run_*/benchmark_stats.json | jq

# View latest benchmark
cat ~/jetson_benchmarks/$(ls -t ~/jetson_benchmarks/ | head -1)/benchmark_stats.json

# Check saved frames
ls -1 ~/jetson_benchmarks/svo_run_*/frames/ | wc -l
```

---

## Report Back

After testing, please report:

1. **Loading Phase**:
   - Time taken (should be 30-60s)
   - GUI responsive? (Yes/No)

2. **Processing Phase**:
   - Mean FPS achieved
   - Component breakdown (grab/inference/depth)
   - GUI responsive? (Yes/No)

3. **Output Quality**:
   - Depth values reasonable? (Yes/No)
   - Sample depths from saved images
   - Any "No depth" annotations?

4. **Any Issues**:
   - Freezes, errors, unexpected behavior
   - Console output if errors occur

---

**Ready to test! 🚀**
