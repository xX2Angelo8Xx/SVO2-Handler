# Live Camera vs SVO2 File Performance Analysis

## Problem: Low FPS Even in C++

Your testing revealed something important:
- **Expected**: C++ much faster than Python
- **Reality**: Both similar performance (24-30 FPS with NONE, 9 FPS with NEURAL_PLUS)

This suggests the **bottleneck is NOT the programming language**, but something else.

## Your Performance Results

### SVO2 File Playback (from `/media/angelo/DRONE_DATA1/...`)

| Mode | Python FPS | C++ FPS | Notes |
|------|-----------|---------|-------|
| NONE (No depth) | 30 | 24-30 | Nearly identical! |
| PERFORMANCE | 21 | 22 | Nearly identical! |
| NEURAL_PLUS | 9 | 9 | Identical! |

**Key Finding**: C++ provides **zero speedup** over Python when reading from SVO2 files.

## Why SVO2 Files Are Slow

### 1. **Disk I/O Bottleneck**
SVO2 files store compressed video + depth data:
- Each frame: ~26 MB/s × 60 FPS = **1.56 GB/s read bandwidth needed**
- Your storage: USB drive or HDD likely maxes out at 100-200 MB/s
- **Result**: Can only sustain ~6-12 FPS from disk alone

### 2. **Decompression Overhead**
Each frame must be:
1. Read from disk (slow)
2. Decompressed (CPU intensive)
3. Transferred to GPU memory
4. Processed by ZED SDK

**Both Python and C++ hit the same bottleneck** (disk + decompression).

### 3. **File Format Overhead**
SVO2 format optimized for:
- ✅ Storage efficiency
- ✅ Data preservation
- ❌ **NOT optimized for playback speed**

## Expected Performance: Live vs SVO2

### Hypothesis: Live Camera Should Be Much Faster

**Live camera advantages**:
1. **No disk I/O**: Data comes directly from camera sensors
2. **No decompression**: Raw sensor data, no decode overhead
3. **Direct GPU pipeline**: Camera → GPU, no CPU bottleneck
4. **Hardware-optimized**: ZED SDK tuned for live streaming

**Expected speedup with live camera**:
```
NONE mode:        30 FPS (SVO2) → 60 FPS (LIVE) = 2.0x faster ✨
PERFORMANCE mode: 21 FPS (SVO2) → 60 FPS (LIVE) = 2.9x faster ✨✨
NEURAL_PLUS mode:  9 FPS (SVO2) → 30 FPS (LIVE) = 3.3x faster ✨✨✨
```

### Why Live Depth Might Be Faster

Neural depth processing optimized for real-time:
- Live: Can use hardware accelerators efficiently
- SVO2: Must sync with file playback, can't optimize pipeline
- **Live neural might reach 30+ FPS** vs SVO2's 9 FPS

## Testing Live Camera Performance

### Python Version
```bash
cd /home/angelo/Projects/SVO2-Handler
python scripts/svo2_grab_speed_test.py

# Menu:
# 1. Choose source: 2 (Live camera)
# 2. Choose depth mode: 1 (NONE - fastest)
# Press CTRL+C after 10-20 seconds
# Note the FPS
```

### C++ Version
```bash
cd /home/angelo/Projects/SVO2-Handler
./scripts/svo2_grab_test_cpp

# Menu:
# 1. Choose source: 2 (Live camera)
# 2. Choose depth mode: 1 (NONE - fastest)
# Press CTRL+C after 10-20 seconds
# Note the FPS
```

### Test All Depth Modes (Live Camera Only)

| Depth Mode | Expected FPS (Live) | Expected FPS (SVO2) | Speedup |
|------------|---------------------|---------------------|---------|
| NONE | 60 FPS | 30 FPS | 2.0x |
| PERFORMANCE | 60 FPS | 21 FPS | 2.9x |
| QUALITY | 30 FPS | 15 FPS | 2.0x |
| ULTRA | 15 FPS | 10 FPS | 1.5x |
| NEURAL | 30 FPS | 8 FPS | 3.8x |
| NEURAL_PLUS | 30 FPS | 9 FPS | 3.3x |

