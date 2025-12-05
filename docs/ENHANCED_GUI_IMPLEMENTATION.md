# Enhanced SVO2 Benchmark GUI - Implementation Plan

## Summary of Requested Features

### 1. Component Timing Breakdown (Rolling Window)
- **Measure**: Grab time, YOLO inference time, Depth extraction time
- **Display**: Show as percentages of total frame time
- **Window**: Rolling average over last 60 frames
- **Logic**: Skip depth timing when no target found

### 2. Live Depth Map Visualization
- **Show**: Depth map only inside YOLO target bounding boxes
- **Toggle**: Button to show/hide during runtime
- **Format**: Colorized depth visualization

### 3. Depth Over Time Chart  
- **Type**: X-Y line chart
- **X-axis**: Frame number (last 60 frames)
- **Y-axis**: Depth in meters
- **Rolling**: 60-frame window

### 4. Stop Button
- **Function**: Gracefully terminate running benchmark
- **Behavior**: Clean up resources, save partial results

### 5. Pause/Resume
- **Function**: Pause benchmark, resume from same frame
- **State**: Maintain all statistics during pause

### 6. Fix Matplotlib
- **Issue**: KeyboardModifier TypeError with PySide6
- **Solution**: Use Agg backend, render to QPixmap

---

## Implementation Strategy

### Phase 1: Fix Matplotlib (Use Agg Backend)
```python
import os
os.environ['QT_API'] = 'pyside6'
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np
```

**Benefits**:
- Avoids Qt backend conflicts
- Render to buffer, convert to QPixmap
- Full control over updates

### Phase 2: Enhanced Timing Tracking

**Add to Worker Thread** (`SVOScenarioWorker`):
```python
# Rolling window for timing (60 frames)
self.timing_windows = {
    'grab': deque(maxlen=60),
    'inference': deque(maxlen=60),
    'depth': deque(maxlen=60)
}

# In run_frame loop:
grab_time = ... # milliseconds
inference_time = ...
depth_time = ... if has_detections else None

self.timing_windows['grab'].append(grab_time)
self.timing_windows['inference'].append(inference_time)
if depth_time is not None:
    self.timing_windows['depth'].append(depth_time)

# Calculate averages and percentages
grab_avg = mean(timing_windows['grab'])
inference_avg = mean(timing_windows['inference'])
depth_avg = mean(timing_windows['depth']) if timing_windows['depth'] else 0

total = grab_avg + inference_avg + depth_avg
grab_pct = (grab_avg / total) * 100
inference_pct = (inference_avg / total) * 100
depth_pct = (depth_avg / total) * 100 if depth_avg > 0 else 0
```

**Update Signal**:
```python
progress_updated = Signal(
    int,   # current frame
    int,   # total frames
    str,   # status
    float, # fps
    int,   # num_objects
    float, # mean_depth
    dict   # component_percentages {'grab': 65.2, 'inference': 28.1, 'depth': 6.7}
)
```

### Phase 3: Component Percentage Display

**GUI Widgets**:
```python
# Add to statistics panel
self.component_breakdown_label = QLabel("Component Breakdown:")
self.grab_pct_label = QLabel("Grab: -- %")
self.inference_pct_label = QLabel("Inference: -- %")
self.depth_pct_label = QLabel("Depth: -- %")

# Optionally: Progress bars showing percentages
self.grab_bar = QProgressBar()
self.grab_bar.setFormat("Grab: %p%")
self.inference_bar = QProgressBar()
self.inference_bar.setFormat("Inference: %p%")
self.depth_bar = QProgressBar()
self.depth_bar.setFormat("Depth: %p%")
```

### Phase 4: Live Depth Map Visualization

