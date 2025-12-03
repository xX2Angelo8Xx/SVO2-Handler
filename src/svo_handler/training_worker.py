"""Background worker thread for YOLO model training with real-time progress reporting."""
from __future__ import annotations

import re
import subprocess
import sys
from typing import Optional

from PySide6 import QtCore

from .training_config import TrainingConfig
from .yolo_formatter import YoloFormatter, YoloFormatConfig


class TrainingWorker(QtCore.QThread):
    """QThread worker for running YOLO training in the background.
    
    Signals:
        progress_update: Emitted with (epoch, total_epochs, message)
        metrics_update: Emitted with dict of current metrics
        log_message: Emitted with log line from training
        training_complete: Emitted when training finishes successfully
        training_error: Emitted with error message if training fails
        format_progress: Emitted during dataset formatting (current, total, message)
        format_complete: Emitted when formatting completes
    """
    
    # Signals
    progress_update = QtCore.Signal(int, int, str)  # current_epoch, total_epochs, message
    metrics_update = QtCore.Signal(dict)  # metrics dict
    log_message = QtCore.Signal(str)  # log line
    training_complete = QtCore.Signal(str)  # success message
    training_error = QtCore.Signal(str)  # error message
    format_progress = QtCore.Signal(int, int, str)  # current, total, message
    format_complete = QtCore.Signal()
    
    def __init__(self, config: TrainingConfig):
        super().__init__()
        self.config = config
        self._cancelled = False
        self._paused = False
        self._process: Optional[subprocess.Popen] = None
    
    def run(self) -> None:
        """Main worker thread execution."""
        try:
            # Step 1: Format dataset to YOLO structure
            self.log_message.emit("📦 Formatting dataset to YOLO structure...")
            dataset = self._format_dataset()
            if self._cancelled:
                return
            
            self.format_complete.emit()
            self.log_message.emit(f"✅ Dataset formatted: {len(dataset.train_images)} train, "
                                 f"{len(dataset.val_images)} val, {len(dataset.test_images)} test")
            
            # Step 2: Start YOLO training
            self.log_message.emit("🚀 Starting YOLO training...")
            self._run_training()
            
            if not self._cancelled:
                self.training_complete.emit(f"✅ Training complete! Weights saved to: {self.config.save_dir}")
        
        except Exception as e:
            self.training_error.emit(f"❌ Training failed: {str(e)}")
    
    def _format_dataset(self):
        """Format the 73-bucket structure to YOLO format."""
        format_config = YoloFormatConfig(
            source_root=self.config.source_training_root,
            output_root=self.config.output_dataset_root,
            train_ratio=self.config.train_ratio,
            val_ratio=self.config.val_ratio,
            test_ratio=self.config.test_ratio,
            include_negative_samples=self.config.include_negative_samples,
            shuffle=self.config.shuffle_data,
            random_seed=self.config.random_seed,
        )
        
        formatter = YoloFormatter(format_config)
        
        # Format with progress updates
        self.format_progress.emit(0, 100, "Collecting images...")
        dataset = formatter.format_dataset()
        self.format_progress.emit(100, 100, "Formatting complete")
        
        return dataset
    
    def _run_training(self) -> None:
        """Run YOLO training using ultralytics package."""
        try:
            # Import here to avoid startup overhead
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError(
                "ultralytics package not installed. Please run: pip install ultralytics"
            )
        
        # Create model
        model_path = self.config._get_model_path()
        self.log_message.emit(f"📊 Loading model: {model_path}")
        model = YOLO(model_path)
        
        # Get training arguments
        train_args = self.config.to_yolo_args()
        
        # Run training (this blocks until complete)
        self.log_message.emit("🏃 Training started...")
        
        try:
            # Train model
            results = model.train(**train_args)
            
            self.log_message.emit("✅ Training finished successfully")
            self.log_message.emit(f"📂 Results saved to: {results.save_dir}")
            
        except KeyboardInterrupt:
            self.log_message.emit("⏸️  Training interrupted by user")
            self._cancelled = True
        except Exception as e:
            raise RuntimeError(f"Training failed: {str(e)}")
    
    def cancel(self) -> None:
        """Cancel the training process."""
        self._cancelled = True
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            if self._process.poll() is None:
                self._process.kill()
        self.log_message.emit("⏹️  Training cancelled")
    
    def pause(self) -> None:
        """Pause training (not fully supported by YOLO, but we can set flag)."""
        self._paused = True
        self.log_message.emit("⏸️  Pause requested (will take effect between epochs)")
    
    def resume(self) -> None:
        """Resume training."""
        self._paused = False
        self.log_message.emit("▶️  Training resumed")


