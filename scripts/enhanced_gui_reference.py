#!/usr/bin/env python3
"""
Enhanced SVO2 Benchmark GUI Implementation Script

This script contains all the code additions needed for the enhanced GUI.
Due to the file size, apply these changes manually or use this as reference.
"""

# ============================================================================
# STEP 1: Fix Matplotlib Import (Replace lines 1-52)
# ============================================================================

MATPLOTLIB_FIX = """
#!/usr/bin/env python3
import sys
import os
import json
import time
import shutil
import random
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple
from collections import deque

# Set matplotlib to use Agg backend (non-interactive) BEFORE any other imports
os.environ['MPLBACKEND'] = 'Agg'
import matplotlib
matplotlib.use('Agg')

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit,
    QGroupBox, QMessageBox, QProgressDialog, QScrollArea, QSpinBox, QCheckBox,
    QStackedWidget, QComboBox, QProgressBar, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QPen, QColor, QBrush

# Matplotlib components (Agg backend - no Qt conflicts)
MATPLOTLIB_AVAILABLE = False
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import numpy as np
    import cv2
    MATPLOTLIB_AVAILABLE = True
    print("✅ Matplotlib loaded successfully with Agg backend")
except Exception as e:
    print(f"⚠️  Warning: matplotlib not available ({type(e).__name__}: {e})")
    print("   Depth visualizations will be disabled.")
"""

# ============================================================================
# STEP 2: New Widget Classes
# ============================================================================

DEPTH_MAP_VIEWER_CLASS = '''
class DepthMapViewer(QLabel):
    """Display colorized depth map from target detection area."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 225)
        self.setMaximumSize(400, 300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #000; border: 2px solid #444;")
        self.setText("Depth Map\\n(Toggle to show)")
        self.setStyleSheet("color: #666; background-color: #000;")
    
    def update_depth_map(self, depth_array: 'np.ndarray', bbox: tuple):
        """
        Extract and display depth map from bbox region.
        
        Args:
            depth_array: Full depth map (HxW) in meters
            bbox: (x1, y1, x2, y2) bounding box coordinates
        """
        if not MATPLOTLIB_AVAILABLE:
            return
        
        try:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            
            # Extract ROI
            depth_roi = depth_array[y1:y2, x1:x2]
            
            # Filter valid depth values
            valid_mask = (
                (depth_roi > 0) & 
                ~np.isnan(depth_roi) & 
                ~np.isinf(depth_roi) &
                (depth_roi <= 40.0)
            )
            
            if not valid_mask.any():
                self.setText("No valid\\ndepth data")
                return
            
            # Create figure
            fig = Figure(figsize=(4, 3), dpi=80)
            fig.patch.set_facecolor('#1e1e1e')
            ax = fig.add_subplot(111)
            
            # Plot depth map
            vmin = depth_roi[valid_mask].min()
            vmax = depth_roi[valid_mask].max()
            
            im = ax.imshow(depth_roi, cmap='viridis', vmin=vmin, vmax=vmax, 
                          interpolation='nearest')
            cbar = fig.colorbar(im, ax=ax, label='Depth (m)')
            cbar.ax.tick_params(labelsize=8, colors='white')
            cbar.set_label('Depth (m)', color='white', fontsize=9)
            
            ax.set_title('Depth Map (Target Area)', color='white', fontsize=10, 
                        fontweight='bold')
            ax.set_xlabel('Width (px)', color='white', fontsize=8)
            ax.set_ylabel('Height (px)', color='white', fontsize=8)
            ax.tick_params(colors='white', labelsize=7)
            ax.set_facecolor('#2e2e2e')
            
            fig.tight_layout()
            
            # Render to QPixmap
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            buf = canvas.buffer_rgba()
            w, h = canvas.get_width_height()
            qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)
            
            # Scale to fit label
            scaled = pixmap.scaled(self.width(), self.height(),
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled)
            
        except Exception as e:
            self.setText(f"Error:\\n{str(e)[:30]}")
    
    def clear(self):
        """Clear depth map display."""
        self.clear()
        self.setText("Depth Map\\n(Toggle to show)")
'''