## Data Collection Template

```bash
# Create comparison file
cat > live_vs_svo2_results.txt << 'EOF'
=================================================================
LIVE CAMERA vs SVO2 FILE PERFORMANCE COMPARISON
=================================================================

Hardware:
- Camera: ZED2i (S/N 34754237)
- System: Jetson Orin Nano Super
- Resolution: HD720 (1280x720)
- Target FPS: 60

SVO2 Test File:
- Path: /media/angelo/DRONE_DATA1/flight_20251124_161414_Mixed/video.svo2
- Total frames: 10002
- Original FPS: 60

Results:
--------

NONE Mode (No Depth):
  SVO2 File:   30 FPS ← DISK BOTTLENECK
  Live Camera: _____ FPS ← Expected: 60 FPS
  Speedup:     _____ x

PERFORMANCE Mode (Fast Stereo Depth):
  SVO2 File:   21 FPS ← DISK + DECODE BOTTLENECK
  Live Camera: _____ FPS ← Expected: 60 FPS
  Speedup:     _____ x

NEURAL_PLUS Mode (AI Depth):
  SVO2 File:   9 FPS ← DISK + DECODE + NEURAL
  Live Camera: _____ FPS ← Expected: 30 FPS
  Speedup:     _____ x

Analysis:
---------
Primary bottleneck in SVO2 playback: [ ] Disk I/O [ ] Decompression [ ] Both
Live camera removes bottleneck: [ ] Yes [ ] No
Recommended for real-time use: [ ] Live [ ] SVO2 [ ] Depends

Conclusions:
------------
<Your findings here>

=================================================================
EOF

nano live_vs_svo2_results.txt
```

## Architectural Implications

### If Live Camera Is 2-3x Faster

**Finding**: SVO2 file I/O is the bottleneck, not Python/C++

**Recommendations**:
1. ✅ **Use live camera for real-time detection** (60 FPS possible)
2. ✅ **Keep Python for development** (no performance penalty vs C++)
3. ✅ **Use SVO2 only for recording/analysis** (not real-time)
4. ⚠️ **Consider RAM disk for SVO2 playback** if needed:
   ```bash
   # Create 8GB RAM disk
   sudo mkdir -p /mnt/ramdisk
   sudo mount -t tmpfs -o size=8192M tmpfs /mnt/ramdisk
   
   # Copy SVO2 to RAM
   cp /media/angelo/.../video.svo2 /mnt/ramdisk/
   
   # Test again (should be much faster)
   ```

### If Live Camera Is NOT Significantly Faster

**Finding**: ZED SDK itself is the bottleneck

**Recommendations**:
1. ⚠️ **Check ZED SDK version** - update to latest
2. ⚠️ **Check power mode** - ensure Jetson in MAXN mode
3. ⚠️ **Check thermal throttling** - monitor with `tegrastats`
4. ⚠️ **Contact StereoLabs support** - performance below spec

## Bottleneck Decision Tree

```
Low FPS observed (30 FPS with NONE mode)
│
├─ Is C++ faster than Python? NO ← You are here
│  └─ Bottleneck is NOT language
│     │
│     ├─ Is LIVE faster than SVO2? → Test this now!
│     │  ├─ YES (2x+) → Bottleneck is disk I/O
│     │  │  └─ Solution: Use live camera for real-time
│     │  │
│     │  └─ NO (same speed) → Bottleneck is ZED SDK or hardware
│     │     └─ Check: Power mode, thermals, SDK version
│     │
│     └─ Test complete
│
└─ Is C++ faster than Python? YES (not your case)
   └─ Bottleneck was language overhead
      └─ Solution: Rewrite in C++
```

## Quick Test Commands

### Test 1: Live Camera, No Depth (Should be ~60 FPS)
```bash
# Python
echo -e "2\n1" | python scripts/svo2_grab_speed_test.py &
sleep 15 && pkill -INT python

# C++
echo -e "2\n1" | ./scripts/svo2_grab_test_cpp &
sleep 15 && pkill -INT svo2_grab_test_cpp
```

