#!/usr/bin/env python3
"""
Jetson Benchmark Application for YOLO model validation.

Workflow:
1. Select TensorRT engine file
2. Choose scenario: Pure Inference OR SVO2 Pipeline
3. Run benchmark on images/SVO2 file
4. Manual validation: review detections, mark correct/missed/false
5. Generate statistics report

Supports multiple benchmark scenarios:
- Pure Inference: TensorRT on pre-loaded images (baseline)
- SVO2 Pipeline: Full pipeline with depth extraction (NEURAL_PLUS)
"""

import sys
import json
import shutil
import time
import random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit,
    QGroupBox, QMessageBox, QProgressDialog, QScrollArea, QSpinBox, QCheckBox,
    QStackedWidget, QComboBox, QProgressBar, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QPen, QColor, QBrush

# Matplotlib for depth plot
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, depth plot disabled")


class DepthPlotCanvas(FigureCanvasQTAgg if MATPLOTLIB_AVAILABLE else QWidget):
    """Canvas for plotting depth over time."""
    
    def __init__(self, parent=None):
        if MATPLOTLIB_AVAILABLE:
            self.fig = Figure(figsize=(5, 3), dpi=100)
            self.fig.patch.set_facecolor('#f0f0f0')
            super().__init__(self.fig)
            self.axes = self.fig.add_subplot(111)
            self.axes.set_facecolor('#ffffff')
            self.axes.set_xlabel('Frame', fontsize=9)
            self.axes.set_ylabel('Depth (m)', fontsize=9)
            self.axes.set_title('Mean Depth (Last 30 Frames)', fontsize=10)
            self.axes.grid(True, alpha=0.3)
            self.axes.tick_params(labelsize=8)
            self.fig.tight_layout()
            
            self.depth_data = []
            self.max_points = 30
        else:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            label = QLabel("Matplotlib not available")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
    
    def update_plot(self, depth_value: float):
        """Update plot with new depth value."""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        self.depth_data.append(depth_value if depth_value > 0 else 0)
        if len(self.depth_data) > self.max_points:
            self.depth_data.pop(0)
        
        self.axes.clear()
        self.axes.set_facecolor('#ffffff')
        self.axes.set_xlabel('Frame', fontsize=9)
        self.axes.set_ylabel('Depth (m)', fontsize=9)
        self.axes.set_title('Mean Depth (Last 30 Frames)', fontsize=10, fontweight='bold')
        self.axes.grid(True, alpha=0.3)
        self.axes.tick_params(labelsize=8)
        
        if self.depth_data:
            x = list(range(len(self.depth_data)))
            self.axes.plot(x, self.depth_data, 'b-', linewidth=2, marker='o', markersize=4)
            self.axes.fill_between(x, 0, self.depth_data, alpha=0.3)
            
            # Set y-axis limits
            max_depth = max(self.depth_data) if self.depth_data else 40
            self.axes.set_ylim(0, min(max_depth * 1.2, 45))
        
        self.fig.tight_layout()
        self.draw()
    
    def clear_plot(self):
        """Clear all data."""
        if MATPLOTLIB_AVAILABLE:
            self.depth_data = []
            self.axes.clear()
            self.axes.set_xlabel('Frame', fontsize=9)
            self.axes.set_ylabel('Depth (m)', fontsize=9)
            self.axes.set_title('Mean Depth (Last 30 Frames)', fontsize=10)
            self.axes.grid(True, alpha=0.3)
            self.fig.tight_layout()
            self.draw()


@dataclass
class DetectionResult:
    """Single object detection result."""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x_center, y_center, width, height (normalized)


@dataclass
class ImageResult:
    """Results for a single image."""
    image_path: str
    detections: List[DetectionResult]
    inference_time_ms: float


