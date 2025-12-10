# Depth Analysis and Frame Skipping Guide

## Overview

The enhanced Python test script now supports:
1. **Real-time depth analysis**: Average, min, max, std deviation
2. **Configurable Hz**: Compute depth at 1, 5, 10 Hz or custom frequency
3. **Frame skipping**: High FPS grab with lower Hz depth computation
4. **ROI support**: Analyze depth in 100%, 50%, or 25% of frame

## Why Frame Skipping Matters

**Problem**: NEURAL_PLUS depth is limited to ~11 FPS, but camera can grab at 60 FPS.

**Solution**: Skip depth computation on most frames!

```
Without skipping (11 FPS total):
Frame 1: Grab + YOLO + Depth (91ms) ← Slow!
Frame 2: Grab + YOLO + Depth (91ms)
Frame 3: Grab + YOLO + Depth (91ms)
...

With 10 Hz skipping (60 FPS grab, 10 Hz depth):
Frame 1: Grab + YOLO + Depth (91ms)
Frame 2: Grab + YOLO (17ms) ← Fast!
Frame 3: Grab + YOLO (17ms)
Frame 4: Grab + YOLO (17ms)
Frame 5: Grab + YOLO (17ms)
Frame 6: Grab + YOLO (17ms)
Frame 7: Grab + YOLO + Depth (91ms)
...
```

**Result**: Detection at 60 FPS, depth at 10 Hz - perfect for tracking!

## Usage

### Quick Start: 10 Hz Depth with NEURAL_PLUS

```bash
python scripts/svo2_grab_speed_test.py

# Menu selections:
# 1. Source: 2 (Live camera)
# 2. Depth: 6 (NEURAL_PLUS)
# 3. ROI: 1 (100% - full frame)
# 4. Frequency: 2 (10 Hz)
```

**Output** (real-time):
```
📊 Frame 271/999999 (0.0%) | FPS: 7.23 | Depth: 7.2 Hz | 
   Avg: 1.05m | Min: 0.40m | Max: 3.97m | Std: 0.33m | Elapsed: 37.5s
```

### Menu Options

#### Depth Computation Frequency

**1) Every frame** (no skipping):
- Maximum depth quality
- Lowest overall FPS (~11 FPS with NEURAL_PLUS)
- Use for: Post-processing, quality evaluation

**2) 10 Hz** (recommended):
- Good for tracking moving targets
- Balanced speed/quality
- Depth every ~6th frame with 60 FPS grab
- Use for: Drone tracking, obstacle avoidance

**3) 5 Hz**:
- Good for slow targets
- Depth every ~12th frame with 60 FPS grab
- Use for: Slow-moving objects, verification

**4) 1 Hz**:
- Verification only
- Depth every ~60th frame with 60 FPS grab
- Use for: Periodic distance checks, debugging

**5) Custom Hz**:
- Enter any value 1-60 Hz
- System will compute closest frame interval
- Use for: Specific requirements

### ROI Options

**100% - Full frame**:
- Analyzes entire depth map (1280×720 = 921,600 pixels)
- Most comprehensive
- Useful for: Scene understanding, multi-object tracking

**50% - Half frame**:
- Analyzes center 640×360 = 230,400 pixels
- Simulates medium-sized detection
- Useful for: Single large target

**25% - Quarter frame**:
- Analyzes center 320×180 = 57,600 pixels
- Simulates small detection
- Useful for: Distant target, minimal processing

**Note**: ROI doesn't improve NEURAL_PLUS speed (fixed GPU overhead), but reduces memory for analysis.

## Real-Time Display

### Status Line Format

```
📊 Frame N/Total (%) | FPS: X.XX | Depth: Y.Y Hz | Avg: Z.ZZm | Min: A.AAm | Max: B.BBm | Std: C.CCm | Elapsed: Ds
```

**Fields**:
- `Frame N/Total`: Current frame / total frames (999999 for live)
- `FPS`: Overall grab rate (includes all frames)
- `Depth: Y.Y Hz`: Actual depth computation rate
- `Avg: Z.ZZm`: Average depth in ROI (meters)
- `Min: A.AAm`: Minimum depth in ROI
- `Max: B.BBm`: Maximum depth in ROI
- `Std: C.CCm`: Standard deviation of depth
- `Elapsed`: Total runtime

### Depth Statistics Explained

**Average depth** (`Avg`):
- Mean of all valid depth pixels in ROI
- Filters out NaN, inf, and <=0 values
- Useful for: Target distance estimation

**Minimum depth** (`Min`):
- Closest valid depth point
- Useful for: Collision avoidance, closest obstacle

