# Viewer/Annotator Plan

Goal: GUI to browse folders with paired RGB + depth (`.npy`) files, visualize depth with adjustable min/max (in meters), zoom/pan, select AOI rectangles, compute mean depth, and rename JPGs with category + depth info.

## Core features
- Folder open dialog; load first RGB/depth pair automatically (same basename).
- Depth visualization: load `.npy`, apply colormap with user-set min/max sliders; real-time update.
- Navigation: next/previous frame buttons.
- Zoom/pan on depth view.
- AOI tool: draw rectangle, compute mean depth, display value.
- Confirm action: rename JPG to include depth mean and selected category tokens.
- Category selection: dropdown for main (S, SE, E, NE, N, NW, W, SW) and sub (Bot, Horizon, Top).

## File expectations
- Paired files: `frame_000000.jpg` with `frame_000000.npy` in the same folder.
- Depth stored as float32 in `.npy`.

## Rename pattern (proposal)
- `{basename}__{main}_{sub}__depth-{mean_m:.2f}m.jpg`
  - Example: `frame_000123__NE_Top__depth-12.45m.jpg`

## Tech stack
- PySide6 for GUI.
- NumPy + OpenCV/Matplotlib for depth rendering.

## Next steps
- Scaffold `viewer_app.py` with file picker, image/depth panes, min/max sliders, category dropdowns, and AOI placeholder.
- Implement depth render pipeline (min/max sliders → colormap).
- Add AOI rectangle tool + mean computation and rename action.***
