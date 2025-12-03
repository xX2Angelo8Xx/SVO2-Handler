"""Helpers for deriving deterministic export paths for frame extraction."""
from pathlib import Path
from typing import Optional

from .config import DEFAULT_OUTPUT_ROOT


class OutputPathError(Exception):
    """Raised when the export output location is not writable or cannot be created."""


def derive_export_dir(svo_path: Path, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    """Build the export directory based on source folder and file name.

    Pattern: output_root/<source_parent>_RAW_<svo_stem>/
    Example: /media/angelo/DRONE_DATA/flight_20251027_132504/video.svo2
             -> /media/angelo/DRONE_DATA/SVO2_Frame_Export/flight_20251027_132504_RAW_video
    """
    if not svo_path.name:
        raise ValueError("SVO path must include a file name")

    parent_name = svo_path.parent.name or "export"
    stem = svo_path.stem
    export_dir_name = f"{parent_name}_RAW_{stem}"
    return output_root / export_dir_name


def ensure_output_root_writable(output_root: Path) -> None:
    """Ensure the export root exists and is writable; raise OutputPathError otherwise."""
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise OutputPathError(
            f"Kein Schreibzugriff auf {output_root}. Bitte Mount/Permissions prüfen."
        ) from exc
    except FileNotFoundError as exc:
        raise OutputPathError(
            f"Export-Pfad {output_root} existiert nicht (Medium nicht gemountet?)."
        ) from exc

    test_file = output_root / ".write_test"
    try:
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except Exception as exc:
        raise OutputPathError(
            f"Export-Pfad {output_root} ist nicht beschreibbar. Bitte Ziel wählen oder Mount prüfen."
        ) from exc


def latest_frame_in_dir(export_dir: Path) -> Optional[Path]:
    """Return the most recently modified frame file (jpg/png) in the export dir."""
    if not export_dir.exists() or not export_dir.is_dir():
        return None

    candidates = list(export_dir.glob("*.jpg")) + list(export_dir.glob("*.png"))
    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)
