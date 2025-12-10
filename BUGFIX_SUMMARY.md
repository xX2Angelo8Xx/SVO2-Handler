# Bug Fixes Summary - December 5, 2025

## Issues Fixed

### 1. ✅ RecursionError in DepthMapViewer.clear()
**Problem**: Infinite recursion when calling `clear()` method
```python
# BEFORE (Line 226)
def clear(self):
    self.clear()  # ❌ Calls itself infinitely!
    self.setText("No depth data")
```

**Solution**: Remove recursive call
```python
# AFTER
def clear(self):
    self.setText("No depth data")  # ✅ Direct call to QLabel method
    self.setStyleSheet("background-color: #000; color: #666; border: 1px solid #555;")
```

**Impact**: No more crashes when toggling depth heatmap or starting processing

---

### 2. ✅ Depth Map Overlapping Console
**Problem**: Depth heatmap appeared below console, overlapping it

**Solution**: Moved depth heatmap to be side-by-side with depth plot
- Created horizontal layout for depth visualizations
- Depth plot on left (60% width, stretch=3)
- Depth heatmap on right (40% width, stretch=2)
- Both maintain same height (200-250px)

**Layout Structure**:
```
[Depth Plot]  [Depth Heatmap]
     60%            40%
```

**Impact**: Professional side-by-side layout, no console overlap

---

### 3. ⚠️ SVO2 Processing Not Starting (DEBUG MODE)
**Problem**: After initialization, clicking "Start Processing" does nothing

**Investigation**: Added debug output to trace signal flow
- Worker thread waits in Phase 2 for `_start_benchmark` flag
- GUI emits `start_processing` signal
- Signal connected with `Qt.ConnectionType.QueuedConnection` for thread safety

**Debug Output Added**:
1. GUI side: When signal emitted
2. Worker side: 
   - When waiting starts
   - Every 1 second during wait
   - When flag is set
   - When wait loop exits

**Next Steps**: 
- Launch app with console visible
- Initialize SVO2
- Click "Start Processing"
- Check console for debug messages:
  ```
  [DEBUG] Worker: Waiting for start signal...
  [DEBUG] GUI: Emitting start_processing signal...
  [DEBUG] _set_start_flag called - setting _start_benchmark to True
  [DEBUG] Wait loop exited: _start_benchmark=True, _cancelled=False
  ```

**Possible Issues**:
- Signal/slot connection timing issue
- Qt event loop not processing queued signals
- Worker thread blocked before reaching wait loop

---

## Code Changes

### Files Modified
- `src/svo_handler/jetson_benchmark_app.py`

### Line Changes
1. **Line 225**: Fixed `DepthMapViewer.clear()` recursion
2. **Lines 1450-1500**: Restructured depth visualization layout
3. **Line 532**: Added `Qt.ConnectionType.QueuedConnection` to signal
4. **Line 538**: Added debug output in `_set_start_flag()`
5. **Lines 587-596**: Added debug output in wait loop
6. **Lines 1731-1733**: Added debug output when emitting signal

---

## Testing Checklist

### ✅ Completed
- [x] App launches without crash
- [x] No RecursionError when toggling heatmap
- [x] Depth heatmap shows next to depth plot (not under console)

### 🔄 Needs Testing
- [ ] Initialize SVO2 file successfully
- [ ] Check debug output in console
- [ ] Click "Start Processing" button
- [ ] Verify processing actually starts
- [ ] Check if component percentages update
- [ ] Toggle depth heatmap during processing
- [ ] Toggle depth time chart during processing
- [ ] Verify no console overlap
- [ ] Test pause/resume functionality
- [ ] Test stop button

---

## Known Issues (Still Open)

### Self-Calibration Warning
```
[ZED][WARNING] Self-calibration skipped. Scene may be occluded or lack texture.
```
**Status**: This is a ZED SDK warning, not a code bug. Occurs when SVO2 file doesn't have good calibration data or scene lacks features. Can be ignored for benchmarking.

### YOLO Task Warning
```
WARNING ⚠️ Unable to automatically guess model task, assuming 'task=detect'.
```
**Status**: Informational warning from YOLO. Since we're using TensorRT engines, this is expected and harmless.

---

## Performance Impact

All fixes have **zero performance impact**:
- RecursionError fix: Same logic, just correct
- Layout change: Pure UI restructuring
- Debug output: Only prints to console (can be removed after testing)

---

## Next Steps

1. **Test Processing Start**:
   ```bash
   cd /home/angelo/Projects/SVO2-Handler
   python -m svo_handler.jetson_benchmark_app
   # Watch console for debug messages
   ```

2. **If Processing Still Doesn't Start**:
   - Check if `[DEBUG]` messages appear
   - If no messages: Signal connection issue
   - If stuck in wait loop: Flag not being set
   - If worker crashes: Check for exceptions in benchmark code

3. **Remove Debug Output** (after fixing):
   - Remove print statements from lines 538, 587-596, 1731-1733
   - Remove Qt.ConnectionType parameter if not needed

---

## Commits

Ready to commit once processing start issue is verified:
```bash
git add src/svo_handler/jetson_benchmark_app.py
git commit -m "fix: Resolve RecursionError and layout issues in benchmark GUI

- Fix infinite recursion in DepthMapViewer.clear()
- Move depth heatmap next to depth plot (side-by-side layout)
- Add debug output for processing start issue investigation
- Improve signal/slot connection for cross-thread communication"
```

---

## Documentation

After fixes verified:
- Update `docs/applications.md` with new layout screenshots
- Update `FINAL_UPDATES.md` with bugfix notes
- Add to `docs/fieldtest-learnings.md` if relevant