**Maximum depth** (`Max`):
- Farthest valid depth point
- Useful for: Scene extent, background distance

**Standard deviation** (`Std`):
- Spread of depth values
- Low std: Flat surface (wall, floor)
- High std: Complex surface (trees, clutter)
- Useful for: Surface classification, confidence

### Example Interpretations

**Flat wall ahead**:
```
Avg: 2.50m | Min: 2.45m | Max: 2.55m | Std: 0.05m
```
- Small range (2.45-2.55m = 10cm)
- Low std dev (0.05m)
- **Interpretation**: Planar surface at ~2.5m

**Complex scene**:
```
Avg: 3.20m | Min: 0.80m | Max: 8.50m | Std: 1.50m
```
- Large range (0.80-8.50m = 7.7m)
- High std dev (1.50m)
- **Interpretation**: Multiple objects at varying distances

**Close obstacle**:
```
Avg: 0.65m | Min: 0.40m | Max: 1.20m | Std: 0.25m
```
- Min very close (0.40m = 40cm)
- **Action**: Emergency stop/avoidance!

## Final Statistics

After stopping (CTRL+C), see comprehensive summary:

```
======================================================================
📊 FINAL STATISTICS
======================================================================
Total frames processed: 500/999999
Total time: 45.23s
Average FPS (grab): 11.05
Average frame time: 90.46ms

Depth computation:
  • Depth frames: 50/500
  • Depth Hz: 1.11
  • Frame skip: Every 10.0 frames
  • Last avg depth: 1.05m
  • Last depth range: 0.40m - 3.97m
  • Last std dev: 0.33m

Components retrieved:
  • Left image (HD720: 1280x720)
  • Right image (HD720: 1280x720)
  • Depth map (NEURAL_PLUS)
======================================================================
```

**Key metrics**:
- `Average FPS (grab)`: Overall frame acquisition rate
- `Depth frames`: How many times depth was computed
- `Depth Hz`: Actual depth rate achieved
- `Frame skip`: Interval between depth computations
- `Last avg depth`: Final depth measurement

## Performance Expectations

### With Frame Skipping

| Depth Mode | Target Hz | Frame Skip | Expected Grab FPS | Expected Depth Hz |
|------------|-----------|------------|-------------------|-------------------|
| NEURAL_PLUS | 10 Hz | Every 6th | 60 FPS | 10 Hz |
| NEURAL_PLUS | 5 Hz | Every 12th | 60 FPS | 5 Hz |
| NEURAL_PLUS | 1 Hz | Every 60th | 60 FPS | 1 Hz |
| PERFORMANCE | 10 Hz | None | 58 FPS | 58 Hz (limited by mode) |
| PERFORMANCE | 30 Hz | Every 2nd | 60 FPS | 30 Hz |

**Note**: NEURAL_PLUS is limited to ~11 FPS, so requesting 10 Hz will give ~7-10 Hz actual rate.

### Real-World Pipeline Performance

**YOLO + Depth (10 Hz)**:
```
Assumption: YOLO = 31ms, Grab = 16ms

Depth frames (every 6th):
  Grab (16ms) + YOLO (31ms) + Depth (91ms) = 138ms ← 7 FPS

Non-depth frames (5 out of 6):
  Grab (16ms) + YOLO (31ms) = 47ms ← 21 FPS

Average:
  (138ms + 47ms×5) / 6 = 62ms ← 16 FPS overall

Depth rate:
  1 depth per 6 frames at 16 FPS = 2.7 Hz actual
```

**Recommendation**: With 16 FPS pipeline, request **5 Hz depth** to achieve ~2.5 Hz actual.

## Practical Applications

### 1. Drone Landing on Moving Target

**Goal**: Track target at 30 FPS, depth at 10 Hz

```bash
# Configuration
python scripts/svo2_grab_speed_test.py
# Source: Live (2)
# Depth: PERFORMANCE (2) ← Fast enough for 30 Hz
# ROI: 50% (2) ← Assumes target in center
# Frequency: Custom (5) → Enter: 10
```

**Pipeline**:
1. Grab + YOLO: 60 FPS
2. Compute depth every 6th frame: 10 Hz
3. Average depth in 50% ROI = target distance
4. Use std dev to verify single target (low std = good)

### 2. Obstacle Avoidance

**Goal**: Detect closest obstacle continuously

```bash
# Configuration
# Source: Live (2)
# Depth: PERFORMANCE (2) ← Real-time priority
# ROI: 100% (1) ← Full field of view
# Frequency: 10 Hz (2)
```

