# ROI-Based Depth Computation Performance Analysis

## Concept: Depth Only Where You Need It

**Problem**: Computing depth for the full frame (1280×720) is expensive, especially with NEURAL_PLUS mode (11 FPS).

**Solution**: Only compute depth where YOLO detects objects!

In real-world usage:
1. YOLO detects an object → gives bounding box
2. Expand bbox slightly for context
3. Compute depth **only in that region**
4. Rest of frame: no depth computation

**Expected benefit**: If object covers 25% of frame, depth should be ~4x faster!

## Your Baseline Performance (Live Camera)

| Depth Mode | Full Frame (100%) | Notes |
|------------|-------------------|-------|
| NONE | 60 FPS | No depth, max speed |
| PERFORMANCE | 58 FPS | Fast stereo |
| NEURAL_PLUS | 11 FPS | AI depth, slow |

## Test Setup

Both Python and C++ versions now support ROI-based depth:

### ROI Options
1. **100%**: Full frame (1280×720) - baseline
2. **50%**: Half frame (640×360, centered) - simulates medium object
3. **25%**: Quarter frame (320×180, centered) - simulates small object

The ROI is always **centered** to simulate a target in the middle of the frame.

## Expected Results

### Hypothesis: Smaller ROI = Faster Depth

**NEURAL_PLUS mode predictions**:
```
100% ROI (1280×720): 11 FPS ← Your baseline
 50% ROI ( 640×360): 20-25 FPS? (1.8-2.3x faster)
 25% ROI ( 320×180): 35-45 FPS? (3.2-4.1x faster)
```

**Why this matters**:
- If YOLO detects object at 25% of frame
- And we get 35+ FPS with 25% ROI
- **Real-time AI depth becomes viable!**

### What Affects Speedup

**Best case** (linear scaling):
- Depth computation is 100% of the work
- 25% area = 25% time = 4x speedup
- 11 FPS → 44 FPS ✨

**Realistic case** (partial scaling):
- Depth is 70% of work, overhead is 30%
- 25% area = 47.5% total time = 2.1x speedup
- 11 FPS → 23 FPS

**Worst case** (limited scaling):
- Fixed overhead dominates (initialization, data transfer)
- 25% area = 80% total time = 1.25x speedup
- 11 FPS → 14 FPS ⚠️

## Testing Procedure

### Test 1: Baseline (100% ROI)
Confirm your baseline numbers:

**Python**:
```bash
python scripts/svo2_grab_speed_test.py

# Menu:
# 1. Source: 2 (Live camera)
# 2. Depth: 6 (NEURAL_PLUS)
# 3. ROI: 1 (100%)
# Wait 60s for neural init
# Let run for 20-30 seconds
# CTRL+C and note FPS
```

**Expected**: ~11 FPS (your baseline)

### Test 2: Half ROI (50%)
Test medium-sized object:

**Python**:
```bash
python scripts/svo2_grab_speed_test.py

# Menu:
# 1. Source: 2 (Live camera)
# 2. Depth: 6 (NEURAL_PLUS)
# 3. ROI: 2 (50%)
# Let run for 20-30 seconds
# CTRL+C and note FPS
```

**Expected**: 15-25 FPS (1.4-2.3x faster)

### Test 3: Quarter ROI (25%)
Test small object:

**Python**:
```bash
python scripts/svo2_grab_speed_test.py

# Menu:
# 1. Source: 2 (Live camera)
# 2. Depth: 6 (NEURAL_PLUS)
# 3. ROI: 3 (25%)
# Let run for 20-30 seconds
# CTRL+C and note FPS
```

**Expected**: 20-45 FPS (1.8-4.1x faster)

### Test 4: C++ Comparison
Verify Python vs C++ performance:

```bash
./scripts/svo2_grab_test_cpp

# Test same combinations:
# - Live, NEURAL_PLUS, 100%
# - Live, NEURAL_PLUS, 50%
# - Live, NEURAL_PLUS, 25%
```

**Expected**: Similar to Python (language not the bottleneck)

## Data Collection Template

```bash
cat > roi_depth_results.txt << 'EOF'
=================================================================
ROI-BASED DEPTH COMPUTATION PERFORMANCE
=================================================================

Hardware:
- Camera: ZED2i (S/N 34754237)
- System: Jetson Orin Nano Super
- Resolution: HD720 (1280x720)
- Depth Mode: NEURAL_PLUS

Test: Live Camera Feed
----------------------

PYTHON RESULTS:

100% ROI (1280×720, full frame):
  FPS: 11 (baseline)
  Frame time: 91 ms

50% ROI (640×360, centered):
  FPS: _____ 
  Frame time: _____ ms
  Speedup: _____ x

25% ROI (320×180, centered):
  FPS: _____
  Frame time: _____ ms
  Speedup: _____ x


C++ RESULTS:

100% ROI (1280×720, full frame):
  FPS: 11 (baseline)
  Frame time: 91 ms

50% ROI (640×360, centered):
  FPS: _____ 
  Frame time: _____ ms
  Speedup: _____ x

25% ROI (320×180, centered):
  FPS: _____
  Frame time: _____ ms
  Speedup: _____ x


ANALYSIS:
---------
Best speedup achieved: _____ x (with _____ % ROI)
Is speedup linear? [ ] Yes (4x with 25%) [ ] No (less than 4x)
Python vs C++: [ ] Same [ ] C++ faster by _____ %

Practical implications:
- If YOLO bbox covers 25% of frame → expect _____ FPS
- If YOLO bbox covers 50% of frame → expect _____ FPS
- Real-time YOLO + depth: [ ] Viable [ ] Not viable

Recommendations:
<Your conclusions here>

=================================================================
EOF

nano roi_depth_results.txt
```

