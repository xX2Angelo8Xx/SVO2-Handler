"""
Benchmark application for testing YOLO models on Jetson.

This application loads trained YOLO models (PyTorch .pt, ONNX, or TensorRT)
and runs comprehensive benchmarks including:
- Inference speed testing
- Accuracy metrics (if ground truth available)
- Resource usage monitoring
- Comparison between model formats

Usage:
    python -m svo_handler.benchmark_app
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets

from .benchmark_config import BenchmarkConfig
from .benchmark_worker import BenchmarkWorker


class BenchmarkApp(QtWidgets.QMainWindow):
    """Main window for YOLO model benchmarking."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVO2 Handler - Model Benchmark")
        self.resize(1200, 800)

        self._config: Optional[BenchmarkConfig] = None
        self._worker: Optional[BenchmarkWorker] = None

        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        """Build the user interface."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # Model selection section
        model_group = QtWidgets.QGroupBox("Model Selection")
        model_layout = QtWidgets.QFormLayout()

        self.model_path_edit = QtWidgets.QLineEdit()
        self.model_path_edit.setPlaceholderText("Select model file (.pt, .onnx, or .engine)")
        model_browse_btn = QtWidgets.QPushButton("Browse...")
        model_path_layout = QtWidgets.QHBoxLayout()
        model_path_layout.addWidget(self.model_path_edit)
        model_path_layout.addWidget(model_browse_btn)
        model_browse_btn.clicked.connect(self._browse_model)

        self.model_format_combo = QtWidgets.QComboBox()
        self.model_format_combo.addItems(["PyTorch (.pt)", "ONNX (.onnx)", "TensorRT (.engine)"])

        model_layout.addRow("Model Path:", model_path_layout)
        model_layout.addRow("Format:", self.model_format_combo)
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Test dataset section
        data_group = QtWidgets.QGroupBox("Test Dataset")
        data_layout = QtWidgets.QFormLayout()

        self.test_images_edit = QtWidgets.QLineEdit()
        self.test_images_edit.setPlaceholderText("Select folder with test images")
        test_browse_btn = QtWidgets.QPushButton("Browse...")
        test_path_layout = QtWidgets.QHBoxLayout()
        test_path_layout.addWidget(self.test_images_edit)
        test_path_layout.addWidget(test_browse_btn)
        test_browse_btn.clicked.connect(self._browse_test_images)

        self.has_gt_checkbox = QtWidgets.QCheckBox("Has ground truth annotations (.txt files)")
        self.has_gt_checkbox.setChecked(True)

        data_layout.addRow("Test Images:", test_path_layout)
        data_layout.addRow("Ground Truth:", self.has_gt_checkbox)
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

        # Benchmark configuration section
        config_group = QtWidgets.QGroupBox("Benchmark Configuration")
        config_layout = QtWidgets.QFormLayout()

        self.image_size_combo = QtWidgets.QComboBox()
        self.image_size_combo.addItems(["640", "1280", "Source (no resize)"])

        self.warmup_spin = QtWidgets.QSpinBox()
        self.warmup_spin.setRange(1, 100)
        self.warmup_spin.setValue(10)
        self.warmup_spin.setSuffix(" frames")

        self.iterations_spin = QtWidgets.QSpinBox()
        self.iterations_spin.setRange(10, 10000)
        self.iterations_spin.setValue(100)
        self.iterations_spin.setSuffix(" frames")

        self.conf_threshold_spin = QtWidgets.QDoubleSpinBox()
        self.conf_threshold_spin.setRange(0.0, 1.0)
        self.conf_threshold_spin.setSingleStep(0.05)
        self.conf_threshold_spin.setValue(0.25)

        self.iou_threshold_spin = QtWidgets.QDoubleSpinBox()
        self.iou_threshold_spin.setRange(0.0, 1.0)
        self.iou_threshold_spin.setSingleStep(0.05)
        self.iou_threshold_spin.setValue(0.45)

        config_layout.addRow("Image Size:", self.image_size_combo)
        config_layout.addRow("Warmup Iterations:", self.warmup_spin)
        config_layout.addRow("Test Iterations:", self.iterations_spin)
        config_layout.addRow("Confidence Threshold:", self.conf_threshold_spin)
        config_layout.addRow("IoU Threshold:", self.iou_threshold_spin)
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Benchmark types section
        types_group = QtWidgets.QGroupBox("Benchmark Types")
        types_layout = QtWidgets.QVBoxLayout()

        self.speed_checkbox = QtWidgets.QCheckBox("Speed & Performance")
        self.speed_checkbox.setChecked(True)
        self.speed_checkbox.setToolTip("Measure inference time, FPS, latency distribution")

        self.accuracy_checkbox = QtWidgets.QCheckBox("Accuracy Metrics")
        self.accuracy_checkbox.setChecked(True)
        self.accuracy_checkbox.setToolTip("Calculate mAP, precision, recall (requires ground truth)")

        self.resource_checkbox = QtWidgets.QCheckBox("Resource Usage")
        self.resource_checkbox.setChecked(True)
        self.resource_checkbox.setToolTip("Monitor GPU memory, CPU usage, power consumption")

        types_layout.addWidget(self.speed_checkbox)
        types_layout.addWidget(self.accuracy_checkbox)
        types_layout.addWidget(self.resource_checkbox)
        types_group.setLayout(types_layout)
        layout.addWidget(types_group)

        # Control buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start Benchmark")
        self.start_btn.setEnabled(False)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.export_btn = QtWidgets.QPushButton("Export Results")
        self.export_btn.setEnabled(False)

        button_layout.addStretch()
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.export_btn)
        layout.addLayout(button_layout)

        # Progress section
        self.progress_bar = QtWidgets.QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QtWidgets.QLabel("Ready to benchmark")
        layout.addWidget(self.status_label)

        # Results display
        results_group = QtWidgets.QGroupBox("Benchmark Results")
        results_layout = QtWidgets.QVBoxLayout()

        self.results_text = QtWidgets.QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFont(QtWidgets.QFont("Courier", 10))
        results_layout.addWidget(self.results_text)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group, stretch=1)

        # Connect validation
        self.model_path_edit.textChanged.connect(self._validate_inputs)
        self.test_images_edit.textChanged.connect(self._validate_inputs)

    def _wire_signals(self) -> None:
        """Wire up signal connections."""
        self.start_btn.clicked.connect(self._start_benchmark)
        self.stop_btn.clicked.connect(self._stop_benchmark)
        self.export_btn.clicked.connect(self._export_results)

    def _browse_model(self) -> None:
        """Browse for model file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Model File",
            str(Path.home()),
            "Model Files (*.pt *.onnx *.engine);;All Files (*)"
        )
        if path:
            self.model_path_edit.setText(path)
            # Auto-detect format
            if path.endswith('.pt'):
                self.model_format_combo.setCurrentText("PyTorch (.pt)")
            elif path.endswith('.onnx'):
                self.model_format_combo.setCurrentText("ONNX (.onnx)")
            elif path.endswith('.engine'):
                self.model_format_combo.setCurrentText("TensorRT (.engine)")

    def _browse_test_images(self) -> None:
        """Browse for test images folder."""
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Test Images Folder",
            str(Path.home())
        )
        if path:
            self.test_images_edit.setText(path)

    def _validate_inputs(self) -> None:
        """Validate inputs and enable/disable start button."""
        model_path = Path(self.model_path_edit.text())
        test_path = Path(self.test_images_edit.text())

        valid = (
            model_path.exists() and
            model_path.is_file() and
            test_path.exists() and
            test_path.is_dir()
        )

        self.start_btn.setEnabled(valid)

    def _start_benchmark(self) -> None:
        """Start the benchmark."""
        # TODO: Implement benchmark execution
        self.status_label.setText("Benchmark not yet implemented")
        QtWidgets.QMessageBox.information(
            self,
            "Not Implemented",
            "Benchmark execution will be implemented in the next iteration.\n\n"
            "This app will test:\n"
            "- Inference speed (FPS, latency)\n"
            "- Accuracy metrics (mAP, precision, recall)\n"
            "- Resource usage (GPU memory, CPU, power)\n\n"
            "For now, use the test_inference.py script in the model export folder."
        )

    def _stop_benchmark(self) -> None:
        """Stop the running benchmark."""
        if self._worker:
            self._worker.cancel()

    def _export_results(self) -> None:
        """Export benchmark results to file."""
        pass


def main() -> int:
    """Application entry point."""
    app = QtWidgets.QApplication(sys.argv)
    window = BenchmarkApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