**Depth Map Widget**:
```python
class DepthMapViewer(QLabel):
    """Display depth map from target bbox area."""
    
    def update_depth_map(self, depth_array: np.ndarray, bbox: tuple):
        """
        Extract depth from bbox, colorize, display.
        
        Args:
            depth_array: Full depth map (HxW) in meters
            bbox: (x1, y1, x2, y2) in pixels
        """
        x1, y1, x2, y2 = bbox
        depth_roi = depth_array[y1:y2, x1:x2]
        
        # Normalize and colorize
        valid_mask = (depth_roi > 0) & ~np.isnan(depth_roi) & ~np.isinf(depth_roi)
        if valid_mask.any():
            vmin = depth_roi[valid_mask].min()
            vmax = depth_roi[valid_mask].max()
            
            # Create colorized image
            fig = Figure(figsize=(4, 3), dpi=100)
            ax = fig.add_subplot(111)
            im = ax.imshow(depth_roi, cmap='viridis', vmin=vmin, vmax=vmax)
            fig.colorbar(im, ax=ax, label='Depth (m)')
            ax.set_title('Depth Map (Target Area)')
            
            # Render to QPixmap
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            buf = canvas.buffer_rgba()
            w, h = canvas.get_width_height()
            qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888)
            self.setPixmap(QPixmap.fromImage(qimg))
```

**Toggle Button**:
```python
self.toggle_depthmap_btn = QPushButton("Show Depth Map")
self.toggle_depthmap_btn.setCheckable(True)
self.toggle_depthmap_btn.toggled.connect(self._on_depthmap_toggled)

def _on_depthmap_toggled(self, checked: bool):
    self.depth_map_viewer.setVisible(checked)
    self.show_depth_map = checked
```

### Phase 5: Depth Over Time Chart

**Depth Plot Widget**:
```python
class DepthTimePlot(QLabel):
    """Line chart: Depth (m) vs Frame number."""
    
    def __init__(self):
        super().__init__()
        self.depth_history = deque(maxlen=60)  # Last 60 frames
        self.setMinimumSize(400, 200)
    
    def update_plot(self, depth: float):
        """Add new depth value and redraw."""
        self.depth_history.append(depth if depth > 0 else np.nan)
        
        fig = Figure(figsize=(5, 2.5), dpi=100)
        ax = fig.add_subplot(111)
        
        x = list(range(len(self.depth_history)))
        y = list(self.depth_history)
        
        ax.plot(x, y, 'b-', linewidth=2, marker='o', markersize=3)
        ax.fill_between(x, 0, y, alpha=0.3)
        ax.set_xlabel('Frame (last 60)', fontsize=9)
        ax.set_ylabel('Depth (m)', fontsize=9)
        ax.set_title('Depth Over Time', fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # Render to QPixmap
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        w, h = canvas.get_width_height()
        qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888)
        self.setPixmap(QPixmap.fromImage(qimg))
```

### Phase 6: Stop Button

**UI Button**:
```python
self.stop_btn = QPushButton("⏹ Stop")
self.stop_btn.setStyleSheet("background-color: #F44336; color: white;")
self.stop_btn.clicked.connect(self._stop_benchmark)
self.stop_btn.setEnabled(False)  # Enable when running
```

**Worker Thread**:
```python
def _stop_benchmark(self):
    """Request graceful stop."""
    if self.svo_worker:
        self.output_text.append("\n⏹ Stopping benchmark...")
        self.svo_worker.cancel()
        
def cancel(self):
    """Set cancellation flag."""
    self._cancelled = True
    self.output_text.append("Cleaning up...")
```

**Save Partial Results**:
```python
# In worker cleanup
if self._cancelled:
    stats['status'] = 'cancelled'
    stats['frames_completed'] = frames_processed
    
    # Save partial stats
    stats_file = self.output_folder / "benchmark_stats_partial.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    self.scenario.cleanup()
    self.benchmark_failed.emit(f"Cancelled by user after {frames_processed} frames")
```

### Phase 7: Pause/Resume

**UI Buttons**:
```python
self.pause_btn = QPushButton("⏸ Pause")
self.pause_btn.setStyleSheet("background-color: #FF9800; color: white;")
self.pause_btn.clicked.connect(self._toggle_pause)
self.pause_btn.setEnabled(False)

def _toggle_pause(self):
    """Toggle pause state."""
    if self.svo_worker:
        if self.svo_worker._paused:
            self.svo_worker.resume()
            self.pause_btn.setText("⏸ Pause")
            self.output_text.append("\n▶ Resumed")
        else:
            self.svo_worker.pause()
            self.pause_btn.setText("▶ Resume")
            self.output_text.append("\n⏸ Paused")
```

