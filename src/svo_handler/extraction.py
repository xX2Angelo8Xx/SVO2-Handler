"""Frame extraction worker built on ZED SDK and OpenCV."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6 import QtCore

from .config import STREAM_LEFT, STREAM_RIGHT, DEPTH_MODES, DEFAULT_DEPTH_MODE
from .export_paths import derive_export_dir
from .ingestion import SvoIngestor, sl
from .options import FrameExportOptions


@dataclass
class ExportSummary:
    frames_written: int
    output_dir: Path
    last_frame_path: Optional[Path]
    manifest_path: Optional[Path]
    warning: Optional[str] = None


def _fs_type(path: Path) -> Optional[str]:
    """Best-effort filesystem type detection."""
    try:
        result = subprocess.run(
            ["findmnt", "-n", "-o", "FSTYPE", "--target", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _has_min_free_space(path: Path, min_bytes: int) -> bool:
    usage = shutil.disk_usage(path)
    return usage.free >= min_bytes


class FrameExportWorker(QtCore.QThread):
    progress = QtCore.Signal(str)
    frame_saved = QtCore.Signal(str)
    progress_ratio = QtCore.Signal(float)
    finished = QtCore.Signal(bool, ExportSummary, str)

    def __init__(self, options: FrameExportOptions, parent=None) -> None:
        super().__init__(parent)
        self.options = options
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            summary = self._export_frames()
            self.finished.emit(not self._cancelled, summary, "Abgebrochen" if self._cancelled else "")
        except Exception as exc:  # pragma: no cover - runtime path
            summary = ExportSummary(
                frames_written=0, output_dir=self.options.output_root, last_frame_path=None, manifest_path=None
            )
            self.finished.emit(False, summary, str(exc))

    def _export_frames(self) -> ExportSummary:
        if sl is None:
            raise RuntimeError("ZED SDK (python-sl) ist nicht installiert.")

        export_dir = derive_export_dir(self.options.svo_path, self.options.output_root)
        export_dir.mkdir(parents=True, exist_ok=True)

        # Filesystem checks (best-effort warnings)
        warning = None
        fstype = _fs_type(export_dir)
        if fstype and fstype.lower() in {"vfat", "msdos", "fat32"}:
            warning = "Warnung: FAT32 erkannt – Export kann bei großen Dateien scheitern."
        if not _has_min_free_space(export_dir, min_bytes=500 * 1024 * 1024):
            warning = (warning + " " if warning else "") + "Warnung: Wenig freier Speicher (<500MB)."

        if self._cancelled:
            return ExportSummary(0, export_dir, None, None, warning)

        ingestor = SvoIngestor(self.options.svo_path)
        init_params = sl.InitParameters()
        init_params.set_from_svo_file(str(self.options.svo_path))
        init_params.coordinate_units = sl.UNIT.METER
        init_params.depth_mode = self._resolve_depth_mode(self.options.depth_mode) if self.options.export_depth else sl.DEPTH_MODE.NONE
        if ingestor._camera.open(init_params) != sl.ERROR_CODE.SUCCESS:
            raise RuntimeError("SVO Open failed.")
        camera = ingestor._camera  # direct access for grab/retrieve
        info = camera.get_camera_information()
        total_frames = self.options.total_frames
        if not total_frames:
            try:
                total_frames = info.svo_streaming.total_frames
            except Exception:
                total_frames = None

        keep_every = self.options.keep_every
        stream_view = STREAM_LEFT if self.options.stream == STREAM_LEFT else STREAM_RIGHT
        view_enum = sl.VIEW.LEFT if stream_view == STREAM_LEFT else sl.VIEW.RIGHT

        zed_mat = sl.Mat()
        depth_mat = sl.Mat()
        frame_idx = 0  # Index of successfully grabbed frames (NOT theoretical timestamp)
        written = 0
        last_frame_path: Optional[Path] = None

        self.progress.emit(f"Export nach {export_dir} gestartet (keep every {keep_every}).")
        self.progress.emit("Hinweis: Zählt nur existierende Frames (dropped frames werden automatisch übersprungen).")

        try:
            while not self._cancelled and camera.grab() == sl.ERROR_CODE.SUCCESS:
                # frame_idx counts only successfully grabbed frames (dropped frames don't increment it)
                # So keep_every correctly spaces exports even if source has frame drops
                if frame_idx % keep_every == 0:
                    try:
                        if camera.retrieve_image(zed_mat, view_enum) == sl.ERROR_CODE.SUCCESS:
                            np_img = zed_mat.get_data()  # BGRA
                            bgr = cv2.cvtColor(np_img, cv2.COLOR_BGRA2BGR)
                            filename = export_dir / f"frame_{written:06d}.jpg"
                            if cv2.imwrite(str(filename), bgr):
                                written += 1
                                last_frame_path = filename
                                self.frame_saved.emit(str(filename))
                                # Optional depth export
                                if self.options.export_depth:
                                    if camera.retrieve_measure(depth_mat, sl.MEASURE.DEPTH) == sl.ERROR_CODE.SUCCESS:
                                        depth_data = depth_mat.get_data()
                                        depth_filename = export_dir / f"frame_{written-1:06d}.npy"
                                        np.save(depth_filename, depth_data)
                                if total_frames:
                                    self.progress_ratio.emit(min(1.0, frame_idx / max(1, total_frames)))
                                if written % 100 == 0:
                                    self.progress.emit(f"{written} Frames gespeichert…")
                        else:
                            self.progress.emit(f"Frame {frame_idx} konnte nicht gelesen werden (weiter).")
                    except Exception as exc:
                        self.progress.emit(f"Frame {frame_idx} Fehler: {exc} (weiter).")
                frame_idx += 1
        finally:
            ingestor.close()

        if total_frames:
            self.progress_ratio.emit(1.0)

        manifest_path = export_dir / "manifest.json"
        resolution = None
        if info and getattr(info, "camera_configuration", None):
            res = info.camera_configuration.resolution
            try:
                resolution = {"width": res.width, "height": res.height}
            except Exception:
                resolution = None

        # If total_frames unknown, fall back to processed count
        total_frames_manifest = total_frames if total_frames is not None else frame_idx

        manifest = {
            "source_svo": str(self.options.svo_path),
            "stream": stream_view,
            "source_fps": self.options.source_fps,
            "target_fps": self.options.target_fps,
            "keep_every": keep_every,
            "frames_written": written,
            "total_frames_seen": total_frames_manifest,
            "resolution": resolution,
            "export_depth": self.options.export_depth,
            "depth_mode": self.options.depth_mode,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        self.progress.emit(f"Fertig: {written} Frames geschrieben.")
        return ExportSummary(
            frames_written=written,
            output_dir=export_dir,
            last_frame_path=last_frame_path,
            manifest_path=manifest_path,
            warning=warning,
        )

    @staticmethod
    def _resolve_depth_mode(name: str):
        """Map string depth mode to pyzed depth mode with safe fallback."""
        if not name:
            name = DEFAULT_DEPTH_MODE
        upper = name.upper()
        mode_map = {
            "NEURAL_PLUS": getattr(sl.DEPTH_MODE, "NEURAL_PLUS", getattr(sl.DEPTH_MODE, "NEURAL", sl.DEPTH_MODE.PERFORMANCE)),
            "NEURAL": getattr(sl.DEPTH_MODE, "NEURAL", getattr(sl.DEPTH_MODE, "NEURAL_PLUS", sl.DEPTH_MODE.PERFORMANCE)),
            "ULTRA": getattr(sl.DEPTH_MODE, "ULTRA", sl.DEPTH_MODE.QUALITY),
            "QUALITY": getattr(sl.DEPTH_MODE, "QUALITY", sl.DEPTH_MODE.PERFORMANCE),
            "PERFORMANCE": getattr(sl.DEPTH_MODE, "PERFORMANCE", sl.DEPTH_MODE.NONE),
            "NONE": sl.DEPTH_MODE.NONE,
        }
        return mode_map.get(upper, mode_map[DEFAULT_DEPTH_MODE])
