# Learnings from Drone Field Test (Producer of SVO2 Files)

Context: Source `.svo2` files come from a Jetson Orin Nano + ZED 2i stack (see `/home/angelo/Projects/Drone-Fieldtest`). These notes capture the most relevant operational constraints and patterns to inform the SVO2 Handler design.

## Capture & Encoding
- Recordings use ZED SDK 4.x in LOSSLESS mode only (NVENC/H.264/H.265 not available on Orin Nano). Expect large files (HD720@60 ≈ ~26 MB/s; ~10 GB per 4 minutes).
- Source FPS commonly 30 or 60; always read metadata from the SVO header and surface it in the UI before configuring extraction/downsampling.
- CORRUPTED_FRAME warnings were treated as non-fatal during capture; downstream extraction should log and continue if individual frames fail to decode.

## Filesystem & Storage
- FAT32 has a hard 4GB limit; corruption occurs beyond ~4.29GB. Field stack enforced a 3.75GB safety cap. Prefer NTFS/exFAT for both recording and large exports.
- When writing many frames/depth dumps, validate available space and warn if output targets FAT32 or low-free-space volumes.

## Extraction Patterns
- Downsampling used simple frame skipping (`grab` loop, modulo on frame index). UI slider should map target FPS to skip interval against source FPS (e.g., 60→10 FPS = keep every 6th frame).
- Left camera was the default training source; keep explicit left/right choice in the UI and in output path naming.
- Prior tool wrote organized folders derived from flight/session name; mimic clear, deterministic output structure (session/stream/frame_xxxxxx.jpg) and include a manifest.

## Depth Data
- Raw depth exports were stored as float32 arrays preceded by a small header (int width, int height, int frame_number), one file per frame. Visualization used jet colormap with invalid depth (NaN/Inf/<=0) set to black.
- Depth mode selection is important: match the capture depth model when possible, and surface the chosen model in manifests for training provenance.

## Concurrency & Robustness
- Monitor/worker loops must break on STOPPING to avoid deadlocks (avoid `continue` inside stop branches); join worker threads from the controller, not from within the workers.
- Keep UI-responsive by offloading decode/write work to workers with bounded queues; provide cancellation that drains gracefully.

For the full upstream rationale, see `docs/CRITICAL_LEARNINGS_v1.3.md` in the Drone-Fieldtest repository.
