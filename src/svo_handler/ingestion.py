"""SVO ingestion helpers using ZED SDK."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import os

try:
    import pyzed.sl as sl  # type: ignore
except ImportError:  # pragma: no cover
    sl = None  # Allow module import even when ZED SDK is not installed locally.


@dataclass
class SvoMetadata:
    path: Path
    fps: Optional[int]
    resolution: Optional[Tuple[int, int]]
    total_frames: Optional[int]
    file_size_bytes: Optional[int]


class SvoIngestor:
    """Lightweight wrapper to read SVO metadata and iterate frames."""

    def __init__(self, svo_path: Path):
        if sl is None:
            raise RuntimeError("ZED SDK (python-sl) is required for ingestion.")
        self.svo_path = Path(svo_path)
        self._camera = sl.Camera()

    def open(self) -> None:
        init_params = sl.InitParameters()
        init_params.set_from_svo_file(str(self.svo_path))
        init_params.coordinate_units = sl.UNIT.METER
        init_params.depth_mode = sl.DEPTH_MODE.NONE

        err = self._camera.open(init_params)
        if err != sl.ERROR_CODE.SUCCESS:
            raise RuntimeError(f"Failed to open SVO: {err}")

    def close(self) -> None:
        try:
            self._camera.close()
        except Exception:
            pass

    def metadata(self) -> SvoMetadata:
        self.open()
        fps: Optional[int] = None
        resolution: Optional[Tuple[int, int]] = None
        total_frames: Optional[int] = None
        file_size_bytes: Optional[int] = None
        try:
            info = self._camera.get_camera_information()
            try:
                fps = info.camera_configuration.fps
            except Exception:
                fps = None
            try:
                resolution = (
                    info.camera_configuration.resolution.width,
                    info.camera_configuration.resolution.height,
                )
            except Exception:
                resolution = None
            try:
                total_frames = info.svo_streaming.total_frames
            except Exception:
                total_frames = None
            try:
                file_size_bytes = info.input_type.get_svo_file_size()
            except Exception:
                file_size_bytes = None
        finally:
            self.close()

        # Fallbacks
        if file_size_bytes is None:
            try:
                file_size_bytes = os.stat(self.svo_path).st_size
            except Exception:
                file_size_bytes = None

        return SvoMetadata(
            path=self.svo_path,
            fps=fps,
            resolution=resolution,
            total_frames=total_frames,
            file_size_bytes=file_size_bytes,
        )

    @staticmethod
    def fast_count_frames(svo_path: Path, progress_callback=None) -> Optional[int]:
        """Count frames by scanning the SVO when metadata does not provide a total.

        Uses `get_svo_number_of_frames` if available; otherwise performs a quick grab loop.
        Optionally calls progress_callback(count) every 100 frames during counting.
        Returns None on failure.
        """
        if sl is None:
            return None

        try:
            cam = sl.Camera()
            init_params = sl.InitParameters()
            init_params.set_from_svo_file(str(svo_path))
            init_params.coordinate_units = sl.UNIT.METER
            init_params.depth_mode = sl.DEPTH_MODE.NONE
            if cam.open(init_params) != sl.ERROR_CODE.SUCCESS:
                return None

            # Prefer direct API if present
            if hasattr(cam, "get_svo_number_of_frames"):
                try:
                    total = cam.get_svo_number_of_frames()
                    cam.close()
                    return int(total)
                except Exception:
                    pass

            count = 0
            if progress_callback:
                print(f"Counting frames in {svo_path.name}...", flush=True)
            while cam.grab() == sl.ERROR_CODE.SUCCESS:
                count += 1
                if progress_callback and count % 100 == 0:
                    progress_callback(count)
            cam.close()
            if progress_callback:
                print(f"Total frames counted: {count}", flush=True)
            return count
        except Exception:
            return None
