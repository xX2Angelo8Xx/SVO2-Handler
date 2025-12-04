#!/usr/bin/env python3
"""
Jetson Benchmark Application for YOLO model validation.

Workflow:
1. Select TensorRT engine file
2. Select test image folder  
3. Run inference on all images (saves results to benchmark run folder)
4. Manual validation: review detections, mark correct/missed/false
5. Generate statistics report

The app copies test images to a timestamped benchmark folder and runs
inference, saving detection coordinates as .txt files alongside images.
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
    QGroupBox, QMessageBox, QProgressDialog, QScrollArea, QSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QPen, QColor, QBrush


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
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the main UI."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Title
        title = QLabel("Jetson YOLO Benchmark & Validation Tool")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        # Setup widget (hidden during validation)
        self.setup_widget = QWidget()
        setup_layout = QVBoxLayout(self.setup_widget)
        
        # Engine file selection
        engine_group = QGroupBox("1. Select TensorRT Engine")
        engine_layout = QHBoxLayout()
        self.engine_edit = QLineEdit()
        self.engine_edit.setPlaceholderText("Path to .engine file...")
        engine_browse_btn = QPushButton("Browse")
        engine_browse_btn.clicked.connect(self._browse_engine)
        engine_layout.addWidget(self.engine_edit)
        engine_layout.addWidget(engine_browse_btn)
        engine_group.setLayout(engine_layout)
        setup_layout.addWidget(engine_group)
        
        # Test folder selection
        test_group = QGroupBox("2. Select Test Images Folder")
        test_layout = QVBoxLayout()
        folder_layout = QHBoxLayout()
        self.test_folder_edit = QLineEdit()
        self.test_folder_edit.setPlaceholderText("Path to test images folder...")
        self.test_folder_edit.textChanged.connect(self._on_folder_changed)
        test_browse_btn = QPushButton("Browse")
        test_browse_btn.clicked.connect(self._browse_test_folder)
        folder_layout.addWidget(self.test_folder_edit)
        folder_layout.addWidget(test_browse_btn)
        test_layout.addLayout(folder_layout)
        
        # Image count label
        self.image_count_label = QLabel("")
        self.image_count_label.setStyleSheet("color: #2196F3; font-size: 11px;")
        test_layout.addWidget(self.image_count_label)
        
        test_group.setLayout(test_layout)
        setup_layout.addWidget(test_group)
        
        # Max images selection
        images_group = QGroupBox("3. Number of Images to Test")
        images_layout = QVBoxLayout()
        
        images_control_layout = QHBoxLayout()
        self.max_images_spin = QSpinBox()
        self.max_images_spin.setRange(1, 10000)
        self.max_images_spin.setValue(200)
        self.max_images_spin.setSuffix(" images")
        images_control_layout.addWidget(QLabel("Max Images:"))
        images_control_layout.addWidget(self.max_images_spin)
        images_control_layout.addStretch()
        
        self.use_all_check = QCheckBox("Use all images")
        self.use_all_check.toggled.connect(self._toggle_max_images)
        images_control_layout.addWidget(self.use_all_check)
        
        images_layout.addLayout(images_control_layout)
        
        note_label = QLabel("Note: Images are RANDOMLY SELECTED for unbiased sampling")
        note_label.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        images_layout.addWidget(note_label)
        
        images_group.setLayout(images_layout)
        setup_layout.addWidget(images_group)
        
        # Run button
        self.run_btn = QPushButton("▶ Run Inference")
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 16px; padding: 15px;")
        self.run_btn.clicked.connect(self._run_inference)
        setup_layout.addWidget(self.run_btn)
        
        # Load previous run button
        self.load_prev_btn = QPushButton("📂 Load Previous Run for Validation")
        self.load_prev_btn.setStyleSheet("background-color: #757575; color: white; font-size: 12px; padding: 10px;")
        self.load_prev_btn.clicked.connect(self._load_previous_run)
        setup_layout.addWidget(self.load_prev_btn)
        
        main_layout.addWidget(self.setup_widget)
        
        # Output area
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(200)
        output_layout.addWidget(self.output_text)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        self.output_text.append("Ready. Select engine and test folder to begin.")
    
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
            # Hide setup widget
            self.setup_widget.setVisible(False)
            
            # Create validation viewer
            self.validation_viewer = ValidationViewer(run_folder)
            self.validation_viewer.validation_complete.connect(self._on_validation_complete)
            
            # Replace central widget
            self.setCentralWidget(self.validation_viewer)
            
            self.output_text.append(f"\n🔍 Starting validation for {len(self.validation_viewer.image_files)} images")
            self.statusBar().showMessage("Validation mode - Review each image")
        except ValueError as e:
            # Validation viewer initialization failed (no images)
            self.setup_widget.setVisible(True)
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
        
        # Create a fresh central widget with setup_widget and output
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Re-add setup widget
        main_layout.addWidget(self.setup_widget)
        self.setup_widget.setVisible(True)
        
        # Re-add output area (find it from setup_widget's parent layout)
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        output_layout.addWidget(self.output_text)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        # Cleanup validation viewer
        if self.validation_viewer:
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
