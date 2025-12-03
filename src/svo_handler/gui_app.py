"""PySide6 GUI skeleton focused on frame extraction."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .config import DEFAULT_OUTPUT_ROOT, DEFAULT_TARGET_FPS, STREAM_LEFT, STREAM_RIGHT, DEPTH_MODES, DEFAULT_DEPTH_MODE
from .extraction import FrameExportWorker, ExportSummary
from .ingestion import SvoIngestor
from .export_paths import derive_export_dir, ensure_output_root_writable, OutputPathError
from .options import FrameExportOptions


class FrameExportWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVO2 Frame Exporter")
        self.resize(900, 600)

        self.options = FrameExportOptions(
            svo_path=Path(),
            output_root=DEFAULT_OUTPUT_ROOT,
            stream=STREAM_LEFT,
            target_fps=DEFAULT_TARGET_FPS,
        )

        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout()

        file_row = QtWidgets.QHBoxLayout()
        self.svo_path_edit = QtWidgets.QLineEdit()
        self.svo_path_edit.setPlaceholderText("Pfad zur .svo2 Datei")
        browse_btn = QtWidgets.QPushButton("Browse…")
        file_row.addWidget(QtWidgets.QLabel("SVO2 Datei:"))
        file_row.addWidget(self.svo_path_edit)
        file_row.addWidget(browse_btn)

        output_root_row = QtWidgets.QHBoxLayout()
        self.output_root_edit = QtWidgets.QLineEdit(str(DEFAULT_OUTPUT_ROOT))
        self.output_root_edit.setPlaceholderText("Export-Root (z.B. gemounteter USB-Stick)")
        output_root_btn = QtWidgets.QPushButton("Ordner wählen…")
        output_root_row.addWidget(QtWidgets.QLabel("Export-Root:"))
        output_root_row.addWidget(self.output_root_edit)
        output_root_row.addWidget(output_root_btn)

        metadata_row = QtWidgets.QHBoxLayout()
        self.source_fps_label = QtWidgets.QLabel("Source FPS: unbekannt")
        self.resolution_label = QtWidgets.QLabel("Auflösung: -")
        self.file_size_label = QtWidgets.QLabel("Dateigröße: -")
        self.total_frames_label = QtWidgets.QLabel("Frames gesamt: -")
        metadata_row.addWidget(self.source_fps_label)
        metadata_row.addWidget(self.resolution_label)
        metadata_row.addWidget(self.file_size_label)
        metadata_row.addWidget(self.total_frames_label)

        stream_row = QtWidgets.QHBoxLayout()
        stream_row.addWidget(QtWidgets.QLabel("Stream:"))
        self.left_radio = QtWidgets.QRadioButton("Left")
        self.right_radio = QtWidgets.QRadioButton("Right")
        self.left_radio.setChecked(True)
        stream_row.addWidget(self.left_radio)
        stream_row.addWidget(self.right_radio)
        stream_row.addStretch()

        fps_group = QtWidgets.QGroupBox("Ziel-FPS (keine Downscaling der Auflösung)")
        fps_layout = QtWidgets.QVBoxLayout()
        self.target_fps_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.target_fps_slider.setMinimum(1)
        self.target_fps_slider.setMaximum(60)
        self.target_fps_slider.setValue(DEFAULT_TARGET_FPS)
        self.target_fps_value = QtWidgets.QLabel(f"Target FPS: {DEFAULT_TARGET_FPS}")
        self.skip_value = QtWidgets.QLabel("Keep every: 1 (source FPS unbekannt)")
        self.depth_checkbox = QtWidgets.QCheckBox("Depth (32-bit .npy) mit exportieren")
        self.depth_checkbox.setChecked(False)
        depth_mode_row = QtWidgets.QHBoxLayout()
        depth_mode_row.addWidget(QtWidgets.QLabel("Depth Mode:"))
        self.depth_mode_combo = QtWidgets.QComboBox()
        self.depth_mode_combo.addItems(DEPTH_MODES)
        default_index = self.depth_mode_combo.findText(DEFAULT_DEPTH_MODE)
        if default_index >= 0:
            self.depth_mode_combo.setCurrentIndex(default_index)
        depth_mode_row.addWidget(self.depth_mode_combo)
        depth_mode_row.addStretch()
        fps_layout.addWidget(self.target_fps_value)
        fps_layout.addWidget(self.target_fps_slider)
        fps_layout.addWidget(self.skip_value)
        fps_layout.addWidget(self.depth_checkbox)
        fps_layout.addLayout(depth_mode_row)
        fps_group.setLayout(fps_layout)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        actions_row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Frames exportieren")
        self.stop_btn = QtWidgets.QPushButton("Stopp")
        self.stop_btn.setEnabled(False)
        self.status_label = QtWidgets.QLabel("Bereit.")
        self.warning_label = QtWidgets.QLabel("")
        self.warning_label.setStyleSheet("color: orange;")
        actions_row.addWidget(self.start_btn)
        actions_row.addWidget(self.stop_btn)
        actions_row.addWidget(self.status_label)
        actions_row.addWidget(self.warning_label)
        actions_row.addStretch()

        preview_group = QtWidgets.QGroupBox("Aktuelles exportiertes Frame")
        preview_layout = QtWidgets.QVBoxLayout()
        self.preview_label = QtWidgets.QLabel("Noch kein Frame angezeigt.")
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setMinimumHeight(250)
        self.preview_label.setFrameStyle(QtWidgets.QFrame.Box)
        preview_layout.addWidget(self.preview_label)
        preview_group.setLayout(preview_layout)

        layout.addLayout(file_row)
        layout.addLayout(output_root_row)
        layout.addLayout(metadata_row)
        layout.addLayout(stream_row)
        layout.addWidget(fps_group)
        layout.addWidget(self.progress_bar)
        layout.addLayout(actions_row)
        layout.addWidget(preview_group)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._browse_btn = browse_btn
        self._output_root_btn = output_root_btn

    def _wire_signals(self) -> None:
        self._browse_btn.clicked.connect(self._choose_file)
        self._output_root_btn.clicked.connect(self._choose_output_root)
        self.target_fps_slider.valueChanged.connect(self._on_target_fps_changed)
        self.start_btn.clicked.connect(self._start_export)
        self.stop_btn.clicked.connect(self._stop_export)
        self.left_radio.toggled.connect(self._on_stream_changed)
        self.svo_path_edit.textChanged.connect(self._on_svo_path_changed)
        self.output_root_edit.textChanged.connect(self._on_output_root_changed)
        self.depth_checkbox.stateChanged.connect(self._on_depth_changed)
        self.depth_mode_combo.currentTextChanged.connect(self._on_depth_mode_changed)

    def _choose_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "SVO2 Datei wählen", "", "SVO2 Files (*.svo2);;All Files (*)"
        )
        if file_path:
            self.svo_path_edit.setText(file_path)

    def _choose_output_root(self) -> None:
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Export-Root wählen", str(DEFAULT_OUTPUT_ROOT))
        if dir_path:
            self.output_root_edit.setText(dir_path)

    def _on_stream_changed(self) -> None:
        self.options.stream = STREAM_LEFT if self.left_radio.isChecked() else STREAM_RIGHT

    def _on_svo_path_changed(self, text: str) -> None:
        path = Path(text)
        self.options.svo_path = path
        if path.exists():
            self._load_metadata(path)
        else:
            self.source_fps_label.setText("Source FPS: unbekannt")
            self.resolution_label.setText("Auflösung: -")
            self.file_size_label.setText("Dateigröße: -")
            self.total_frames_label.setText("Frames gesamt: -")

    def _on_output_root_changed(self, text: str) -> None:
        root = Path(text) if text else DEFAULT_OUTPUT_ROOT
        self.options.output_root = root

    def _on_target_fps_changed(self, value: int) -> None:
        self.options.target_fps = value
        self.target_fps_value.setText(f"Target FPS: {value}")
        self._update_keep_every_label()

    def _on_depth_changed(self, state: int) -> None:
        self.options.export_depth = state == QtCore.Qt.Checked
        self.depth_mode_combo.setEnabled(self.options.export_depth)

    def _on_depth_mode_changed(self, text: str) -> None:
        self.options.depth_mode = text

    def _update_keep_every_label(self) -> None:
        interval = self.options.keep_every
        source_fps = self.options.source_fps or 0
        if source_fps > 0:
            self.skip_value.setText(f"Keep every: {interval} (Quelle: {source_fps} FPS)")
        else:
            self.skip_value.setText(f"Keep every: {interval} (source FPS unbekannt)")

    def _start_export(self) -> None:
        if not self.options.svo_path or not self.options.svo_path.exists():
            self.status_label.setText("SVO2 Datei fehlt oder ungültig.")
            return

        # Sync options from current UI state
        self.options.export_depth = self.depth_checkbox.isChecked()
        self.options.depth_mode = self.depth_mode_combo.currentText()

        try:
            ensure_output_root_writable(self.options.output_root)
        except OutputPathError as exc:
            self.status_label.setText(str(exc))
            return

        export_dir = derive_export_dir(self.options.svo_path, self.options.output_root)
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.status_label.setText(f"Export-Pfad kann nicht angelegt werden: {exc}")
            return

        self.status_label.setText("Export läuft…")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.warning_label.setText("")
        self.progress_bar.setValue(0)

        self.worker = FrameExportWorker(self.options)
        self.worker.progress.connect(self._on_progress)
        self.worker.progress_ratio.connect(self._on_progress_ratio)
        self.worker.frame_saved.connect(self._on_frame_saved)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _stop_export(self) -> None:
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("Stop wird ausgeführt…")
            self.stop_btn.setEnabled(False)

    def _update_preview(self, frame_path: Path) -> None:
        if not frame_path.exists():
            self.preview_label.setText("Kein exportiertes Frame gefunden.")
            return

        pixmap = QtGui.QPixmap(str(frame_path))
        if pixmap.isNull():
            self.preview_label.setText(f"Konnte Frame nicht laden: {frame_path.name}")
            return

        scaled = pixmap.scaled(
            self.preview_label.width(),
            self.preview_label.height(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def _on_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_progress_ratio(self, ratio: float) -> None:
        self.progress_bar.setValue(int(ratio * 100))

    def _on_frame_saved(self, frame_path: str) -> None:
        self._update_preview(Path(frame_path))

    def _on_finished(self, success: bool, summary: ExportSummary, error_message: str) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if success:
            if error_message:
                self.status_label.setText(error_message)
            else:
                self.status_label.setText(f"Fertig: {summary.frames_written} Frames.")
            if summary.warning:
                self.warning_label.setText(summary.warning)
            if summary.last_frame_path:
                self._update_preview(summary.last_frame_path)
        else:
            self.status_label.setText(f"Fehler: {error_message}")
            if summary.warning:
                self.warning_label.setText(summary.warning)

    def _load_metadata(self, path: Path) -> None:
        # Clear preview when loading new SVO2
        self.preview_label.clear()
        self.preview_label.setText("Noch kein Frame angezeigt.")
        
        try:
            self.status_label.setText("SVO wird geladen… bitte warten.")
            QtWidgets.QApplication.processEvents()
            meta = SvoIngestor(path).metadata()
        except Exception as exc:
            self.source_fps_label.setText(f"Source FPS: Fehler ({exc})")
            return

        self.options.source_fps = meta.fps
        self.options.total_frames = meta.total_frames
        if meta.fps:
            self.source_fps_label.setText(f"Source FPS: {meta.fps}")
            self.target_fps_slider.setMaximum(meta.fps)
            if self.options.target_fps > meta.fps:
                self.options.target_fps = meta.fps
                self.target_fps_slider.setValue(meta.fps)
        else:
            self.source_fps_label.setText("Source FPS: unbekannt")

        if meta.resolution:
            self.resolution_label.setText(f"Auflösung: {meta.resolution[0]}x{meta.resolution[1]}")
        else:
            self.resolution_label.setText("Auflösung: -")

        if meta.file_size_bytes:
            mb = meta.file_size_bytes / (1024 * 1024)
            self.file_size_label.setText(f"Dateigröße: {mb:.1f} MB")
        else:
            self.file_size_label.setText("Dateigröße: -")

        total_frames = meta.total_frames
        if not total_frames:
            self.status_label.setText("Frames zählen… (siehe auch Konsole)")
            QtWidgets.QApplication.processEvents()
            
            # Progress callback for frame counting
            def count_progress(count):
                print(f"  Gezählte Frames: {count}", flush=True)
                self.status_label.setText(f"Frames zählen… {count} bisher")
                QtWidgets.QApplication.processEvents()
            
            total_frames = SvoIngestor.fast_count_frames(path, progress_callback=count_progress)

        if total_frames:
            self.total_frames_label.setText(f"Frames gesamt: {total_frames}")
            self.options.total_frames = total_frames
        else:
            self.total_frames_label.setText("Frames gesamt: -")

        self.status_label.setText("Bereit.")
        self._update_keep_every_label()


def run() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = FrameExportWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