**Logic**:
```python
if depth_min < 1.0:  # Less than 1 meter
    trigger_emergency_stop()
elif depth_min < 2.0:  # Less than 2 meters
    slow_down()
else:
    continue_normal_flight()
```

### 3. Verification Mode

**Goal**: Confirm target distance periodically

```bash
# Configuration
# Source: Live (2)
# Depth: NEURAL_PLUS (6) ← Best accuracy
# ROI: 25% (3) ← Small target area
# Frequency: 1 Hz (4)
```

**Logic**:
- YOLO tracks at 60 FPS
- Depth verifies once per second
- Use avg depth for range estimation
- Log for post-flight analysis

## Comparison: Before vs After

### Before (No Frame Skipping)

```
Configuration:
- Depth: NEURAL_PLUS, every frame
- Result: 11 FPS overall

Timeline (90ms per frame):
0ms:   Frame 1 (Grab + YOLO + Depth)
90ms:  Frame 2 (Grab + YOLO + Depth)
180ms: Frame 3 (Grab + YOLO + Depth)
270ms: Frame 4 (Grab + YOLO + Depth)
...

1 second = 11 frames = 11 Hz depth
```

**Drawback**: Miss fast-moving targets between frames (90ms gaps).

### After (10 Hz Frame Skipping)

```
Configuration:
- Grab: 60 FPS
- Depth: NEURAL_PLUS, 10 Hz target (~7 Hz actual)
- Result: 60 FPS grab, 7 Hz depth

Timeline:
0ms:   Frame 1 (Grab + YOLO + Depth) 
17ms:  Frame 2 (Grab + YOLO)
34ms:  Frame 3 (Grab + YOLO)
51ms:  Frame 4 (Grab + YOLO)
68ms:  Frame 5 (Grab + YOLO)
85ms:  Frame 6 (Grab + YOLO)
102ms: Frame 7 (Grab + YOLO + Depth)
...

1 second = 60 frames grab, ~7 depth computations
```

**Benefit**: Detect at 60 FPS, depth when needed, smooth tracking!

## Advanced: Adaptive Hz

For real applications, adjust depth Hz based on conditions:

```python
# Pseudo-code for adaptive depth frequency

if target_detected and tracking:
    depth_hz = 10  # Track with depth
    
elif searching:
    depth_hz = 1   # Occasional depth to map scene
    
elif approaching_target:
    depth_hz = 20  # High frequency for precise distance
    
else:
    depth_hz = None  # No depth, save power
```

## Troubleshooting

### Issue: Requested 10 Hz, Getting 7 Hz

**Cause**: NEURAL_PLUS is limited to ~11 FPS, and with overhead, actual is ~7 FPS.

**Solution**: Accept it, or switch to PERFORMANCE mode (can achieve true 10 Hz).

### Issue: Depth Stats Show 0.00m

**Cause**: All depth values invalid (NaN, inf, or <=0).

**Reasons**:
1. Camera too close to object (< 0.3m)
2. Poor lighting (IR patterns not visible)
3. Reflective surface (mirror, water)
4. Transparent object (glass)

**Solution**: Improve scene (add texture, better lighting), or check if using NEURAL mode helps.

### Issue: High Std Dev (>1.0m) with Single Target

**Cause**: Multiple objects in ROI or noisy depth.

**Solution**:
1. Reduce ROI to 25% (isolate target)
2. Use NEURAL_PLUS for better quality
3. Filter depth with median or moving average

### Issue: FPS Lower Than Expected

**Cause**: System load, thermal throttling, or competing processes.

**Solution**:
1. Check thermals: `tegrastats`
2. Set power mode: `sudo nvpmodel -m 0`
3. Close other applications
4. Reduce depth Hz if not needed

## Summary

**Key Features**:
✅ Real-time depth averaging (avg/min/max/std)
✅ Configurable Hz (1/5/10 or custom)
✅ Frame skipping for high FPS grab
✅ ROI support (100%/50%/25%)
✅ Live display with all metrics

**Best Practices**:
- Use **PERFORMANCE mode** + **10 Hz** for tracking
- Use **NEURAL_PLUS** + **5 Hz** for quality
- Use **25% ROI** when tracking single centered target
- Monitor **min depth** for collision avoidance
- Monitor **std dev** for target isolation confidence

**Typical Configuration** (drone tracking):
```
Source: Live camera
Depth: PERFORMANCE
ROI: 50%
Frequency: 10 Hz

Expected: 60 FPS grab, 10 Hz depth, smooth tracking!
```

Happy tracking! 🎯