**Worker Thread**:
```python
def __init__(self):
    ...
    self._paused = False
    self._pause_lock = threading.Lock()

def pause(self):
    """Set pause flag."""
    self._paused = True

def resume(self):
    """Clear pause flag."""
    self._paused = False

def _run_benchmark_internal(self):
    """Run benchmark with pause support."""
    while not self._cancelled:
        # Check for pause
        while self._paused and not self._cancelled:
            time.sleep(0.1)  # Wait while paused
        
        if self._cancelled:
            break
        
        # Process frame
        result = self.scenario.run_frame(None)
        ...
```

---

## Modified Signals

```python
# SVOScenarioWorker
progress_updated = Signal(
    int,    # current
    int,    # total
    str,    # status
    float,  # fps
    int,    # num_objects
    float,  # mean_depth
    dict,   # component_percentages: {'grab': 65.2, 'inference': 28.1, 'depth': 6.7}
    object  # depth_map_data: {'depth_array': np.ndarray, 'bbox': (x1,y1,x2,y2)} or None
)
```

---

## GUI Layout Changes

```
┌────────────────────────────────────────────────────────────┐
│  Left Panel (Controls)  │  Right Panel (Visualization)     │
├────────────────────────────────────────────────────────────┤
│ 1. Scenario             │  ┌──────────────────────────┐   │
│ 2. Engine               │  │  Live Preview            │   │
│ 3. Input                │  │  (480x270 - 640x360)     │   │
│ 4. Options              │  └──────────────────────────┘   │
│                         │                                  │
│ [Initialize SVO2]       │  ┌──────────────────────────┐   │
│ [Start Processing]      │  │  Component Breakdown     │   │
│ [Pause] [Stop]          │  │  Grab:      65.2%        │   │
│                         │  │  Inference: 28.1%        │   │
│                         │  │  Depth:      6.7%        │   │
│                         │  └──────────────────────────┘   │
│                         │                                  │
│                         │  [Toggle Depth Map]              │
│                         │  ┌──────────────────────────┐   │
│                         │  │  Depth Map (if toggled)  │   │
│                         │  │  (Colorized heatmap)     │   │
│                         │  └──────────────────────────┘   │
│                         │                                  │
│                         │  ┌──────────────────────────┐   │
│                         │  │  Depth Over Time         │   │
│                         │  │  (Line chart, 60 frames) │   │
│                         │  └──────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

---

## Testing Checklist

- [ ] Matplotlib renders without Qt backend errors
- [ ] Component percentages sum to 100%
- [ ] Rolling window updates smoothly (60 frames)
- [ ] Depth map shows only when detections present
- [ ] Toggle button hides/shows depth map during runtime
- [ ] Depth over time plot updates every frame
- [ ] Stop button terminates gracefully, saves partial stats
- [ ] Pause button freezes processing
- [ ] Resume continues from exact frame
- [ ] Statistics remain accurate after pause/resume
- [ ] All visualizations clear on new benchmark

---

## Performance Considerations

1. **Matplotlib Rendering**: Use Agg backend (~5-10ms per plot)
2. **Depth Map**: Only render when toggle enabled
3. **Update Frequency**: Consider updating plots every 5 frames if slow
4. **Memory**: `deque(maxlen=60)` automatically manages memory

---

## Implementation Order

1. ✅ Fix matplotlib (Agg backend)
2. ✅ Add timing tracking to worker
3. ✅ Add percentage display to GUI
4. ✅ Add depth map viewer with toggle
5. ✅ Add depth over time plot
6. ✅ Add stop button
7. ✅ Add pause/resume buttons

---

This implementation will provide comprehensive real-time insights into the SVO2 pipeline performance!