DEPTH_TIME_PLOT_CLASS = '''
class DepthTimePlot(QLabel):
    """Line chart showing depth over last 60 frames."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.depth_history = deque(maxlen=60)
        self.setMinimumSize(400, 200)
        self.setMaximumSize(600, 250)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #000; border: 2px solid #444;")
        self.clear_plot()
    
    def update_plot(self, depth: float):
        """Add new depth value and redraw plot."""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        try:
            # Add to history (use NaN if invalid)
            self.depth_history.append(depth if depth > 0 else np.nan)
            
            # Create figure
            fig = Figure(figsize=(5, 2.5), dpi=100)
            fig.patch.set_facecolor('#1e1e1e')
            ax = fig.add_subplot(111)
            
            # Plot data
            x = list(range(len(self.depth_history)))
            y = list(self.depth_history)
            
            # Only plot valid data
            valid_idx = [i for i, val in enumerate(y) if not np.isnan(val)]
            if valid_idx:
                valid_x = [x[i] for i in valid_idx]
                valid_y = [y[i] for i in valid_idx]
                
                ax.plot(valid_x, valid_y, 'cyan', linewidth=2, marker='o', 
                       markersize=3, label='Depth')
                ax.fill_between(valid_x, 0, valid_y, alpha=0.2, color='cyan')
            
            ax.set_xlabel('Frame (last 60)', color='white', fontsize=9)
            ax.set_ylabel('Depth (m)', color='white', fontsize=9)
            ax.set_title('Depth Over Time', color='white', fontsize=10, 
                        fontweight='bold')
            ax.grid(True, alpha=0.3, color='gray')
            ax.set_facecolor('#2e2e2e')
            ax.tick_params(colors='white', labelsize=8)
            ax.spines['bottom'].set_color('white')
            ax.spines['top'].set_color('white')
            ax.spines['left'].set_color('white')
            ax.spines['right'].set_color('white')
            
            # Set y-axis limits
            if valid_idx:
                ymax = max(valid_y)
                ax.set_ylim(0, min(ymax * 1.2, 45))
            else:
                ax.set_ylim(0, 40)
            
            fig.tight_layout()
            
            # Render to QPixmap
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            buf = canvas.buffer_rgba()
            w, h = canvas.get_width_height()
            qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)
            
            # Scale to fit
            scaled = pixmap.scaled(self.width(), self.height(),
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled)
            
        except Exception as e:
            self.setText(f"Plot Error: {str(e)[:40]}")
    
    def clear_plot(self):
        """Clear all data and reset plot."""
        self.depth_history.clear()
        self.clear()
        self.setText("Depth Over Time\\n(60-frame window)")
        self.setStyleSheet("color: #666; background-color: #000; border: 2px solid #444;")
'''

# ============================================================================
# STEP 3: Enhanced Worker Signal
# ============================================================================

ENHANCED_SIGNAL = '''
class SVOScenarioWorker(QThread):
    """Background worker for SVO2 pipeline benchmark."""
    
    loading_progress = Signal(int, str)
    loading_complete = Signal()
    loading_failed = Signal(str)
    
    # Enhanced progress signal with component breakdown and depth data
    progress_updated = Signal(
        int,    # current frame
        int,    # total frames
        str,    # status
        float,  # fps
        int,    # num_objects
        float,  # mean_depth
        dict,   # component_percentages: {'grab': float, 'inference': float, 'depth': float}
        object  # depth_data: {'depth_array': np.ndarray, 'bbox': tuple} or None
    )
    
    frame_processed = Signal(object)
    benchmark_complete = Signal(str, float, dict)
    benchmark_failed = Signal(str)
    start_processing = Signal()
    
    def __init__(self, ...):
        super().__init__()
        ...
        self._paused = False
        self.timing_windows = {
            'grab': deque(maxlen=60),
            'inference': deque(maxlen=60),
            'depth': deque(maxlen=60)
        }
'''

# ============================================================================
# STEP 4: GUI Enhancements (Add to _build_ui)
# ============================================================================

GUI_ADDITIONS = '''
# In statistics panel, add component breakdown
component_group = QGroupBox("Component Breakdown")
component_layout = QVBoxLayout()

self.grab_pct_label = QLabel("Grab: -- %")
self.grab_pct_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #FF5722;")
component_layout.addWidget(self.grab_pct_label)

self.inference_pct_label = QLabel("Inference: -- %")
self.inference_pct_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #2196F3;")
component_layout.addWidget(self.inference_pct_label)

self.depth_pct_label = QLabel("Depth: -- %")
self.depth_pct_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #4CAF50;")
component_layout.addWidget(self.depth_pct_label)

component_group.setLayout(component_layout)
stats_layout.addWidget(component_group)

# Add toggle for depth map
self.toggle_depthmap_btn = QPushButton("Show Depth Map")
self.toggle_depthmap_btn.setCheckable(True)
self.toggle_depthmap_btn.setChecked(False)
self.toggle_depthmap_btn.toggled.connect(self._on_depthmap_toggled)
right_layout.addWidget(self.toggle_depthmap_btn)

# Add depth map viewer
self.depth_map_viewer = DepthMapViewer()
self.depth_map_viewer.setVisible(False)
right_layout.addWidget(self.depth_map_viewer)

# Add depth time plot
self.depth_time_plot = DepthTimePlot()
right_layout.addWidget(self.depth_time_plot)

# Add pause/stop buttons
control_buttons = QHBoxLayout()

self.pause_btn = QPushButton("⏸ Pause")
self.pause_btn.setStyleSheet("background-color: #FF9800; color: white; padding: 8px;")
self.pause_btn.setEnabled(False)
self.pause_btn.clicked.connect(self._toggle_pause)
control_buttons.addWidget(self.pause_btn)

self.stop_btn = QPushButton("⏹ Stop")
self.stop_btn.setStyleSheet("background-color: #F44336; color: white; padding: 8px;")
self.stop_btn.setEnabled(False)
self.stop_btn.clicked.connect(self._stop_benchmark)
control_buttons.addWidget(self.stop_btn)

left_layout.addLayout(control_buttons)
'''

print("Enhanced GUI Implementation Reference Created!")
print("See: docs/ENHANCED_GUI_IMPLEMENTATION.md for full implementation plan")
print("")
print("Due to file complexity (1700+ lines), I recommend:")
print("1. Review the implementation plan")
print("2. Apply changes incrementally")
print("3. Test each feature before adding the next")
print("")
print("Key files to modify:")
print("- src/svo_handler/jetson_benchmark_app.py (main GUI)")
print("- src/svo_handler/benchmark_scenarios.py (timing tracking)")