## Test with Other Depth Modes

Not just NEURAL_PLUS - test PERFORMANCE mode too:

### PERFORMANCE Mode (baseline: 58 FPS)

**Question**: Can we reach 60 FPS with smaller ROI?

Test combinations:
```
Live + PERFORMANCE + 100% ROI: 58 FPS (baseline)
Live + PERFORMANCE +  50% ROI: _____ FPS (target: 60 FPS)
Live + PERFORMANCE +  25% ROI: _____ FPS (may hit camera limit)
```

**Why test**: If 50% ROI gets to 60 FPS, we maximize camera framerate while still getting fast depth!

## Interpreting Results

### Scenario A: Strong Scaling (3-4x speedup)

**Results**:
- 100% ROI: 11 FPS
- 50% ROI: 25 FPS (2.3x)
- 25% ROI: 40 FPS (3.6x)

**Meaning**: Depth computation dominates, ROI optimization very effective!

**Recommendation**: ✅ **Implement ROI-based depth in production**
- YOLO detects at 60 FPS
- Compute depth only in bbox
- Achieve 30-40 FPS with AI depth
- **Real-time target tracking possible!**

### Scenario B: Moderate Scaling (1.5-2x speedup)

**Results**:
- 100% ROI: 11 FPS
- 50% ROI: 16 FPS (1.5x)
- 25% ROI: 22 FPS (2.0x)

**Meaning**: Fixed overhead (grab, transfer) limits speedup

**Recommendation**: ⚠️ **ROI helps but not enough for real-time AI depth**
- Use PERFORMANCE mode instead (58 FPS)
- Only use NEURAL_PLUS for post-processing
- Or reduce resolution to HD720→VGA

### Scenario C: Weak Scaling (<1.5x speedup)

**Results**:
- 100% ROI: 11 FPS
- 50% ROI: 13 FPS (1.2x)
- 25% ROI: 14 FPS (1.3x)

**Meaning**: Depth computation is not the bottleneck, or ROI API not optimized

**Recommendation**: ❌ **ROI doesn't help, try other approaches**:
- Use PERFORMANCE mode (58 FPS, good enough?)
- Reduce resolution (HD720 → VGA gains 2x)
- Use depth only every Nth frame
- Pre-compute depth offline from SVO2

## Real-World Application

### YOLO + Depth Pipeline

**Current approach** (100% depth):
```
1. Grab frame: 16 ms
2. YOLO inference: 31 ms
3. Depth (full frame): 91 ms
   ----------------------
   Total: 138 ms → 7.2 FPS ❌
```

**With ROI optimization** (if 3x speedup):
```
1. Grab frame: 16 ms
2. YOLO inference: 31 ms
3. Depth (25% ROI): 30 ms
   ----------------------
   Total: 77 ms → 13 FPS ⚠️
```

**With PERFORMANCE mode** (current):
```
1. Grab frame: 16 ms
2. YOLO inference: 31 ms
3. Depth (PERFORMANCE): 17 ms
   -------------------------
   Total: 64 ms → 15.6 FPS ✅
```

**Best case** (ROI + skip frames):
```
Frame 1:
  1. Grab: 16 ms
  2. YOLO: 31 ms
  3. Depth (25% ROI): 30 ms
  Total: 77 ms

Frame 2-3: Skip depth, just YOLO
  1. Grab: 16 ms
  2. YOLO: 31 ms
  Total: 47 ms × 2

Average: (77 + 47 + 47) / 3 = 57 ms → 17.5 FPS ✨
```

## Quick Test Commands

### Test All ROI Sizes (Python, NEURAL_PLUS)
```bash
#!/bin/bash
for roi in "1" "2" "3"; do
    echo "Testing ${roi}% ROI..."
    echo -e "2\n6\n${roi}" | timeout 30 python scripts/svo2_grab_speed_test.py 2>&1 | grep "Average FPS"
    sleep 2
done
```

### Test All ROI Sizes (C++, NEURAL_PLUS)
```bash
#!/bin/bash
for roi in "1" "2" "3"; do
    echo "Testing ROI option ${roi}..."
    echo -e "2\n6\n${roi}" | timeout 30 ./scripts/svo2_grab_test_cpp 2>&1 | grep "Average FPS"
    sleep 2
done
```

## Success Criteria

### Minimum Goal
- **25% ROI achieves 20+ FPS** with NEURAL_PLUS
- Proves ROI optimization is viable
- Opens path to real-time AI depth

### Stretch Goal
- **25% ROI achieves 30+ FPS** with NEURAL_PLUS
- Near real-time with single-object tracking
- Can track target at 30 Hz with AI depth

### Ultimate Goal
- **50% ROI achieves 30+ FPS** with NEURAL_PLUS
- Can track larger objects in real-time
- Practical for drone landing on moving target

## Next Steps After Testing

Based on results:

1. **If ROI gives 3x+ speedup**:
   - Implement ROI depth in main benchmark app
   - Compute depth only in YOLO bboxes
   - Test full pipeline (grab + YOLO + ROI depth)

2. **If ROI gives 1.5-2x speedup**:
   - Consider hybrid: PERFORMANCE for tracking, NEURAL_PLUS for verification
   - Or: Depth every Nth frame, interpolate in between

3. **If ROI gives <1.5x speedup**:
   - Stick with PERFORMANCE mode (58 FPS is excellent)
   - Use NEURAL_PLUS only offline
   - Focus on YOLO optimization instead

Ready to test? Run the Python version first, then compare with C++! 🎯
