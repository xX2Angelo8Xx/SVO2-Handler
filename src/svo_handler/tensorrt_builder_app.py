#!/usr/bin/env python3
"""
Simple GUI for building TensorRT engines from exported training models.

This app provides a straightforward interface to convert PyTorch models
to optimized TensorRT engines for Jetson deployment.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit,
    QGroupBox, QCheckBox, QSpinBox, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


class TensorRTBuildWorker(QThread):
    """Background worker for TensorRT engine building."""
    
    progress_updated = Signal(str)  # Status message
    build_complete = Signal(str)    # Engine path
    build_failed = Signal(str)      # Error message
    
    def __init__(self, export_folder: Path, fp16: bool, workspace: int):
        super().__init__()
        self.export_folder = export_folder
        self.fp16 = fp16
        self.workspace = workspace
        self._cancelled = False
    
    def cancel(self):
        """Cancel the build process."""
        self._cancelled = True
    
    def run(self):
        """Execute TensorRT build."""
        try:
            import subprocess
            
            # Build command
            script_path = Path(__file__).parent.parent.parent / "scripts" / "build_tensorrt_engine.py"
            cmd = [
                sys.executable,
                str(script_path),
                str(self.export_folder),
                f"--workspace={self.workspace}"
            ]
            
            # Add --no-fp16 only if FP16 is disabled
            if not self.fp16:
                cmd.append("--no-fp16")
            
            self.progress_updated.emit("🔨 Starting TensorRT build...")
            self.progress_updated.emit(f"Command: {' '.join(cmd)}\n")
            
            # Run build process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Stream output
            for line in process.stdout:
                if self._cancelled:
                    process.terminate()
                    self.build_failed.emit("Build cancelled by user")
                    return
                self.progress_updated.emit(line.rstrip())
            
            process.wait()
            
            if process.returncode == 0:
                engine_path = self.export_folder / "models" / "best.engine"
                self.build_complete.emit(str(engine_path))
            else:
                self.build_failed.emit(f"Build failed with exit code {process.returncode}")
                
        except Exception as e:
            self.build_failed.emit(f"Build error: {e}")


class TensorRTBuilderApp(QMainWindow):
    """Main window for TensorRT engine builder."""
    
    def __init__(self):
        super().__init__()
        self.worker = None
        self._init_ui()
    
    def _init_ui(self):
        """Initialize user interface."""
        self.setWindowTitle("TensorRT Engine Builder")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("TensorRT Engine Builder")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Export folder selection
        folder_group = QGroupBox("Exported Training Model")
        folder_layout = QVBoxLayout()
        
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select exported model folder (e.g., svo_model_20251204_112709_640)")
        folder_row.addWidget(self.folder_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        
        folder_layout.addLayout(folder_row)
        
        info_label = QLabel("Select the folder containing models/ subdirectory with best.pt file")
        info_label.setStyleSheet("color: gray; font-size: 10pt;")
        folder_layout.addWidget(info_label)
        
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)
        
        # Build options
        options_group = QGroupBox("Build Options")
        options_layout = QVBoxLayout()
        
        # FP16 precision
        self.fp16_check = QCheckBox("Enable FP16 precision (faster, recommended)")
        self.fp16_check.setChecked(True)
        options_layout.addWidget(self.fp16_check)
        
        # Workspace size
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(QLabel("Workspace size (GB):"))
        self.workspace_spin = QSpinBox()
        self.workspace_spin.setRange(1, 8)
        self.workspace_spin.setValue(4)
        workspace_row.addWidget(self.workspace_spin)
        workspace_row.addStretch()
        options_layout.addLayout(workspace_row)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Build button
        self.build_btn = QPushButton("Build TensorRT Engine")
        self.build_btn.setMinimumHeight(40)
        self.build_btn.clicked.connect(self._start_build)
        layout.addWidget(self.build_btn)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Output log
        log_label = QLabel("Build Output:")
        layout.addWidget(log_label)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.output_text, stretch=1)
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def _browse_folder(self):
        """Open folder browser dialog."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Exported Model Folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly
        )
        if folder:
            self.folder_edit.setText(folder)
            self._validate_folder(Path(folder))
    
    def _validate_folder(self, folder: Path) -> bool:
        """Validate export folder structure."""
        models_dir = folder / "models"
        pt_file = models_dir / "best.pt"
        
        if not models_dir.exists():
            self.output_text.append(f"❌ No models/ directory found in {folder}")
            return False
        
        if not pt_file.exists():
            self.output_text.append(f"❌ No best.pt file found in {models_dir}")
            return False
        
        self.output_text.append(f"✓ Found PyTorch model: {pt_file}")
        return True
    
    def _start_build(self):
        """Start TensorRT engine build."""
        folder = Path(self.folder_edit.text())
        
        if not folder.exists():
            self.output_text.append("❌ Please select a valid export folder")
            return
        
        if not self._validate_folder(folder):
            return
        
        # Disable UI during build
        self.build_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.output_text.clear()
        self.statusBar().showMessage("Building TensorRT engine...")
        
        # Start worker
        self.worker = TensorRTBuildWorker(
            folder,
            self.fp16_check.isChecked(),
            self.workspace_spin.value()
        )
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.build_complete.connect(self._on_complete)
        self.worker.build_failed.connect(self._on_failed)
        self.worker.start()
    
    def _on_progress(self, message: str):
        """Handle progress update."""
        self.output_text.append(message)
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
    
    def _on_complete(self, engine_path: str):
        """Handle build completion."""
        self.progress_bar.setVisible(False)
        self.build_btn.setEnabled(True)
        self.output_text.append("\n" + "=" * 70)
        self.output_text.append(f"✅ TensorRT engine built successfully!")
        self.output_text.append(f"📁 Engine file: {engine_path}")
        self.output_text.append("=" * 70)
        self.statusBar().showMessage("Build complete!")
    
    def _on_failed(self, error: str):
        """Handle build failure."""
        self.progress_bar.setVisible(False)
        self.build_btn.setEnabled(True)
        self.output_text.append("\n" + "=" * 70)
        self.output_text.append(f"❌ Build failed: {error}")
        self.output_text.append("=" * 70)
        self.statusBar().showMessage("Build failed")
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        event.accept()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    window = TensorRTBuilderApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
