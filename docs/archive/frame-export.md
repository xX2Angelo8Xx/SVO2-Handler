# Frame Export Plan (GUI Skeleton)

Goal: fast path to test frame extraction from `.svo2` without downscaling resolution. GUI will drive stream choice, target FPS, and output to the DRONE_DATA USB stick.

## Output layout
- Base path: `/media/angelo/DRONE_DATA/SVO2_Frame_Export`
- Derived export folder: `<source_parent>_RAW_<svo_filename_without_ext>`
  - Example: `/media/angelo/DRONE_DATA/flight_20251027_132504/video.svo2`
    -> `/media/angelo/DRONE_DATA/SVO2_Frame_Export/flight_20251027_132504_RAW_video`
- Frames stored at full capture resolution (no downscaling). Filenames use sequential numbering (`frame_000000.jpg` planned).

## GUI (PySide6) — current state
- File picker for `.svo2`.
- Stream toggle: Left / Right.
- Target FPS slider; when metadata is available, the slider caps at source FPS and shows keep-every-N (downsample by skipping only, never resize).
- Status/progress surface and “Start export” action wired to the extraction worker.
- Preview area: loads the last exported frame from the derived export folder after extraction completes.
- Metadata display: source FPS and resolution loaded via SVO ingestion (ZED SDK required).

## Extraction rules
- No resolution changes; write raw camera resolution frames.
- Downsample via frame skipping only (`keep_every` derived from source FPS and target FPS).
- Keep per-frame decode failures non-fatal where possible; log and continue.
- Before export: ensure output directory exists under the derived path; warn if target filesystem is FAT32 or low on free space (future).

## Implementation notes
- Extraction uses ZED SDK Python bindings (`sl`) and OpenCV. Frames are saved as JPG (BGRA→BGR) with sequential numbering. No resolution downscaling.
- Keep-every-N derived from source/target FPS. If source FPS unknown, defaults to no skipping.
- Manifest (`manifest.json`) recorded in each export folder with source/target FPS, stream, keep-every.
- Best-effort filesystem checks warn on FAT32 and low free space (<500MB).

## Next steps
- Add cancellation UI and progress bar updates.
- Expand manifest (timestamps, duration, storage info) and expose FPS-downsample math for tests.
- Add error surfacing for missing ZED SDK and improve validation of paths/output permissions.***