class InferenceWorker(QThread):
    """Background worker for running inference on test images."""
    
    progress_updated = Signal(int, int, str, float)  # current, total, image_name, fps
    inference_complete = Signal(str, float, dict)  # run_folder, total_time, stats
    inference_failed = Signal(str)  # error_message
    
    def __init__(self, engine_path: Path, test_folder: Path, output_folder: Path, 
                 conf_threshold: float = 0.25, max_images: Optional[int] = None):
        super().__init__()
        self.engine_path = engine_path
        self.test_folder = test_folder
        self.output_folder = output_folder
        self.conf_threshold = conf_threshold
        self.max_images = max_images
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the worker."""
        self._cancelled = True
    
    def run(self):
        """Run inference on all test images."""
        try:
            from ultralytics import YOLO
            import cv2
            
            # Load model
            model = YOLO(str(self.engine_path))
            
            # Get list of images
            image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
                image_files.extend(self.test_folder.glob(ext))
            
            if not image_files:
                self.inference_failed.emit(f"No images found in {self.test_folder}")
                return
            
            # Shuffle images for random sampling
            random.shuffle(image_files)
            
            # Limit to max_images if specified
            if self.max_images:
                image_files = image_files[:self.max_images]
            
            total = len(image_files)
            
            # Create output subdirectories
            images_dir = self.output_folder / "images"
            labels_dir = self.output_folder / "labels"
            images_dir.mkdir(exist_ok=True)
            labels_dir.mkdir(exist_ok=True)
            
            # Track statistics
            detection_counts = []
            start_time = time.time()
            
            # Process each image
            for idx, img_path in enumerate(image_files):
                if self._cancelled:
                    self.inference_failed.emit("Cancelled by user")
                    return
                
                # Copy image (NEVER modifies source!)
                # Source file is READ-ONLY in this operation
                dest_image = images_dir / img_path.name
                shutil.copy2(img_path, dest_image)
                
                # Paranoid check: Verify source file still exists
                if not img_path.exists():
                    self.inference_failed.emit(f"Source file disappeared: {img_path}")
                    return
                
                # Run inference
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                
                results = model(img, conf=self.conf_threshold, verbose=False)
                
                # Save detections in YOLO format
                label_file = labels_dir / f"{img_path.stem}.txt"
                detections = results[0].boxes
                num_detections = len(detections)
                detection_counts.append(num_detections)
                
                with open(label_file, 'w') as f:
                    for box in detections:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        # Convert to YOLO format (x_center, y_center, width, height - normalized)
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        h, w = img.shape[:2]
                        x_center = ((x1 + x2) / 2) / w
                        y_center = ((y1 + y2) / 2) / h
                        width = (x2 - x1) / w
                        height = (y2 - y1) / h
                        f.write(f"{cls} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f} {conf:.6f}\n")
                
                # Calculate current FPS
                elapsed_so_far = time.time() - start_time
                current_fps = (idx + 1) / elapsed_so_far if elapsed_so_far > 0 else 0
                
                # Emit progress
                self.progress_updated.emit(idx + 1, total, img_path.name, current_fps)
            
            total_time = time.time() - start_time
            
            # Calculate statistics
            total_detections = sum(detection_counts)
            images_with_detections = sum(1 for count in detection_counts if count > 0)
            images_empty = len(detection_counts) - images_with_detections
            avg_detections = total_detections / len(detection_counts) if detection_counts else 0
            
            stats = {
                'total_images': len(image_files),
                'total_time_seconds': total_time,
                'mean_fps': len(image_files) / total_time if total_time > 0 else 0,
                'mean_latency_ms': (total_time / len(image_files)) * 1000 if image_files else 0,
                'total_detections': total_detections,
                'images_with_detections': images_with_detections,
                'images_empty': images_empty,
                'avg_detections_per_image': avg_detections,
                'conf_threshold': self.conf_threshold,
                'engine_path': str(self.engine_path),
                'test_folder': str(self.test_folder)
            }
            
            # Save statistics
            stats_file = self.output_folder / "inference_stats.json"
            with open(stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
            
            self.inference_complete.emit(str(self.output_folder), total_time, stats)
            
        except Exception as e:
            self.inference_failed.emit(f"Error during inference: {str(e)}")


class SVOScenarioWorker(QThread):
    """Background worker for SVO2 pipeline benchmark."""
    
    loading_progress = Signal(int, str)  # progress %, message
    loading_complete = Signal()  # SVO loaded and ready
    loading_failed = Signal(str)  # error message
    
    progress_updated = Signal(int, int, str, float, int, float)  # current, total, status, fps, num_objects, mean_depth
    frame_processed = Signal(object)  # preview image (numpy RGB array)
    benchmark_complete = Signal(str, float, dict)  # run_folder, total_time, stats
    benchmark_failed = Signal(str)  # error message
    
    start_processing = Signal()  # Internal signal to start processing phase
    
    def __init__(self, engine_path: Path, svo_path: Path, output_folder: Path,
                 conf_threshold: float = 0.25, save_images: bool = False):
        super().__init__()
        self.engine_path = engine_path
        self.svo_path = svo_path
        self.output_folder = output_folder
        self.conf_threshold = conf_threshold
        self.save_images = save_images
        self._cancelled = False
        self._start_benchmark = False  # Flag to start benchmark phase
        self.scenario = None
        
        # Connect internal signal
        self.start_processing.connect(self._set_start_flag)
    
    def cancel(self):
        """Request cancellation of the worker."""
        self._cancelled = True
    
    def _set_start_flag(self):
        """Set flag to start benchmark processing."""
        self._start_benchmark = True
    
    def run(self):
        """Run SVO2 pipeline benchmark."""
        try:
            from svo_handler.benchmark_scenarios import SVOPipelineScenario
            import numpy as np
            
            # Phase 1: Loading (this is what takes 30-60s)
            def loading_callback(progress: int, message: str):
                if self._cancelled:
                    return
                self.loading_progress.emit(progress, message)
            
            def preview_callback(img_rgb: np.ndarray):
                if self._cancelled:
                    return
                self.frame_processed.emit(img_rgb)
            
            # Create and setup scenario
            self.scenario = SVOPipelineScenario()
            
            config = {
                'svo_path': str(self.svo_path),
                'model_path': str(self.engine_path),
                'conf_threshold': self.conf_threshold,
                'save_images': self.save_images,
                'output_dir': str(self.output_folder / "frames") if self.save_images else None,
                'loading_progress_callback': loading_callback,
                'preview_callback': preview_callback if self.save_images else None
            }
            
            if not self.scenario.setup(config):
                self.loading_failed.emit("Failed to initialize SVO2 pipeline")
                return
            
            if self._cancelled:
                self.scenario.cleanup()
                return
            
            # Loading complete!
            self.loading_complete.emit()
            
            # Phase 2: Wait for start signal
            while not self._start_benchmark and not self._cancelled:
                self.msleep(100)  # Wait 100ms
            
            if self._cancelled:
                self.scenario.cleanup()
                return
            
            # Phase 3: Run benchmark
            self._run_benchmark_internal()
            
        except Exception as e:
            import traceback
            error_msg = f"Error during SVO benchmark: {str(e)}\n{traceback.format_exc()}"
            self.benchmark_failed.emit(error_msg)
            if self.scenario:
                self.scenario.cleanup()
    
    def _run_benchmark_internal(self):
        """Run the actual benchmark (internal, runs in worker thread)."""
        try:
            if not self.scenario:
                self.benchmark_failed.emit("Scenario not ready")
                return
            
            start_time = time.time()
            total_frames = self.scenario.total_frames
            frames_processed = 0
            detection_counts = []
            all_timings = {'grab': [], 'inference': [], 'depth': []}
            if self.save_images:
                all_timings['save'] = []
            
            # Process entire SVO file
            while not self._cancelled:
                frame_start = time.time()
                
                # Run frame processing
                result = self.scenario.run_frame(None)
                
                # Check for completion
                if result is None:
                    break  # End of SVO
                
                # Skip corrupted frames
                if result.get('skipped'):
                    continue
                
                frames_processed += 1
                detections = result.get('detections', [])
                detection_counts.append(len(detections))
                
                # Get mean depth from detections
                depths = [d.get('depth_mean', -1) for d in detections if d.get('depth_mean', -1) > 0]
                mean_depth = sum(depths) / len(depths) if depths else -1.0
                
                # Accumulate timings
                for key, value in result.get('timings', {}).items():
                    if key in all_timings:
                        all_timings[key].append(value)
                
                # Calculate FPS
                frame_time = time.time() - frame_start
                fps = 1.0 / frame_time if frame_time > 0 else 0
                
                # Update progress with detection info
                status = f"Frame {frames_processed}/{total_frames}"
                self.progress_updated.emit(frames_processed, total_frames, status, fps, len(detections), mean_depth)
            
            if self._cancelled:
                self.scenario.cleanup()
                return
            
            total_time = time.time() - start_time
            
            # Calculate statistics
            total_detections = sum(detection_counts)
            frames_with_detections = sum(1 for count in detection_counts if count > 0)
            frames_empty = len(detection_counts) - frames_with_detections
            
            # Component timing averages
            component_times = {
                key: sum(times) / len(times) if times else 0.0
                for key, times in all_timings.items()
            }
            
            stats = {
                'scenario': 'SVO2 Pipeline',
                'total_frames': frames_processed,
                'total_time_seconds': total_time,
                'mean_fps': frames_processed / total_time if total_time > 0 else 0,
                'mean_latency_ms': (total_time / frames_processed) * 1000 if frames_processed > 0 else 0,
                'component_times_ms': component_times,
                'total_detections': total_detections,
                'frames_with_detections': frames_with_detections,
                'frames_empty': frames_empty,
                'avg_detections_per_frame': total_detections / frames_processed if frames_processed > 0 else 0,
                'conf_threshold': self.conf_threshold,
                'engine_path': str(self.engine_path),
                'svo_path': str(self.svo_path),
                'images_saved': self.save_images
            }
            
            # Save statistics
            stats_file = self.output_folder / "benchmark_stats.json"
            with open(stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
            
            self.scenario.cleanup()
            self.benchmark_complete.emit(str(self.output_folder), total_time, stats)
            
        except Exception as e:
            import traceback
            error_msg = f"Error during benchmark: {str(e)}\n{traceback.format_exc()}"
            self.benchmark_failed.emit(error_msg)
            if self.scenario:
                self.scenario.cleanup()


class ValidationViewer(QWidget):
    """Widget for manually validating inference results."""
    
    validation_complete = Signal()
    
    def __init__(self, run_folder: Path, parent=None):
        super().__init__(parent)
        self.run_folder = run_folder
        self.images_dir = run_folder / "images"
        self.labels_dir = run_folder / "labels"
        
        # Load image list
        self.image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
            self.image_files.extend(self.images_dir.glob(ext))
        self.image_files.sort()
        
        # Check if we have images
        if not self.image_files:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self, 
                "No Images Found",
                f"No images found in:\n{self.images_dir}\n\nThe inference run may have failed."
            )
            raise ValueError("No images found for validation")
        
        self.current_index = 0
        
        # Load existing validations if any
        self.validations_file = run_folder / "validations.json"
        self.validations = {}
        if self.validations_file.exists():
            with open(self.validations_file, 'r') as f:
                loaded = json.load(f)
                # Ensure it's a dict (in case of corrupted/old format)
                if isinstance(loaded, dict):
                    self.validations = loaded
                else:
                    self.validations = {}
        
        # Validation status options
        # 'correct': Perfect detection
        # 'correct_plus_false': Correct detection but also has false positives
        # 'missed': Target present but not detected
        # 'false': Only false positives (no correct detection)
        # 'pending': Not yet validated
        
        self._build_ui()
        self._load_image()
    
    def _build_ui(self):
        """Build the validation UI."""
        layout = QVBoxLayout(self)
        
        # Info bar
        info_layout = QHBoxLayout()
        self.counter_label = QLabel()
        self.counter_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        info_layout.addWidget(self.counter_label)
        info_layout.addStretch()
        self.filename_label = QLabel()
        self.filename_label.setFont(QFont("Arial", 10))
        info_layout.addWidget(self.filename_label)
        layout.addLayout(info_layout)
        
        # Image viewer
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(600)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self.image_label)
        layout.addWidget(scroll)
        
        # Validation buttons
        btn_layout = QHBoxLayout()
        
        self.correct_btn = QPushButton("✓ Correct Detection")
        self.correct_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 14px; padding: 10px;")
        self.correct_btn.clicked.connect(lambda: self._mark_validation('correct'))
        btn_layout.addWidget(self.correct_btn)
        
        self.correct_false_btn = QPushButton("✓+ Correct + False Positive")
        self.correct_false_btn.setStyleSheet("background-color: #8BC34A; color: white; font-size: 14px; padding: 10px;")
        self.correct_false_btn.clicked.connect(lambda: self._mark_validation('correct_plus_false'))
        btn_layout.addWidget(self.correct_false_btn)
        
        self.missed_btn = QPushButton("✗ Missed Detection")
        self.missed_btn.setStyleSheet("background-color: #FF9800; color: white; font-size: 14px; padding: 10px;")
        self.missed_btn.clicked.connect(lambda: self._mark_validation('missed'))
        btn_layout.addWidget(self.missed_btn)
        
        self.false_btn = QPushButton("⚠ False Detection")
        self.false_btn.setStyleSheet("background-color: #F44336; color: white; font-size: 14px; padding: 10px;")
        self.false_btn.clicked.connect(lambda: self._mark_validation('false'))
        btn_layout.addWidget(self.false_btn)
        
        layout.addLayout(btn_layout)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setFont(QFont("Arial", 12))
        self.prev_btn.clicked.connect(self._prev_image)
        nav_layout.addWidget(self.prev_btn)
        
        nav_layout.addStretch()
        
        self.next_btn = QPushButton("Next →")
        self.next_btn.setFont(QFont("Arial", 12))
        self.next_btn.clicked.connect(self._next_image)
        nav_layout.addWidget(self.next_btn)
        
        layout.addLayout(nav_layout)
        
        # Finish button
        finish_btn = QPushButton("Finish Validation & Generate Report")
        finish_btn.setStyleSheet("background-color: #2196F3; color: white; font-size: 14px; padding: 15px;")
        finish_btn.clicked.connect(self._finish_validation)
        layout.addWidget(finish_btn)
    
    def _load_image(self):
        """Load and display current image with detections."""
        if not self.image_files:
            return
        
        img_path = self.image_files[self.current_index]
        label_path = self.labels_dir / f"{img_path.stem}.txt"
        
        # Update info
        self.counter_label.setText(f"Image {self.current_index + 1} / {len(self.image_files)}")
        self.filename_label.setText(img_path.name)
        
        # Load image
        pixmap = QPixmap(str(img_path))
        
        # Load detections and draw boxes
        if label_path.exists():
            painter = QPainter(pixmap)
            
            # Get current validation status for color
            img_name = img_path.name
            status = self.validations.get(img_name, 'pending')
            
            # Color based on status
            color_map = {
                'correct': QColor(76, 175, 80),  # Green
                'correct_plus_false': QColor(139, 195, 74),  # Light green
                'missed': QColor(255, 152, 0),  # Orange
                'false': QColor(244, 67, 54),  # Red
                'pending': QColor(33, 150, 243)  # Blue
            }
            color = color_map.get(status, QColor(33, 150, 243))
            
            pen = QPen(color, 3)
            painter.setPen(pen)
            
            img_w = pixmap.width()
            img_h = pixmap.height()
            
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    
                    cls_id = int(parts[0])
                    x_center = float(parts[1]) * img_w
                    y_center = float(parts[2]) * img_h
                    width = float(parts[3]) * img_w
                    height = float(parts[4]) * img_h
                    conf = float(parts[5]) if len(parts) > 5 else 0.0
                    
                    x1 = int(x_center - width / 2)
                    y1 = int(y_center - height / 2)
                    x2 = int(x_center + width / 2)
                    y2 = int(y_center + height / 2)
                    
                    painter.drawRect(x1, y1, x2 - x1, y2 - y1)
                    
                    # Draw label
                    class_names = ['target_close', 'target_far']
                    label = f"{class_names[cls_id] if cls_id < len(class_names) else f'class_{cls_id}'} {conf:.2f}"
                    painter.drawText(x1, y1 - 5, label)
            
            painter.end()
        
        # Scale image to fit window while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(1400, 800, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        
        # Update button states
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.image_files) - 1)
    
    def _mark_validation(self, status: str):
        """Mark current image with validation status."""
        img_name = self.image_files[self.current_index].name
        self.validations[img_name] = status
        
        # Save validations
        with open(self.validations_file, 'w') as f:
            json.dump(self.validations, f, indent=2)
        
        # Reload to update color
        self._load_image()
        
        # Auto-advance to next image
        if self.current_index < len(self.image_files) - 1:
            self._next_image()
    
    def _prev_image(self):
        """Go to previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            self._load_image()
    
    def _next_image(self):
        """Go to next image."""
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self._load_image()
    
    def _finish_validation(self):
        """Generate final report and close."""
        # Check if all images validated
        unvalidated = []
        for img_file in self.image_files:
            if img_file.name not in self.validations:
                unvalidated.append(img_file.name)
        
        if unvalidated:
            reply = QMessageBox.question(
                self,
                "Incomplete Validation",
                f"{len(unvalidated)} images not yet validated.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Generate report
        report_data = self._generate_report()
        
        # Show detailed summary
        self._show_summary_dialog(report_data)
        
        self.validation_complete.emit()
    
    def _generate_report(self):
        """Generate validation statistics report."""
        total = len(self.image_files)
        
        # Count each status
        status_counts = {
            'correct': 0,
            'correct_plus_false': 0,
            'missed': 0,
            'false': 0,
            'pending': 0
        }
        
        for img_file in self.image_files:
            status = self.validations.get(img_file.name, 'pending')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate success rate (correct + correct_plus_false)
        successful = status_counts['correct'] + status_counts['correct_plus_false']
        success_rate = (successful / total * 100) if total > 0 else 0
        
        # Load inference stats if available
        stats_file = self.run_folder / "inference_stats.json"
        inference_stats = {}
        if stats_file.exists():
            with open(stats_file, 'r') as f:
                inference_stats = json.load(f)
        
        # Create report
        report = {
            'run_folder': str(self.run_folder),
            'timestamp': datetime.now().isoformat(),
            'total_images': total,
            'validated_images': total - status_counts['pending'],
            'validation_status_counts': status_counts,
            'success_rate_percent': round(success_rate, 2),
            'inference_stats': inference_stats
        }
        
        # Save JSON report
        report_file = self.run_folder / "validation_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Save human-readable summary
        summary_file = self.run_folder / "validation_summary.txt"
        with open(summary_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("VALIDATION SUMMARY\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Run Folder: {self.run_folder}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total Images: {total}\n")
            f.write(f"Validated: {total - status_counts['pending']}\n")
            f.write(f"Pending: {status_counts['pending']}\n\n")
            f.write("-" * 70 + "\n")
            f.write("VALIDATION RESULTS\n")
            f.write("-" * 70 + "\n")
            f.write(f"✓ Correct Detections: {status_counts['correct']}\n")
            f.write(f"✓+ Correct + False Positives: {status_counts['correct_plus_false']}\n")
            f.write(f"✗ Missed Detections: {status_counts['missed']}\n")
            f.write(f"⚠ False Detections Only: {status_counts['false']}\n\n")
            f.write(f"Overall Success Rate: {success_rate:.2f}%\n")
            f.write(f"  (Correct + Correct w/ False Positives)\n\n")
            
            if inference_stats:
                f.write("-" * 70 + "\n")
                f.write("INFERENCE PERFORMANCE\n")
                f.write("-" * 70 + "\n")
                f.write(f"Mean FPS: {inference_stats.get('mean_fps', 0):.2f}\n")
                f.write(f"Mean Latency: {inference_stats.get('mean_latency_ms', 0):.2f} ms\n")
                f.write(f"Total Detections: {inference_stats.get('total_detections', 0)}\n")
                f.write(f"Images with Detections: {inference_stats.get('images_with_detections', 0)}\n")
                f.write(f"Images Empty: {inference_stats.get('images_empty', 0)}\n")
                f.write(f"Avg Detections per Image: {inference_stats.get('avg_detections_per_image', 0):.2f}\n\n")
            
            f.write("=" * 70 + "\n")
        
        # Return report data for summary dialog
        return report
    
    def _show_summary_dialog(self, report: dict):
        """Show detailed summary dialog after validation."""
        status_counts = report['validation_status_counts']
        success_rate = report['success_rate_percent']
        total = report['total_images']
        inference_stats = report.get('inference_stats', {})
        
        # Build summary message
        summary = "=" * 60 + "\n"
        summary += "📊 VALIDATION SUMMARY\n"
        summary += "=" * 60 + "\n\n"
        
        summary += f"✅ Overall Success Rate: {success_rate:.1f}%\n"
        summary += f"   ({status_counts['correct'] + status_counts['correct_plus_false']} of {total} images)\n\n"
        
        summary += "VALIDATION BREAKDOWN:\n"
        summary += f"  ✓  Perfect Detections:      {status_counts['correct']:>3} ({status_counts['correct']/total*100:.1f}%)\n"
        summary += f"  ✓+ Correct + False Pos:     {status_counts['correct_plus_false']:>3} ({status_counts['correct_plus_false']/total*100:.1f}%)\n"
        summary += f"  ✗  Missed Detections:       {status_counts['missed']:>3} ({status_counts['missed']/total*100:.1f}%)\n"
        summary += f"  ⚠  False Detections Only:   {status_counts['false']:>3} ({status_counts['false']/total*100:.1f}%)\n"
        
        if status_counts['pending'] > 0:
            summary += f"  ⏸  Pending (not validated): {status_counts['pending']:>3}\n"
        
        if inference_stats:
            summary += "\n" + "-" * 60 + "\n"
            summary += "⚡ PERFORMANCE METRICS:\n"
            summary += f"  Mean FPS:            {inference_stats.get('mean_fps', 0):.2f}\n"
            summary += f"  Mean Latency:        {inference_stats.get('mean_latency_ms', 0):.2f} ms\n"
            summary += f"  Total Detections:    {inference_stats.get('total_detections', 0)}\n"
            summary += f"  Images w/ Objects:   {inference_stats.get('images_with_detections', 0)}\n"
            summary += f"  Images Empty:        {inference_stats.get('images_empty', 0)}\n"
        
        summary += "\n" + "=" * 60 + "\n"
        summary += f"📁 Reports saved to:\n   {self.run_folder}\n"
        summary += "=" * 60
        
        # Show in dialog with monospace font for alignment
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Validation Complete ✅")
        msg_box.setText("Validation completed successfully!")
        msg_box.setDetailedText(summary)
        msg_box.setIcon(QMessageBox.Icon.Information)
        
        # Set monospace font for detailed text
        font = QFont("Courier New", 9)
        for button in msg_box.buttons():
            button.setFont(QFont("Arial", 10))
        
        msg_box.exec()


class JetsonBenchmarkApp(QMainWindow):
    """Main application window for Jetson benchmarking."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jetson YOLO Benchmark & Validation")
        self.resize(900, 700)
        
        self.worker = None
        self.validation_viewer = None
        
        # Use stacked widget to switch between views
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the main UI with side-by-side layout."""
        # Create main widget
        self.main_widget = QWidget()
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Add to stacked widget
        self.stacked_widget.addWidget(self.main_widget)
        
        # Title
        title = QLabel("Jetson YOLO Benchmark & Validation Tool")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        # Main horizontal split: Left (Controls) | Right (Preview + Stats)
        content_layout = QHBoxLayout()
        
        # ===== LEFT SIDE: Controls =====
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_widget.setMaximumWidth(500)
        
        # Scenario selection
        scenario_group = QGroupBox("1. Benchmark Scenario")
        scenario_layout = QVBoxLayout()
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems([
            "Pure Inference (Images)",
            "SVO2 Pipeline (with Depth)"
        ])
        self.scenario_combo.currentIndexChanged.connect(self._on_scenario_changed)
        scenario_layout.addWidget(self.scenario_combo)
        scenario_group.setLayout(scenario_layout)
        left_layout.addWidget(scenario_group)
        
        # Engine file selection
        engine_group = QGroupBox("2. TensorRT Engine")
        engine_layout = QHBoxLayout()
        self.engine_edit = QLineEdit()
        self.engine_edit.setPlaceholderText("Path to .engine file...")
        engine_browse_btn = QPushButton("Browse")
        engine_browse_btn.clicked.connect(self._browse_engine)
        engine_browse_btn.setMaximumWidth(80)
        engine_layout.addWidget(self.engine_edit)
        engine_layout.addWidget(engine_browse_btn)
        engine_group.setLayout(engine_layout)
        left_layout.addWidget(engine_group)
        
        # Input selection
        self.test_group = QGroupBox("3. Input File/Folder")
        test_layout = QVBoxLayout()
        input_layout = QHBoxLayout()
        self.test_folder_edit = QLineEdit()
        self.test_folder_edit.textChanged.connect(self._on_folder_changed)
        self.test_browse_btn = QPushButton("Browse")
        self.test_browse_btn.clicked.connect(self._browse_input)
        self.test_browse_btn.setMaximumWidth(80)
        input_layout.addWidget(self.test_folder_edit)
        input_layout.addWidget(self.test_browse_btn)
        test_layout.addLayout(input_layout)
        
        self.image_count_label = QLabel("")
        self.image_count_label.setStyleSheet("color: #2196F3; font-size: 10px;")
        test_layout.addWidget(self.image_count_label)
        
        self.svo_info_label = QLabel("")
        self.svo_info_label.setStyleSheet("color: #2196F3; font-size: 10px;")
        self.svo_info_label.setVisible(False)
        test_layout.addWidget(self.svo_info_label)
        
        self.test_group.setLayout(test_layout)
        left_layout.addWidget(self.test_group)
        
        # Options (conditional based on scenario)
        self.images_group = QGroupBox("4. Options")
        images_layout = QVBoxLayout()
        
        images_control_layout = QHBoxLayout()
        self.max_images_spin = QSpinBox()
        self.max_images_spin.setRange(1, 10000)
        self.max_images_spin.setValue(200)
        self.max_images_spin.setSuffix(" images")
        images_control_layout.addWidget(QLabel("Max:"))
        images_control_layout.addWidget(self.max_images_spin)
        
        self.use_all_check = QCheckBox("Use all")
        self.use_all_check.toggled.connect(self._toggle_max_images)
        images_control_layout.addWidget(self.use_all_check)
        images_control_layout.addStretch()
        
        images_layout.addLayout(images_control_layout)
        self.images_group.setLayout(images_layout)
        left_layout.addWidget(self.images_group)
        
        # SVO2 options
        self.svo_options_group = QGroupBox("4. Options")
        svo_options_layout = QVBoxLayout()
        
        self.save_images_check = QCheckBox("Save annotated frames")
        self.save_images_check.setChecked(False)
        self.save_images_check.toggled.connect(self._on_save_images_toggled)
        svo_options_layout.addWidget(self.save_images_check)
        
        self.show_preview_check = QCheckBox("Show live preview")
        self.show_preview_check.setChecked(True)
        self.show_preview_check.setEnabled(False)
        svo_options_layout.addWidget(self.show_preview_check)
        
        self.svo_options_group.setLayout(svo_options_layout)
        self.svo_options_group.setVisible(False)
        left_layout.addWidget(self.svo_options_group)
        
        # Control buttons
        self.run_btn = QPushButton("▶ Run Benchmark")
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 13px; padding: 12px;")
        self.run_btn.clicked.connect(self._run_benchmark)
        left_layout.addWidget(self.run_btn)
        
        self.svo_load_btn = QPushButton("🔄 Initialize SVO2")
        self.svo_load_btn.setStyleSheet("background-color: #2196F3; color: white; font-size: 12px; padding: 10px;")
        self.svo_load_btn.clicked.connect(self._load_svo)
        self.svo_load_btn.setVisible(False)
        left_layout.addWidget(self.svo_load_btn)
        
        self.svo_start_btn = QPushButton("▶ Start Processing")
        self.svo_start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 13px; padding: 12px;")
        self.svo_start_btn.clicked.connect(self._start_svo_processing)
        self.svo_start_btn.setVisible(False)
        self.svo_start_btn.setEnabled(False)
        left_layout.addWidget(self.svo_start_btn)
        
        self.load_prev_btn = QPushButton("📂 Load Previous Run")
        self.load_prev_btn.setStyleSheet("background-color: #757575; color: white; font-size: 11px; padding: 8px;")
        self.load_prev_btn.clicked.connect(self._load_previous_run)
        left_layout.addWidget(self.load_prev_btn)
        
        left_layout.addStretch()
        
        content_layout.addWidget(left_widget)
        
        # ===== RIGHT SIDE: Preview + Statistics =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        
        # Preview window
        preview_group = QGroupBox("Live Preview")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel("No preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 270)
        self.preview_label.setMaximumSize(640, 360)
        self.preview_label.setStyleSheet("background-color: #000; color: #666;")
        self.preview_label.setScaledContents(False)
        preview_layout.addWidget(self.preview_label)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)
        
        # Statistics panel
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()
        
        # Progress bar
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("Progress:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        stats_layout.addLayout(progress_layout)
        
        # Metrics in grid
        metrics_layout = QHBoxLayout()
        
        # Column 1
        col1_layout = QVBoxLayout()
        self.fps_label = QLabel("FPS: --")
        self.fps_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        col1_layout.addWidget(self.fps_label)
        
        self.frame_label = QLabel("Frame: -- / --")
        self.frame_label.setStyleSheet("font-size: 11px;")
        col1_layout.addWidget(self.frame_label)
        metrics_layout.addLayout(col1_layout)
        
        # Column 2
        col2_layout = QVBoxLayout()
        self.objects_label = QLabel("Objects: --")
        self.objects_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        col2_layout.addWidget(self.objects_label)
        
        self.depth_label = QLabel("Depth: -- m")
        self.depth_label.setStyleSheet("font-size: 11px;")
        col2_layout.addWidget(self.depth_label)
        metrics_layout.addLayout(col2_layout)
        
        stats_layout.addLayout(metrics_layout)
        
        # Depth plot
        self.depth_plot = DepthPlotCanvas()
        self.depth_plot.setMinimumHeight(200)
        self.depth_plot.setMaximumHeight(250)
        stats_layout.addWidget(self.depth_plot)
        
        stats_group.setLayout(stats_layout)
        right_layout.addWidget(stats_group)
        
        right_layout.addStretch()
        
        content_layout.addWidget(right_widget, stretch=1)
        
        main_layout.addLayout(content_layout)
        
        # Output log at bottom (collapsible)
        output_group = QGroupBox("Console Output")
        output_group.setMaximumHeight(150)
        output_layout = QVBoxLayout()
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(120)
        output_layout.addWidget(self.output_text)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        self.output_text.append("Ready. Select scenario and configure settings.")
        main_layout.addWidget(self.preview_group)
        
        # Output area
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(200)
        output_layout.addWidget(self.output_text)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        self.output_text.append("Ready. Select scenario, engine, and input to begin.")
        
        # Initialize with Pure Inference mode
        self._on_scenario_changed(0)
        
        # Track SVO worker
        self.svo_worker = None
        self.svo_loaded = False
    
    def _on_scenario_changed(self, index: int):
        """Handle scenario selection change."""
        is_svo = (index == 1)  # 0 = Pure Inference, 1 = SVO2 Pipeline
        
        # Update UI labels
        if is_svo:
            self.test_group.setTitle("3. Select SVO2 File")
            self.test_folder_edit.setPlaceholderText("Path to .svo2 file...")
        else:
            self.test_group.setTitle("3. Select Test Images Folder")
            self.test_folder_edit.setPlaceholderText("Path to test images folder...")
        
        # Show/hide appropriate widgets
        self.images_group.setVisible(not is_svo)
        self.svo_options_group.setVisible(is_svo)
        self.image_count_label.setVisible(not is_svo)
        self.svo_info_label.setVisible(is_svo)
        
        # Show/hide appropriate buttons
        self.run_btn.setVisible(not is_svo)
        self.svo_load_btn.setVisible(is_svo)
        self.svo_start_btn.setVisible(is_svo)
        
        # Clear input field when switching
        self.test_folder_edit.clear()
        
        # Reset SVO state
        self.svo_loaded = False
        self.svo_start_btn.setEnabled(False)
    
    def _browse_input(self):
        """Browse for input (folder or SVO file depending on scenario)."""
        is_svo = (self.scenario_combo.currentIndex() == 1)
        
        if is_svo:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select SVO2 File",
                str(Path.home()),
                "SVO2 Files (*.svo2 *.svo)"
            )
            if file_path:
                self.test_folder_edit.setText(file_path)
                self._update_svo_info(Path(file_path))
        else:
            self._browse_test_folder()
    
    def _update_svo_info(self, svo_path: Path):
        """Display info about selected SVO2 file."""
        if svo_path.exists():
            size_mb = svo_path.stat().st_size / (1024 * 1024)
            self.svo_info_label.setText(f"📹 SVO2 file: {svo_path.name} ({size_mb:.1f} MB)")
        else:
            self.svo_info_label.setText("⚠ Invalid SVO2 file")
    
    def _on_save_images_toggled(self, checked: bool):
        """Enable/disable preview option based on save images."""
        self.show_preview_check.setEnabled(checked)
        if checked:
            self.show_preview_check.setChecked(True)
    
    def _load_svo(self):
        """Initialize SVO2 file (loading phase)."""
        engine_path = Path(self.engine_edit.text().strip())
        svo_path = Path(self.test_folder_edit.text().strip())
        
        if not engine_path.exists():
            QMessageBox.warning(self, "Error", "Please select a valid TensorRT engine file")
            return
        
        if not svo_path.exists():
            QMessageBox.warning(self, "Error", "Please select a valid SVO2 file")
            return
        
        # Create benchmark run folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = Path.home() / "jetson_benchmarks" / f"svo_run_{timestamp}"
        run_folder.mkdir(parents=True, exist_ok=True)
        
        self.run_folder = run_folder
        
        self.output_text.append("\n" + "=" * 70)
        self.output_text.append("🎬 SVO2 PIPELINE BENCHMARK")
        self.output_text.append("=" * 70)
        self.output_text.append(f"📹 SVO2 File: {svo_path.name}")
        self.output_text.append(f"🤖 Engine: {engine_path.name}")
        self.output_text.append(f"📁 Output: {run_folder}")
        self.output_text.append("\n⏳ Loading SVO2 file with NEURAL_PLUS depth...")
        self.output_text.append("   This can take 30-60 seconds for initialization...")
        
        # Disable UI during loading
        self.svo_load_btn.setEnabled(False)
        self.svo_start_btn.setEnabled(False)
        
        # Show progress dialog
        self.loading_dialog = QProgressDialog("Initializing SVO2 file...", "Cancel", 0, 100, self)
        self.loading_dialog.setWindowTitle("Loading SVO2")
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.show()
        
        # Create worker
        save_images = self.save_images_check.isChecked()
        self.svo_worker = SVOScenarioWorker(engine_path, svo_path, run_folder, 
                                            conf_threshold=0.25, save_images=save_images)
        self.svo_worker.loading_progress.connect(self._on_svo_loading_progress)
        self.svo_worker.loading_complete.connect(self._on_svo_loading_complete)
        self.svo_worker.loading_failed.connect(self._on_svo_loading_failed)
        self.svo_worker.start()
    
    def _on_svo_loading_progress(self, progress: int, message: str):
        """Handle SVO loading progress."""
        self.loading_dialog.setValue(progress)
        self.loading_dialog.setLabelText(message)
        self.output_text.append(f"   [{progress}%] {message}")
    
    def _on_svo_loading_complete(self):
        """Handle SVO loading completion."""
        self.loading_dialog.close()
        self.svo_loaded = True
        self.svo_start_btn.setEnabled(True)
        
        self.output_text.append("\n✅ SVO2 file loaded successfully!")
        self.output_text.append(f"📊 Total frames: {self.svo_worker.scenario.total_frames}")
        self.output_text.append("\n👉 Click 'Start Processing' to begin benchmark")
        
        QMessageBox.information(
            self,
            "SVO2 Ready",
            f"SVO2 file loaded successfully!\n\n"
            f"Total frames: {self.svo_worker.scenario.total_frames}\n\n"
            f"Click 'Start Processing' to begin the benchmark."
        )
    
    def _on_svo_loading_failed(self, error_msg: str):
        """Handle SVO loading failure."""
        self.loading_dialog.close()
        self.svo_load_btn.setEnabled(True)
        self.output_text.append(f"\n❌ Loading failed: {error_msg}")
        QMessageBox.critical(self, "Loading Failed", f"Failed to load SVO2 file:\n\n{error_msg}")
    
    def _start_svo_processing(self):
        """Start SVO2 processing after loading complete."""
        if not self.svo_loaded or not self.svo_worker:
            QMessageBox.warning(self, "Error", "SVO2 file not loaded")
            return
        
        self.output_text.append("\n🚀 Starting SVO2 processing...")
        
        # Reset statistics
        self.progress_bar.setValue(0)
        self.fps_label.setText("FPS: --")
        self.frame_label.setText("Frame: -- / --")
        self.objects_label.setText("Objects: --")
        self.depth_label.setText("Depth: -- m")
        self.depth_plot.clear_plot()
        
        # Connect preview if enabled
        if self.save_images_check.isChecked() and self.show_preview_check.isChecked():
            self.svo_worker.frame_processed.connect(self._on_frame_preview)
        
        # Disable buttons during processing
        self.svo_start_btn.setEnabled(False)
        self.svo_load_btn.setEnabled(False)
        
        # Connect remaining signals
        self.svo_worker.progress_updated.connect(self._on_svo_progress)
        self.svo_worker.benchmark_complete.connect(self._on_svo_benchmark_complete)
        self.svo_worker.benchmark_failed.connect(self._on_svo_benchmark_failed)
        
        # Emit signal to start benchmark phase in worker thread
        self.svo_worker.start_processing.emit()
    
    def _on_svo_progress(self, current: int, total: int, status: str, fps: float, num_objects: int, mean_depth: float):
        """Handle SVO processing progress with detailed stats."""
        # Update status bar
        self.statusBar().showMessage(f"{status} | FPS: {fps:.1f} | Objects: {num_objects}")
        
        # Update progress bar
        progress_pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress_pct)
        self.progress_bar.setFormat(f"{current}/{total} ({progress_pct}%)")
        
        # Update metrics
        self.fps_label.setText(f"FPS: {fps:.1f}")
        self.frame_label.setText(f"Frame: {current} / {total}")
        self.objects_label.setText(f"Objects: {num_objects}")
        
        if mean_depth > 0:
            self.depth_label.setText(f"Depth: {mean_depth:.2f} m")
            self.depth_plot.update_plot(mean_depth)
        else:
            self.depth_label.setText("Depth: No data")
        
        # Log every 10 frames
        if current % 10 == 0:
            self.output_text.append(f"   {status} | FPS: {fps:.1f} | Obj: {num_objects}")

    
    def _on_frame_preview(self, img_rgb):
        """Update preview with latest processed frame."""
        import numpy as np
        
        # Convert numpy array to QPixmap
        height, width, channel = img_rgb.shape
        bytes_per_line = 3 * width
        q_image = QImage(img_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit preview label while maintaining aspect ratio
        scaled = pixmap.scaled(self.preview_label.width(), self.preview_label.height(), 
                               Qt.AspectRatioMode.KeepAspectRatio, 
                               Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
    
    def _on_svo_benchmark_complete(self, run_folder: str, total_time: float, stats: dict):
        """Handle SVO benchmark completion."""
        self.svo_start_btn.setEnabled(False)
        self.svo_load_btn.setEnabled(True)
        
        self.output_text.append(f"\n✅ Benchmark complete in {total_time:.1f}s")
        self.output_text.append("\n" + "-" * 70)
        self.output_text.append("SVO2 PIPELINE STATISTICS:")
        self.output_text.append(f"  Total Frames: {stats['total_frames']}")
        self.output_text.append(f"  Frames w/ Detections: {stats['frames_with_detections']}")
        self.output_text.append(f"  Frames Empty: {stats['frames_empty']}")
        self.output_text.append(f"  Total Detections: {stats['total_detections']}")
        self.output_text.append(f"  Avg Detections per Frame: {stats['avg_detections_per_frame']:.2f}")
        self.output_text.append(f"  Mean FPS: {stats['mean_fps']:.2f}")
        self.output_text.append(f"  Mean Latency: {stats['mean_latency_ms']:.2f} ms")
        self.output_text.append("\nCOMPONENT TIMING BREAKDOWN:")
        for component, time_ms in stats['component_times_ms'].items():
            self.output_text.append(f"  {component.capitalize()}: {time_ms:.2f} ms")
        self.output_text.append("-" * 70)
        
        if stats.get('images_saved'):
            self.output_text.append(f"💾 Saved frames to: {Path(run_folder) / 'frames'}")
        
        self.statusBar().showMessage(f"Benchmark complete - {stats['mean_fps']:.2f} FPS")
        
        # Show summary
        component_summary = "\n".join([f"  {k}: {v:.2f} ms" for k, v in stats['component_times_ms'].items()])
        QMessageBox.information(
            self,
            "Benchmark Complete",
            f"SVO2 Pipeline benchmark completed!\n\n"
            f"Processed {stats['total_frames']} frames in {total_time:.1f}s\n"
            f"Mean FPS: {stats['mean_fps']:.2f}\n"
            f"Mean Latency: {stats['mean_latency_ms']:.2f} ms\n\n"
            f"Component Breakdown:\n{component_summary}"
        )
    
    def _on_svo_benchmark_failed(self, error_msg: str):
        """Handle SVO benchmark failure."""
        self.svo_start_btn.setEnabled(True)
        self.svo_load_btn.setEnabled(True)
        self.output_text.append(f"\n❌ Benchmark failed: {error_msg}")
        self.statusBar().showMessage("Benchmark failed")
        QMessageBox.critical(self, "Benchmark Failed", error_msg)
    
    def _run_benchmark(self):
        """Dispatch to appropriate benchmark method based on scenario."""
        is_svo = (self.scenario_combo.currentIndex() == 1)
        
        if is_svo:
            self._load_svo()
        else:
            self._run_inference()
    
    def _browse_engine(self):
        """Browse for TensorRT engine file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TensorRT Engine",
            str(Path.home()),
            "TensorRT Engine (*.engine)"
        )
        if file_path:
            self.engine_edit.setText(file_path)
    
    def _browse_test_folder(self):
        """Browse for test images folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Test Images Folder",
            str(Path.home())
        )
        if folder_path:
            self.test_folder_edit.setText(folder_path)
    
    def _on_folder_changed(self):
        """Called when test folder path changes."""
        folder_text = self.test_folder_edit.text().strip()
        if folder_text and Path(folder_text).exists():
            self._update_image_count(Path(folder_text))
        else:
            self.image_count_label.setText("")
    
    def _update_image_count(self, folder: Path):
        """Count and display number of images in folder."""
        count = 0
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
            count += len(list(folder.glob(ext)))
        
        if count > 0:
            self.image_count_label.setText(f"📊 Found {count} images in folder")
        else:
            self.image_count_label.setText("⚠ No images found in folder")
    
    def _toggle_max_images(self, checked: bool):
        """Enable/disable max images spinner based on checkbox."""
        self.max_images_spin.setEnabled(not checked)
    
    def _load_previous_run(self):
        """Load a previous benchmark run for validation."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Previous Benchmark Run Folder",
            str(Path.home() / "jetson_benchmarks")
        )
        if folder_path:
            run_folder = Path(folder_path)
            # Validate folder structure
            if not (run_folder / "images").exists() or not (run_folder / "labels").exists():
                QMessageBox.warning(
                    self,
                    "Invalid Run Folder",
                    "Selected folder does not contain 'images' and 'labels' subdirectories.\n\n"
                    "Please select a valid benchmark run folder."
                )
                return
            
            self.output_text.append(f"\n📂 Loading previous run: {run_folder}")
            self._start_validation(run_folder)
    
    def _run_inference(self):
        """Start inference on test images."""
        engine_path = Path(self.engine_edit.text().strip())
        test_folder = Path(self.test_folder_edit.text().strip())
        
        if not engine_path.exists():
            QMessageBox.warning(self, "Error", "Please select a valid TensorRT engine file")
            return
        
        if not test_folder.exists():
            QMessageBox.warning(self, "Error", "Please select a valid test folder")
            return
        
        # Get max images setting
        max_images = None if self.use_all_check.isChecked() else self.max_images_spin.value()
        
        # Create benchmark run folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = Path.home() / "jetson_benchmarks" / f"run_{timestamp}"
        run_folder.mkdir(parents=True, exist_ok=True)
        
        self.output_text.append("\n" + "=" * 70)
        self.output_text.append("⚠️  IMPORTANT: SOURCE FILES ARE NEVER MODIFIED")
        self.output_text.append("   All images are COPIED (not moved) to benchmark folder")
        self.output_text.append("   Your original test images remain untouched")
        self.output_text.append("=" * 70)
        self.output_text.append(f"📁 Created benchmark run: {run_folder}")
        if max_images:
            self.output_text.append(f"📊 Testing on {max_images} RANDOMLY SELECTED images")
        else:
            self.output_text.append("📊 Testing on ALL images in folder (random order)")
        self.output_text.append("🚀 Starting inference...")
        
        # Disable UI
        self.run_btn.setEnabled(False)
        
        # Start worker
        self.worker = InferenceWorker(engine_path, test_folder, run_folder, max_images=max_images)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.inference_complete.connect(self._on_inference_complete)
        self.worker.inference_failed.connect(self._on_inference_failed)
        self.worker.start()
    
    def _on_progress(self, current: int, total: int, image_name: str, fps: float):
        """Handle progress updates."""
        self.statusBar().showMessage(f"Processing {current}/{total}: {image_name} | Current FPS: {fps:.1f}")
    
    def _on_inference_complete(self, run_folder: str, total_time: float, stats: dict):
        """Handle inference completion."""
        self.run_btn.setEnabled(True)
        
        self.output_text.append(f"\n✅ Inference complete in {total_time:.1f}s")
        self.output_text.append("\n" + "-" * 70)
        self.output_text.append("STATISTICS:")
        self.output_text.append(f"  Total Images: {stats['total_images']}")
        self.output_text.append(f"  Images w/ Detections: {stats['images_with_detections']}")
        self.output_text.append(f"  Images Empty: {stats['images_empty']}")
        self.output_text.append(f"  Total Detections: {stats['total_detections']}")
        self.output_text.append(f"  Avg Detections per Image: {stats['avg_detections_per_image']:.2f}")
        self.output_text.append(f"  Mean FPS: {stats['mean_fps']:.2f}")
        self.output_text.append(f"  Mean Latency: {stats['mean_latency_ms']:.2f} ms")
        self.output_text.append("-" * 70)
        
        self.statusBar().showMessage(f"Inference complete - {stats['mean_fps']:.2f} FPS")
        
        # Ask if user wants to start validation
        reply = QMessageBox.question(
            self,
            "Inference Complete",
            f"Inference completed successfully!\n\n"
            f"Processed {stats['total_images']} images in {total_time:.1f}s\n"
            f"Mean FPS: {stats['mean_fps']:.2f}\n"
            f"Total Detections: {stats['total_detections']}\n\n"
            f"Start manual validation now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._start_validation(Path(run_folder))
    
    def _on_inference_failed(self, error_msg: str):
        """Handle inference failure."""
        self.run_btn.setEnabled(True)
        self.output_text.append(f"\n❌ Error: {error_msg}")
        self.statusBar().showMessage("Inference failed")
        QMessageBox.critical(self, "Inference Failed", error_msg)
    
    def _start_validation(self, run_folder: Path):
        """Start validation viewer."""
        try:
            # Create validation viewer
            self.validation_viewer = ValidationViewer(run_folder)
            self.validation_viewer.validation_complete.connect(self._on_validation_complete)
            
            # Add to stacked widget and switch to it
            self.stacked_widget.addWidget(self.validation_viewer)
            self.stacked_widget.setCurrentWidget(self.validation_viewer)
            
            self.output_text.append(f"\n🔍 Starting validation for {len(self.validation_viewer.image_files)} images")
            self.statusBar().showMessage("Validation mode - Review each image")
        except ValueError as e:
            # Validation viewer initialization failed (no images)
            self.output_text.append(f"\n❌ Cannot start validation: {str(e)}")
            QMessageBox.critical(
                self,
                "Validation Error",
                f"Cannot start validation:\n{str(e)}\n\n"
                f"The inference run may have failed or produced no images."
            )
    
    def _on_validation_complete(self):
        """Handle validation completion."""
        self.output_text.append("\n✅ Validation complete! Report generated.")
        self.statusBar().showMessage("Validation complete - Ready for next benchmark")
        
        # Switch back to main widget
        self.stacked_widget.setCurrentWidget(self.main_widget)
        
        # Remove and cleanup validation viewer
        if self.validation_viewer:
            self.stacked_widget.removeWidget(self.validation_viewer)
            self.validation_viewer.deleteLater()
            self.validation_viewer = None


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = JetsonBenchmarkApp()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