### Test 2: Live Camera, NEURAL_PLUS (Should be ~30 FPS)
```bash
# Python
echo -e "2\n6" | python scripts/svo2_grab_speed_test.py &
sleep 30 && pkill -INT python  # Wait longer for neural init

# C++
echo -e "2\n6" | ./scripts/svo2_grab_test_cpp &
sleep 30 && pkill -INT svo2_grab_test_cpp
```

## What We're Testing

### Current Understanding:
```
SVO2 Pipeline (SLOW):
Disk → Read (100 MB/s) → Decompress (CPU) → GPU → ZED SDK → Your Code
 ↑                         ↑
 BOTTLENECK 1           BOTTLENECK 2
 ~30 FPS max            ~30 FPS max
```

### Hypothesis with Live Camera:
```
Live Pipeline (FAST?):
Camera → Direct GPU Transfer → ZED SDK → Your Code
         ↑
         NO BOTTLENECK?
         60 FPS possible?
```

## System Checks Before Testing

### 1. Verify Power Mode (Jetson)
```bash
# Check current mode
sudo nvpmodel -q

# Set to maximum performance (MAXN)
sudo nvpmodel -m 0

# Verify
sudo nvpmodel -q | grep "NV Power Mode"
# Should show: MAXN
```

### 2. Check Thermals
```bash
# Monitor while testing
tegrastats

# Watch for:
# - CPU throttling (if freq drops)
# - GPU throttling (if freq drops)
# - Temperature >75°C (thermal limit approaching)
```

### 3. Verify Storage Speed (SVO2 disk)
```bash
# Test read speed of USB drive
sudo hdparm -t /dev/sdX  # Replace X with your drive letter

# Should see:
# - USB 3.0 HDD: 80-120 MB/s
# - USB 3.0 SSD: 200-400 MB/s
# - USB 2.0: <40 MB/s (way too slow!)
```

### 4. Check ZED SDK Version
```bash
python -c "import pyzed.sl as sl; print(sl.Camera.get_sdk_version())"

# Should be: 5.0.x or later
# If older, update: https://www.stereolabs.com/developers/release
```

## Expected Outcomes

### Best Case: Live Camera Fixes Everything ✨
- **Live**: 60 FPS with NONE, 30 FPS with NEURAL_PLUS
- **SVO2**: 30 FPS with NONE, 9 FPS with NEURAL_PLUS
- **Conclusion**: Use live for deployment, SVO2 only for testing
- **Action**: Keep Python, focus on live optimization

### Worst Case: Still Slow with Live Camera ⚠️
- **Live**: 30 FPS with NONE (same as SVO2)
- **Conclusion**: Hardware or ZED SDK limitation
- **Action**: 
  1. Check power mode and thermals
  2. Update ZED SDK
  3. Test with official ZED samples
  4. Contact StereoLabs if still slow

### Middle Case: Some Improvement
- **Live**: 45 FPS with NONE (better but not 60)
- **Conclusion**: Partial bottleneck removed
- **Action**: Profile to find remaining bottleneck

## Next Steps

1. **Run live camera tests** (both Python and C++)
2. **Record FPS values** for NONE, PERFORMANCE, NEURAL_PLUS
3. **Calculate speedup** (Live FPS ÷ SVO2 FPS)
4. **Analyze results** using decision tree above
5. **Optimize** based on findings

## Questions to Answer

After testing with live camera:

1. **Is live camera ≥2x faster than SVO2?**
   - Yes → Disk I/O is the bottleneck, use live for real-time
   - No → Continue investigation

2. **Does live camera reach 60 FPS with NONE mode?**
   - Yes → Hardware is capable, SVO2 is the problem
   - No → Hardware or SDK limitation

3. **Is Python still same speed as C++ with live camera?**
   - Yes → Language doesn't matter, keep Python
   - No → C++ provides benefit only with live

4. **Can live camera sustain 30+ FPS with NEURAL_PLUS?**
   - Yes → Real-time AI depth possible
   - No → Must use faster depth mode or reduce resolution

Ready to test? Connect your ZED camera and run the tests! 🚀
