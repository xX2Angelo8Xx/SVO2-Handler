"""YOLO Training GUI Application.

This application provides a graphical interface for training YOLO models
on the 73-bucket dataset structure. Features include:
- Dataset formatting and preparation
- Model selection and confi        # Image size
        self.image_size_combo = QtWidgets.QComboBox()
        self.image_size_combo.addItems(["416", "512", "640", "800", "1024", "1280"])
        self.image_size_combo.setCurrentText("640")
        layout.addRow("Image Size:", self.image_size_combo)
        
        # Use source resolution
        self.use_source_resolution_check = QtWidgets.QCheckBox(
            "Use Source Resolution (train at native camera resolution, e.g., 1280x720)"
        )
        self.use_source_resolution_check.setChecked(False)
        self.use_source_resolution_check.toggled.connect(self._on_source_resolution_toggled)
        layout.addRow(self.use_source_resolution_check)
        
        # Batch sizen
- Real-time training progress monitoring
- Training controls (start/pause/cancel)
- Metrics visualization
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets

from .training_config import TrainingConfig, get_augmentation_preset
from .training_worker import TrainingWorker


class TrainingApp(QtWidgets.QMainWindow):
    """Main window for YOLO training application."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YOLO Training - SVO2 Handler")
        self.resize(1000, 800)
        
        self.worker: Optional[TrainingWorker] = None
        self.config: Optional[TrainingConfig] = None
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Create and layout UI components."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        
        # Title
        title = QtWidgets.QLabel("🎯 YOLO Model Training")
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Tabs for different configuration sections
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab 1: Dataset Configuration
        self.tabs.addTab(self._create_dataset_tab(), "📦 Dataset")
        
        # Tab 2: Model Configuration
        self.tabs.addTab(self._create_model_tab(), "🤖 Model")
        
        # Tab 3: Training Parameters
        self.tabs.addTab(self._create_training_tab(), "⚙️ Training")
        
        # Tab 4: Augmentation
        self.tabs.addTab(self._create_augmentation_tab(), "🎨 Augmentation")
        
        # Training controls
        controls_group = QtWidgets.QGroupBox("Training Controls")
        controls_layout = QtWidgets.QHBoxLayout(controls_group)
        
        self.start_btn = QtWidgets.QPushButton("🚀 Start Training")
        self.start_btn.setMinimumHeight(40)
        self.pause_btn = QtWidgets.QPushButton("⏸️ Pause")
        self.pause_btn.setEnabled(False)
        self.cancel_btn = QtWidgets.QPushButton("⏹️ Cancel")
        self.cancel_btn.setEnabled(False)
        
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.cancel_btn)
        layout.addWidget(controls_group)
        
        # Progress display
        progress_group = QtWidgets.QGroupBox("Training Progress")
        progress_layout = QtWidgets.QVBoxLayout(progress_group)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_label = QtWidgets.QLabel("Ready to start training")
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(QtWidgets.QLabel("Training Log:"))
        progress_layout.addWidget(self.log_text)
        layout.addWidget(progress_group)
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def _create_dataset_tab(self) -> QtWidgets.QWidget:
        """Create dataset configuration tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)
        
        # Source training folder (73-bucket structure)
        source_layout = QtWidgets.QHBoxLayout()
        self.source_folder_edit = QtWidgets.QLineEdit()
        self.source_folder_edit.setPlaceholderText("Select 73-bucket training folder...")
        source_browse_btn = QtWidgets.QPushButton("Browse")
        source_browse_btn.clicked.connect(self._browse_source_folder)
        source_layout.addWidget(self.source_folder_edit)
        source_layout.addWidget(source_browse_btn)
        layout.addRow("Source Training Folder:", source_layout)
        
        # Output dataset folder
        output_layout = QtWidgets.QHBoxLayout()
        self.output_folder_edit = QtWidgets.QLineEdit()
        self.output_folder_edit.setPlaceholderText("Where to create YOLO-formatted dataset...")
        output_browse_btn = QtWidgets.QPushButton("Browse")
        output_browse_btn.clicked.connect(self._browse_output_folder)
        output_layout.addWidget(self.output_folder_edit)
        output_layout.addWidget(output_browse_btn)
        layout.addRow("Output Dataset Folder:", output_layout)
        
        # Data splits
        layout.addRow(QtWidgets.QLabel("<hr>"))
        layout.addRow(QtWidgets.QLabel("<b>Data Split Ratios</b>"))
        
        self.train_ratio_spin = QtWidgets.QDoubleSpinBox()
        self.train_ratio_spin.setRange(0.0, 1.0)
        self.train_ratio_spin.setSingleStep(0.05)
        self.train_ratio_spin.setValue(0.7)
        self.train_ratio_spin.setSuffix(" (70%)")
        layout.addRow("Training Set:", self.train_ratio_spin)
        
        self.val_ratio_spin = QtWidgets.QDoubleSpinBox()
        self.val_ratio_spin.setRange(0.0, 1.0)
        self.val_ratio_spin.setSingleStep(0.05)
        self.val_ratio_spin.setValue(0.2)
        self.val_ratio_spin.setSuffix(" (20%)")
        layout.addRow("Validation Set:", self.val_ratio_spin)
        
        self.test_ratio_spin = QtWidgets.QDoubleSpinBox()
        self.test_ratio_spin.setRange(0.0, 1.0)
        self.test_ratio_spin.setSingleStep(0.05)
        self.test_ratio_spin.setValue(0.1)
        self.test_ratio_spin.setSuffix(" (10%)")
        layout.addRow("Test Set:", self.test_ratio_spin)
        
        # Options
        layout.addRow(QtWidgets.QLabel("<hr>"))
        self.include_negatives_check = QtWidgets.QCheckBox("Include negative samples (backgrounds)")
        self.include_negatives_check.setChecked(True)
        layout.addRow(self.include_negatives_check)
        
        self.shuffle_check = QtWidgets.QCheckBox("Shuffle data before splitting")
        self.shuffle_check.setChecked(True)
        layout.addRow(self.shuffle_check)
        
        self.random_seed_spin = QtWidgets.QSpinBox()
        self.random_seed_spin.setRange(0, 99999)
        self.random_seed_spin.setValue(42)
        layout.addRow("Random Seed:", self.random_seed_spin)
        
        layout.addRow(QtWidgets.QLabel(""))
        return widget
    
    def _create_model_tab(self) -> QtWidgets.QWidget:
        """Create model configuration tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)
        
        # Model selection
        self.model_type_combo = QtWidgets.QComboBox()
        self.model_type_combo.addItems(["yolov8", "yolov5"])
        layout.addRow("YOLO Version:", self.model_type_combo)
        
        self.model_variant_combo = QtWidgets.QComboBox()
        self.model_variant_combo.addItems(["n (nano)", "s (small)", "m (medium)", "l (large)", "x (xlarge)"])
        layout.addRow("Model Variant:", self.model_variant_combo)
        
        # Pretrained weights
        layout.addRow(QtWidgets.QLabel("<hr>"))
        self.pretrained_combo = QtWidgets.QComboBox()
        self.pretrained_combo.addItems(["COCO pretrained (default)", "From scratch", "Custom weights..."])
        layout.addRow("Pretrained Weights:", self.pretrained_combo)
        
        self.custom_weights_edit = QtWidgets.QLineEdit()
        self.custom_weights_edit.setPlaceholderText("Path to .pt file...")
        self.custom_weights_edit.setEnabled(False)
        layout.addRow("Custom Weights Path:", self.custom_weights_edit)
        
        # Resume checkpoint
        layout.addRow(QtWidgets.QLabel("<hr>"))
        resume_layout = QtWidgets.QHBoxLayout()
        self.resume_checkbox = QtWidgets.QCheckBox("Resume from checkpoint")
        self.resume_path_edit = QtWidgets.QLineEdit()
        self.resume_path_edit.setPlaceholderText("Path to checkpoint .pt file...")
        self.resume_path_edit.setEnabled(False)
        resume_browse_btn = QtWidgets.QPushButton("Browse")
        resume_browse_btn.clicked.connect(self._browse_resume_checkpoint)
        resume_browse_btn.setEnabled(False)
        resume_layout.addWidget(self.resume_path_edit)
        resume_layout.addWidget(resume_browse_btn)
        
        layout.addRow(self.resume_checkbox)
        layout.addRow("Checkpoint Path:", resume_layout)
        
        # Connect signals
        self.pretrained_combo.currentTextChanged.connect(
            lambda text: self.custom_weights_edit.setEnabled("Custom" in text)
        )
        self.resume_checkbox.toggled.connect(
            lambda checked: (self.resume_path_edit.setEnabled(checked), resume_browse_btn.setEnabled(checked))
        )
        
        layout.addRow(QtWidgets.QLabel(""))
        return widget
    
    def _create_training_tab(self) -> QtWidgets.QWidget:
        """Create training parameters tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)
        
        # Image size
        self.image_size_combo = QtWidgets.QComboBox()
        self.image_size_combo.addItems(["416", "512", "640", "1280"])
        self.image_size_combo.setCurrentText("640")
        layout.addRow("Image Size:", self.image_size_combo)
        
        # Batch size
        self.batch_size_spin = QtWidgets.QSpinBox()
        self.batch_size_spin.setRange(1, 128)
        self.batch_size_spin.setValue(16)
        self.batch_size_spin.setSpecialValueText("Auto-detect")
        layout.addRow("Batch Size:", self.batch_size_spin)
        
        # Epochs
        self.epochs_spin = QtWidgets.QSpinBox()
        self.epochs_spin.setRange(1, 1000)
        self.epochs_spin.setValue(100)
        layout.addRow("Epochs:", self.epochs_spin)
        
        # Learning rate
        layout.addRow(QtWidgets.QLabel("<hr>"))
        layout.addRow(QtWidgets.QLabel("<b>Optimization</b>"))
        
        self.lr_spin = QtWidgets.QDoubleSpinBox()
        self.lr_spin.setRange(0.0001, 1.0)
        self.lr_spin.setSingleStep(0.001)
        self.lr_spin.setDecimals(4)
        self.lr_spin.setValue(0.01)
        layout.addRow("Learning Rate:", self.lr_spin)
        
        self.optimizer_combo = QtWidgets.QComboBox()
        self.optimizer_combo.addItems(["Adam", "SGD", "AdamW"])
        layout.addRow("Optimizer:", self.optimizer_combo)
        
        self.lr_scheduler_combo = QtWidgets.QComboBox()
        self.lr_scheduler_combo.addItems(["cosine", "linear", "step", "none"])
        layout.addRow("LR Scheduler:", self.lr_scheduler_combo)
        
        # Hardware
        layout.addRow(QtWidgets.QLabel("<hr>"))
        layout.addRow(QtWidgets.QLabel("<b>Hardware</b>"))
        
        self.device_edit = QtWidgets.QLineEdit("0")
        self.device_edit.setPlaceholderText("0 (cuda:0), cpu, or 0,1 (multi-GPU)")
        layout.addRow("Device:", self.device_edit)
        
        self.workers_spin = QtWidgets.QSpinBox()
        self.workers_spin.setRange(0, 32)
        self.workers_spin.setValue(8)
        layout.addRow("Dataloader Workers:", self.workers_spin)
        
        self.amp_check = QtWidgets.QCheckBox("Use AMP (Automatic Mixed Precision)")
        self.amp_check.setChecked(True)
        layout.addRow(self.amp_check)
        
        # Advanced
        layout.addRow(QtWidgets.QLabel("<hr>"))
        layout.addRow(QtWidgets.QLabel("<b>Advanced</b>"))
        
        self.save_period_spin = QtWidgets.QSpinBox()
        self.save_period_spin.setRange(1, 100)
        self.save_period_spin.setValue(10)
        layout.addRow("Save Period (epochs):", self.save_period_spin)
        
        self.patience_spin = QtWidgets.QSpinBox()
        self.patience_spin.setRange(0, 1000)
        self.patience_spin.setValue(50)
        self.patience_spin.setSpecialValueText("Disabled")
        layout.addRow("Early Stopping Patience:", self.patience_spin)
        
        layout.addRow(QtWidgets.QLabel(""))
        return widget
    
    def _create_augmentation_tab(self) -> QtWidgets.QWidget:
        """Create augmentation settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        # Preset selection
        preset_layout = QtWidgets.QHBoxLayout()
        preset_layout.addWidget(QtWidgets.QLabel("Preset:"))
        self.aug_preset_combo = QtWidgets.QComboBox()
        self.aug_preset_combo.addItems(["none", "light", "moderate", "heavy"])
        self.aug_preset_combo.setCurrentText("moderate")
        preset_layout.addWidget(self.aug_preset_combo)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)
        
        layout.addWidget(QtWidgets.QLabel("<i>Augmentation parameters (modify preset values if needed):</i>"))
        
        # Augmentation parameters
        form = QtWidgets.QFormLayout()
        
        self.aug_fliplr_spin = QtWidgets.QDoubleSpinBox()
        self.aug_fliplr_spin.setRange(0.0, 1.0)
        self.aug_fliplr_spin.setSingleStep(0.1)
        self.aug_fliplr_spin.setValue(0.5)
        form.addRow("Horizontal Flip Probability:", self.aug_fliplr_spin)
        
        self.aug_mosaic_spin = QtWidgets.QDoubleSpinBox()
        self.aug_mosaic_spin.setRange(0.0, 1.0)
        self.aug_mosaic_spin.setSingleStep(0.1)
        self.aug_mosaic_spin.setValue(1.0)
        form.addRow("Mosaic Probability:", self.aug_mosaic_spin)
        
        self.aug_scale_spin = QtWidgets.QDoubleSpinBox()
        self.aug_scale_spin.setRange(0.0, 1.0)
        self.aug_scale_spin.setSingleStep(0.05)
        self.aug_scale_spin.setValue(0.5)
        form.addRow("Scale Augmentation:", self.aug_scale_spin)
        
        self.aug_translate_spin = QtWidgets.QDoubleSpinBox()
        self.aug_translate_spin.setRange(0.0, 0.5)
        self.aug_translate_spin.setSingleStep(0.05)
        self.aug_translate_spin.setValue(0.1)
        form.addRow("Translate Augmentation:", self.aug_translate_spin)
        
        layout.addLayout(form)
        layout.addStretch()
        
        # Connect preset change
        self.aug_preset_combo.currentTextChanged.connect(self._on_aug_preset_changed)
        
        return widget
    
    def _connect_signals(self) -> None:
        """Connect signals for UI interactions."""
        self.start_btn.clicked.connect(self._start_training)
        self.pause_btn.clicked.connect(self._pause_training)
        self.cancel_btn.clicked.connect(self._cancel_training)
    
    def _on_source_resolution_toggled(self, checked: bool) -> None:
        """Handle source resolution checkbox toggle."""
        # Disable image size combo when using source resolution
        self.image_size_combo.setEnabled(not checked)
        if checked:
            self.image_size_combo.setToolTip(
                "Disabled: Using source resolution from dataset images"
            )
        else:
            self.image_size_combo.setToolTip("")
    
    def _browse_source_folder(self) -> None:
        """Browse for source training folder."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select 73-Bucket Training Folder"
        )
        if folder:
            self.source_folder_edit.setText(folder)
    
    def _browse_output_folder(self) -> None:
        """Browse for output dataset folder."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Output Dataset Folder"
        )
        if folder:
            self.output_folder_edit.setText(folder)
    
    def _browse_resume_checkpoint(self) -> None:
        """Browse for resume checkpoint file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Checkpoint File",
            "",
            "PyTorch Weights (*.pt)"
        )
        if file:
            self.resume_path_edit.setText(file)
    
    def _on_aug_preset_changed(self, preset: str) -> None:
        """Update augmentation sliders when preset changes."""
        aug_params = get_augmentation_preset(preset)
        self.aug_fliplr_spin.setValue(aug_params.get("aug_fliplr", 0.5))
        self.aug_mosaic_spin.setValue(aug_params.get("aug_mosaic", 1.0))
        self.aug_scale_spin.setValue(aug_params.get("aug_scale", 0.5))
        self.aug_translate_spin.setValue(aug_params.get("aug_translate", 0.1))
    
    def _build_config(self) -> TrainingConfig:
        """Build training configuration from UI values."""
        # Get model variant (remove description in parentheses)
        variant = self.model_variant_combo.currentText().split()[0]
        
        # Get pretrained weights
        pretrained_text = self.pretrained_combo.currentText()
        if "default" in pretrained_text:
            pretrained = "default"
        elif "scratch" in pretrained_text:
            pretrained = None
        else:
            pretrained = self.custom_weights_edit.text() or None
        
        # Resume checkpoint
        resume = None
        if self.resume_checkbox.isChecked() and self.resume_path_edit.text():
            resume = Path(self.resume_path_edit.text())
        
        config = TrainingConfig(
            # Dataset
            source_training_root=Path(self.source_folder_edit.text()),
            output_dataset_root=Path(self.output_folder_edit.text()),
            train_ratio=self.train_ratio_spin.value(),
            val_ratio=self.val_ratio_spin.value(),
            test_ratio=self.test_ratio_spin.value(),
            include_negative_samples=self.include_negatives_check.isChecked(),
            shuffle_data=self.shuffle_check.isChecked(),
            random_seed=self.random_seed_spin.value(),
            
            # Model
            model_type=self.model_type_combo.currentText(),
            model_variant=variant,
            pretrained_weights=pretrained,
            resume_checkpoint=resume,
            
            # Training
            image_size=int(self.image_size_combo.currentText()) if not self.use_source_resolution_check.isChecked() else -1,
            batch_size=self.batch_size_spin.value(),
            epochs=self.epochs_spin.value(),
            learning_rate=self.lr_spin.value(),
            optimizer=self.optimizer_combo.currentText(),
            lr_scheduler=self.lr_scheduler_combo.currentText(),
            device=self.device_edit.text(),
            workers=self.workers_spin.value(),
            amp=self.amp_check.isChecked(),
            save_period=self.save_period_spin.value(),
            patience=self.patience_spin.value(),
            
            # Augmentation
            augmentation_preset=self.aug_preset_combo.currentText(),
            aug_fliplr=self.aug_fliplr_spin.value(),
            aug_mosaic=self.aug_mosaic_spin.value(),
            aug_scale=self.aug_scale_spin.value(),
            aug_translate=self.aug_translate_spin.value(),
        )
        
        return config
    
    def _start_training(self) -> None:
        """Start training with current configuration."""
        try:
            # Build configuration
            self.config = self._build_config()
            
            # Show configuration summary
            self._log(self.config.get_summary())
            self._log("\n" + "="*50 + "\n")
            
            # Create and start worker
            self.worker = TrainingWorker(self.config)
            self.worker.log_message.connect(self._log)
            self.worker.progress_update.connect(self._update_progress)
            self.worker.training_complete.connect(self._on_training_complete)
            self.worker.training_error.connect(self._on_training_error)
            self.worker.format_complete.connect(lambda: self._log("✅ Dataset formatting complete"))
            
            self.worker.start()
            
            # Update UI
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            self.tabs.setEnabled(False)
            self.statusBar().showMessage("Training in progress...")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Configuration Error",
                f"Failed to start training:\n{str(e)}"
            )
    
    def _pause_training(self) -> None:
        """Pause training."""
        if self.worker:
            self.worker.pause()
            self.statusBar().showMessage("Training paused")
    
    def _cancel_training(self) -> None:
        """Cancel training."""
        if self.worker:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Cancel Training",
                "Are you sure you want to cancel training?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.worker.cancel()
                self.worker.wait()
                self._reset_ui()
                self.statusBar().showMessage("Training cancelled")
    
    def _update_progress(self, current: int, total: int, message: str) -> None:
        """Update progress bar and label."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(message)
        self.statusBar().showMessage(f"Epoch {current}/{total}")
    
    def _log(self, message: str) -> None:
        """Add message to log."""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def _on_training_complete(self, message: str) -> None:
        """Handle training completion."""
        self._log(message)
        self._reset_ui()
        self.statusBar().showMessage("Training completed successfully")
        QtWidgets.QMessageBox.information(
            self,
            "Training Complete",
            message
        )
    
    def _on_training_error(self, error: str) -> None:
        """Handle training error."""
        self._log(error)
        self._reset_ui()
        self.statusBar().showMessage("Training failed")
        QtWidgets.QMessageBox.critical(
            self,
            "Training Error",
            error
        )
    
    def _reset_ui(self) -> None:
        """Reset UI to initial state."""
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.tabs.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Ready to start training")


def main() -> None:
    """Entry point for the training application."""
    app = QtWidgets.QApplication(sys.argv)
    window = TrainingApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
