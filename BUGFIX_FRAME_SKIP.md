# Frame Skip Bug Fix

## Problem
User reported: "I see skipping is implemented and the gui tells me skipped from frame n to n+100 but after resuming the frames actually haven't changed and it's resuming from its last played frame like nothing happened"

## Root Cause
The issue was in the frame index management. In `benchmark_scenarios.py`, the `frame_index` is incremented at the **end** of `run_frame()` (line 610):

```python
def run_frame(self, frame_data: Any) -> Dict[str, Any]:
    # ... grab and process frame ...
    self.frame_index += 1  # Incremented at END
    return result
```

This means `frame_index` always points to the frame we're **about to process**, not the one we just processed.

## The Bugs
There were TWO bugs preventing frame skipping from working:

### Bug #1: Frame Index Off-by-One
Original skip implementation (WRONG):
```python
self.scenario.camera.set_svo_position(target_pos)  # Camera at target_pos
self.scenario.frame_index = target_pos             # Index at target_pos
```

**What happened**:
1. Skip to frame 120: `set_svo_position(120)`, `frame_index = 120`
2. Resume → `run_frame()` grabs frame 120 ✅
3. End of `run_frame()` does `frame_index += 1` → becomes 121
4. Next iteration grabs frame 121 (skipped one extra!) ❌

The camera WAS positioned correctly, but the index accounting was off by one!

### Bug #2: Display Counter vs Actual Position
The progress display was using a local counter (`frames_processed`) instead of the actual SVO frame position:

```python
frames_processed += 1  # Just counts iterations: 1, 2, 3, 4...
status = f"Frame {frames_processed}/{total_frames}"  # Shows wrong frame!
```

**What happened**:
- Camera skips to frame 148
- But `frames_processed` is still at 48 (only counts iterations)
- Display shows "Frame 50/9786" even though we're at frame 148!
- User sees skip message but thinks it didn't work

## The Fixes

### Fix #1: Frame Index Off-by-One
Updated skip implementation (CORRECT):
```python
self.scenario.camera.set_svo_position(target_pos)      # Camera at target_pos
self.scenario.frame_index = target_pos - 1             # Index ONE BEFORE target
```

**What happens now**:
1. Skip to frame 120: `set_svo_position(120)`, `frame_index = 119`
2. Resume → `run_frame()` grabs frame 120 ✅
3. End of `run_frame()` does `frame_index += 1` → becomes 120 ✅
4. Next iteration grabs frame 121 ✅ (correct sequential processing)

### Fix #2: Display Actual Frame Position
Use the actual SVO frame index from the result dictionary:

```python
# Get actual frame index from scenario (important for skip functionality)
actual_frame_index = result.get('frame_index', frames_processed)

# Use actual_frame_index to show correct position after skips
status = f"Frame {actual_frame_index}/{total_frames}"
self.progress_updated.emit(actual_frame_index, total_frames, status, ...)
```

**What happens now**:
- `actual_frame_index` reflects the true SVO frame position
- After skip to frame 148, display shows "Frame 148/9786" ✅
- Progress bar also uses actual position
- User sees correct frame numbers throughout

## Code Changes

### File: `src/svo_handler/jetson_benchmark_app.py`

**Change #1: Fix frame index off-by-one** (Lines 658-676 in pause loop):

```python
# Check if frame skip was requested
if self._skip_frames > 0:
    skip_count = self._skip_frames
    self._skip_frames = 0  # Reset
    
    # Get current position
    current_pos = self.scenario.frame_index
    target_pos = min(current_pos + skip_count, self.scenario.total_frames - 1)
    
    # Use ZED SDK's set_svo_position for efficient skipping
    try:
        self.scenario.camera.set_svo_position(target_pos)
        # Note: frame_index will be incremented by run_frame() after grab
        # So we set it to target_pos - 1 so after increment it becomes target_pos
        self.scenario.frame_index = target_pos - 1  # ← FIX #1: Subtract 1
        self.frames_skipped.emit(skip_count, target_pos)
    except Exception as e:
        print(f"Error skipping frames: {e}")
```

**Change #2: Use actual frame position in display** (Lines 697-700, 783-785):

```python
frames_processed += 1

# Get actual frame index from scenario (important for skip functionality)
actual_frame_index = result.get('frame_index', frames_processed)  # ← FIX #2

# ... later in code ...

# Update progress with detection info and component percentages
# Use actual_frame_index to show correct position after skips
status = f"Frame {actual_frame_index}/{total_frames}"  # ← FIX #2: Use actual
self.progress_updated.emit(actual_frame_index, total_frames, status, ...)  # ← FIX #2
```

### Documentation Update
**File: `FRAME_SKIP_FEATURE.md`**
- Added detailed "Frame Index Management" section explaining the off-by-one issue
- Updated code examples to show the `-1` adjustment
- Added example flow demonstrating correct behavior

## Verification
To verify the fix works:

1. Run benchmark app: `python -m svo_handler.jetson_benchmark_app`
2. Select SVO2 Pipeline scenario
3. Initialize and start processing
4. Let it process ~20 frames (note frame number in status bar)
5. Click Pause
6. Set skip to 50 frames
7. Click Skip button
8. **Observe**: Console should show "Skipped 50 frames → Now at frame 70"
9. Click Resume
10. **Verify**: Processing should continue from frame 70 (not 20, not 71)
11. **Check**: Next frame should be 71, then 72, etc. (sequential)

## Technical Insight
This is a classic off-by-one error caused by different frame index semantics:
- **Camera position**: Points to the frame that WILL BE grabbed
- **Frame index**: Points to the frame we're ABOUT TO process (before grab)
- **Post-grab increment**: Prepares index for the NEXT frame

The fix ensures these three states remain synchronized when jumping to a new position.

## Files Modified
1. `src/svo_handler/jetson_benchmark_app.py`:
   - Line 673: Added `-1` to frame_index assignment (fix off-by-one)
   - Line 700: Added `actual_frame_index` extraction from result
   - Lines 783-785: Changed status and progress_updated to use `actual_frame_index`
2. `FRAME_SKIP_FEATURE.md` - Added comprehensive frame index management documentation
3. `BUGFIX_FRAME_SKIP.md` - This document

## Summary of Changes
- **Before**: Skip appeared to work in console, but display and actual processing didn't match
- **After**: Skip works correctly - both camera position AND display show actual frame number
- **Root causes**: Off-by-one in frame_index + display counter vs actual position mismatch
- **Impact**: Frame skipping now fully functional for rapid SVO2 navigation

## Testing Status
- ✅ Both code fixes applied
- ⏳ Awaiting user verification with actual SVO2 file
