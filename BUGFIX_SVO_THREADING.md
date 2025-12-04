# SVO2 Benchmark Threading Fix

## Issue

GUI froze for 10+ minutes after clicking "Start Processing" button. The application became unresponsive and had to be force-quit.

**Root Cause**: The `run_benchmark()` method was being called from the main GUI thread when the user clicked "Start Processing", blocking the entire UI while processing the SVO2 file.

---

## Solution

Redesigned the threading architecture to keep all heavy processing in the worker thread using a **signal-based continuation** pattern.

### Architecture Changes

#### Before (Broken)

```python
# In worker thread
def run(self):
    # Phase 1: Load SVO
    self.scenario.setup()
    self.loading_complete.emit()
    # Thread exits here!

# In main thread (BLOCKS UI!)
def _start_svo_processing(self):
    self.svo_worker.run_benchmark()  # ❌ Runs in main thread!
```

#### After (Fixed)

```python
# In worker thread
def run(self):
    # Phase 1: Load SVO
    self.scenario.setup()
    self.loading_complete.emit()
    
    # Phase 2: Wait for start signal
    while not self._start_benchmark:
        self.msleep(100)  # ✅ Thread sleeps, UI responsive
    
    # Phase 3: Run benchmark
    self._run_benchmark_internal()  # ✅ Still in worker thread!

# In main thread (DOES NOT BLOCK!)
def _start_svo_processing(self):
    self.svo_worker.start_processing.emit()  # ✅ Signal to worker!
```

### Key Changes

1. **Added Internal Flag** (`_start_benchmark`):
   - Worker thread waits in a loop after loading completes
   - Checks flag every 100ms (non-blocking)
   - Continues to benchmark phase when flag is set

2. **Added Internal Signal** (`start_processing`):
   - Connects to `_set_start_flag()` slot
   - Sets `_start_benchmark = True`
   - Signal/slot ensures thread-safe communication

3. **Renamed Method** (`run_benchmark()` → `_run_benchmark_internal()`):
   - Makes it clear this runs in worker thread
   - Called automatically after flag is set
   - GUI never calls it directly

---

## Depth Range Fix

Also fixed the depth validation range as requested:

### Changes

1. **Init Parameters**:
   ```python
   # Before
   init_params.depth_minimum_distance = 0.3  # Too close
   
   # After
   init_params.depth_minimum_distance = 1.0  # 1 meter minimum
   ```

2. **Depth Validation**:
   ```python
   # Before
   valid_depth = depth_roi[
       (depth_roi >= 0.3) &  # Too close
       (depth_roi <= 40.0)
   ]
   
   # After
   valid_depth = depth_roi[
       (depth_roi >= 1.0) &  # 1 meter minimum
       (depth_roi <= 40.0)   # 40 meters maximum
   ]
   ```

3. **Mean Depth Calculation**:
   - Takes ALL valid pixels in the bbox
   - Calculates mean (average) of all valid depth values
   - Ignores invalid pixels (NaN, Inf, <1.0m, >40m)
   - Returns -1.0 if no valid pixels found

---

## Threading Flow

### Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ User clicks "Initialize SVO2 File"                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ SVOScenarioWorker.start()                                   │
│   → Worker thread created and started                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ WORKER THREAD: run()                                        │
│                                                              │
│ Phase 1: Loading                                            │
│   → scenario.setup()                                        │
│   → Opens SVO2 file                                         │
│   → Initializes NEURAL_PLUS (30-60s)                       │
│   → Emits loading_progress signals                         │
│   → Emits loading_complete when done                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ WORKER THREAD: Wait Loop                                    │
│                                                              │
│   while not self._start_benchmark:                         │
│       self.msleep(100)  # Sleep 100ms, check flag          │
│                                                              │
│   → Thread is ALIVE but SLEEPING                           │
│   → GUI remains responsive                                 │
│   → "Start Processing" button enabled                      │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼ (User clicks "Start Processing")
┌─────────────────────────────────────────────────────────────┐
│ MAIN THREAD: _start_svo_processing()                        │
│   → Emits start_processing signal                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ WORKER THREAD: _set_start_flag() (slot)                    │
│   → self._start_benchmark = True                           │
│   → Wait loop exits                                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ WORKER THREAD: _run_benchmark_internal()                   │
│                                                              │
│   → Processes entire SVO2 file                             │
│   → Emits progress_updated every frame                     │
│   → Emits frame_processed (if saving)                      │
│   → Emits benchmark_complete when done                     │
│                                                              │
│   GUI stays responsive, updates in real-time!              │
└─────────────────────────────────────────────────────────────┘
```

---

## Code Changes Summary

### `jetson_benchmark_app.py`

1. **SVOScenarioWorker.__init__**:
   - Added `_start_benchmark` flag (default: False)
   - Added `start_processing` signal
   - Connected signal to `_set_start_flag()` slot

2. **SVOScenarioWorker.run()**:
   - After `loading_complete.emit()`, enters wait loop
   - Checks `_start_benchmark` flag every 100ms
   - Continues to `_run_benchmark_internal()` when flag set

3. **SVOScenarioWorker._set_start_flag()**:
   - New slot method
   - Sets `_start_benchmark = True`

4. **SVOScenarioWorker._run_benchmark_internal()**:
   - Renamed from `run_benchmark()`
   - Marked as internal (not called from main thread)
   - Same logic as before

5. **JetsonBenchmarkApp._start_svo_processing()**:
   - Changed from `self.svo_worker.run_benchmark()`
   - To `self.svo_worker.start_processing.emit()`

### `benchmark_scenarios.py`

1. **SVOPipelineScenario.setup()**:
   - Changed `depth_minimum_distance` from 0.3 to 1.0

2. **SVOPipelineScenario.run_frame()**:
   - Updated depth validation to use 1.0m minimum
   - Added comments explaining depth range

---

## Testing Checklist

- [x] App starts without errors
- [ ] SVO2 file loads (30-60s initialization)
- [ ] GUI remains responsive during loading
- [ ] "Start Processing" button enables after loading
- [ ] Processing starts when button clicked
- [ ] GUI remains responsive during processing
- [ ] FPS updates in real-time
- [ ] Preview updates (if save images enabled)
- [ ] Depth values in range 1.0-40.0m
- [ ] Mean depth calculated correctly
- [ ] Processing completes successfully
- [ ] Statistics saved to JSON

---

## Expected Performance

### Timing Breakdown (640 model)

| Component | Time (ms) | Notes |
|-----------|-----------|-------|
| Grab | ~5 | SVO frame retrieval |
| Inference | ~25 | YOLO TensorRT |
| Depth | ~8 | Depth in bboxes only |
| **Total** | **~38** | **→ 26 FPS** |

With image saving: ~40ms → **25 FPS**

### UI Responsiveness

- **Loading phase**: Progress dialog updates smoothly (0-100%)
- **Wait phase**: GUI fully responsive, can cancel if needed
- **Processing phase**: FPS counter updates every frame
- **Preview**: Updates every frame (if enabled)

---

## Thread Safety

### Mechanisms

1. **Signal/Slot**: Qt's thread-safe communication
2. **Flag Polling**: Worker checks `_start_benchmark` flag
3. **msleep()**: Non-blocking sleep in worker thread
4. **Cancellation**: `_cancelled` flag checked each iteration

### No Race Conditions

- `scenario` object created and used only in worker thread
- GUI only emits signals, never calls worker methods directly
- All heavy processing (grab/inference/depth) in worker thread
- UI updates via signals (thread-safe)

---

## What Was Wrong Before

The original code had this pattern:

```python
class SVOScenarioWorker:
    def run(self):
        # Load SVO
        self.scenario.setup()
        self.loading_complete.emit()
        # Thread exits here! ❌
    
    def run_benchmark(self):  # ❌ Meant to be called externally
        # Process SVO
        ...
```

When the GUI called `worker.run_benchmark()`, it ran in the **main thread**, freezing the UI for the entire duration of SVO processing (potentially thousands of frames).

---

## What's Right Now

The new code keeps everything in the worker thread:

```python
class SVOScenarioWorker:
    def run(self):
        # Load SVO
        self.scenario.setup()
        self.loading_complete.emit()
        
        # Wait for start signal
        while not self._start_benchmark:
            self.msleep(100)  # ✅ Non-blocking wait
        
        # Process SVO
        self._run_benchmark_internal()  # ✅ Still in worker thread!
```

The GUI only emits a signal, which sets a flag. The worker thread sees the flag and continues processing. No main thread blocking!

---

## Commit Message

```
Fix SVO2 benchmark threading and depth range

- Fixed GUI freeze issue by keeping all processing in worker thread
- Added signal-based continuation pattern for start button
- Changed from run_benchmark() call to start_processing signal
- Worker thread now waits in non-blocking loop after loading
- GUI remains responsive during entire benchmark process

- Updated depth range from 0.3-40m to 1.0-40m as requested
- Mean depth calculation averages all valid pixels in bbox
- Properly filters out invalid depth (NaN, Inf, out of range)

Tested: App starts without errors, ready for SVO2 testing
```

---

## Next Steps

1. Test with real SVO2 file from drone
2. Verify GUI stays responsive during processing
3. Check depth values are reasonable (1-40m range)
4. Validate FPS meets target (>10 Hz for flight controller)
5. Review saved images for quality

---

## Files Modified

- `src/svo_handler/jetson_benchmark_app.py` (SVOScenarioWorker class)
- `src/svo_handler/benchmark_scenarios.py` (SVOPipelineScenario depth range)
- `BUGFIX_SVO_THREADING.md` (this file)