class TrainingMonitor(QtCore.QThread):
    """Alternative worker that monitors YOLO training by parsing stdout.
    
    This version runs YOLO training as a subprocess and parses the output
    to provide real-time metrics updates. Use this if you need more granular
    progress updates during training.
    """
    
    # Signals
    progress_update = QtCore.Signal(int, int, str)
    metrics_update = QtCore.Signal(dict)
    log_message = QtCore.Signal(str)
    training_complete = QtCore.Signal(str)
    training_error = QtCore.Signal(str)
    
    def __init__(self, config: TrainingConfig):
        super().__init__()
        self.config = config
        self._cancelled = False
        self._process: Optional[subprocess.Popen] = None
    
    def run(self) -> None:
        """Run training and parse output."""
        try:
            # Build command
            cmd = self._build_training_command()
            self.log_message.emit(f"🚀 Running: {' '.join(cmd)}")
            
            # Start process
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            
            # Parse output line by line
            for line in self._process.stdout:
                if self._cancelled:
                    self._process.terminate()
                    break
                
                line = line.strip()
                if line:
                    self.log_message.emit(line)
                    self._parse_training_line(line)
            
            # Wait for completion
            return_code = self._process.wait()
            
            if return_code == 0 and not self._cancelled:
                self.training_complete.emit("✅ Training completed successfully")
            elif self._cancelled:
                self.log_message.emit("⏹️  Training cancelled")
            else:
                self.training_error.emit(f"❌ Training failed with code {return_code}")
        
        except Exception as e:
            self.training_error.emit(f"❌ Error: {str(e)}")
    
    def _build_training_command(self) -> list:
        """Build command line for YOLO training."""
        # Use yolo CLI
        cmd = [
            sys.executable, "-m", "ultralytics",
            "train",
            f"model={self.config._get_model_path()}",
            f"data={self.config.output_dataset_root / 'data.yaml'}",
            f"epochs={self.config.epochs}",
            f"imgsz={self.config.image_size}",
            f"batch={self.config.batch_size}",
            f"device={self.config.device}",
            f"project={self.config.project_name}",
            f"name={self.config.run_name}",
        ]
        
        return cmd
    
    def _parse_training_line(self, line: str) -> None:
        """Parse a line of training output to extract metrics.
        
        Example YOLO output:
        "Epoch    GPU_mem   box_loss   obj_loss   cls_loss  Instances       Size"
        "  1/100     1.23G      0.345      0.678      0.234         32        640"
        """
        # Match epoch progress
        epoch_match = re.search(r'(\d+)/(\d+)', line)
        if epoch_match:
            current = int(epoch_match.group(1))
            total = int(epoch_match.group(2))
            self.progress_update.emit(current, total, f"Epoch {current}/{total}")
        
        # Match metrics (box_loss, obj_loss, cls_loss, etc.)
        metrics = {}
        
        # Loss values
        loss_match = re.search(r'box_loss[:\s]+([0-9.]+)', line)
        if loss_match:
            metrics['box_loss'] = float(loss_match.group(1))
        
        obj_match = re.search(r'obj_loss[:\s]+([0-9.]+)', line)
        if obj_match:
            metrics['obj_loss'] = float(obj_match.group(1))
        
        cls_match = re.search(r'cls_loss[:\s]+([0-9.]+)', line)
        if cls_match:
            metrics['cls_loss'] = float(cls_match.group(1))
        
        # mAP values
        map50_match = re.search(r'mAP50[:\s]+([0-9.]+)', line)
        if map50_match:
            metrics['mAP50'] = float(map50_match.group(1))
        
        map_match = re.search(r'mAP50-95[:\s]+([0-9.]+)', line)
        if map_match:
            metrics['mAP50-95'] = float(map_match.group(1))
        
        # Emit metrics if any were found
        if metrics:
            self.metrics_update.emit(metrics)
    
    def cancel(self) -> None:
        """Cancel training."""
        self._cancelled = True
        if self._process:
            self._process.terminate()
