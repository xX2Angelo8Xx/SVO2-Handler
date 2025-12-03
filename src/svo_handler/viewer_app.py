"""Viewer/Annotator skeleton for RGB + depth pairs."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import cv2
from PIL import Image

from .training_export import (
    bucket_from_meta,
    append_csv,
    target_dir,
    ensure_bucket_structure,
    ensure_dir,
)
from .config import DEFAULT_TRAINING_ROOT


class BenchmarkWorker(QtCore.QThread):
    """Worker thread to scan source folder and copy unannotated images to benchmark folder."""
    
    progress = QtCore.Signal(int, int, str)  # (current, total, status_msg)
    finished = QtCore.Signal(int)  # (total_copied)
    error = QtCore.Signal(str)  # (error_msg)
    
    def __init__(self, source_folder: Path, training_root: Path):
        super().__init__()
        self.source_folder = source_folder
        self.training_root = training_root
        self._cancelled = False
    
    def cancel(self) -> None:
        self._cancelled = True
    
    def run(self) -> None:
        """Scan source folder for images not yet annotated in training root, copy to benchmark/."""
        try:
            benchmark_dir = self.training_root / "benchmark"
            benchmark_dir.mkdir(parents=True, exist_ok=True)
            
            # Find all image files in source folder
            all_images = []
            for pattern in ["*.jpg", "*.jpeg", "*.png"]:
                all_images.extend(self.source_folder.glob(pattern))
            
            total_images = len(all_images)
            unannotated = []
            
            # Get source folder name for matching exported files
            source_folder_name = self.source_folder.name
            
            # Phase 1: Find images that haven't been annotated
            self.progress.emit(0, total_images, "Suche nicht-annotierte Frames...")
            for i, img_path in enumerate(all_images):
                if self._cancelled:
                    return
                
                # Check if this frame has been exported to ANY bucket in training root
                # Exported files have format: frame_NNNNNN-<source_folder>-*
                base_name = img_path.stem  # e.g., "frame_000123"
                pattern = f"{base_name}-{source_folder_name}-*{img_path.suffix}"
                
                # Search in all buckets (including 0_far and negative_samples)
                found_annotation = False
                for exported_file in self.training_root.rglob(pattern):
                    # Check if it's in benchmark folder (skip those)
                    if "benchmark" not in exported_file.parts:
                        found_annotation = True
                        break
                
                if not found_annotation:
                    unannotated.append(img_path)
                
                if i % 10 == 0:  # Update progress every 10 images
                    self.progress.emit(i, total_images, f"Gescannt: {i}/{total_images}")
            
            # Phase 2: Copy unannotated images to benchmark/
            total_to_copy = len(unannotated)
            self.progress.emit(0, total_to_copy, f"{total_to_copy} nicht-annotierte Frames gefunden")
            
            copied = 0
            for i, img_path in enumerate(unannotated):
                if self._cancelled:
                    return
                
                # Target filename: frame_NNNNNN-<source_folder>-unannotated.jpg
                target_name = f"{img_path.stem}-{source_folder_name}-unannotated{img_path.suffix}"
                target_path = benchmark_dir / target_name
                
                # Skip if already exists (avoid re-copying)
                if not target_path.exists():
                    target_path.write_bytes(img_path.read_bytes())
                    copied += 1
                
                if i % 10 == 0:  # Update progress every 10 copies
                    self.progress.emit(i, total_to_copy, f"Kopiert: {i}/{total_to_copy}")
                    copied += 1
                
                if i % 10 == 0:  # Update progress every 10 copies
                    self.progress.emit(i, total_to_copy, f"Kopiert: {i}/{total_to_copy}")
            
            self.finished.emit(copied)
            
        except Exception as e:
            self.error.emit(str(e))


class AspectRatioWidget(QtWidgets.QWidget):
    """Container that maintains a fixed aspect ratio for its child widget."""
    
    resized = QtCore.Signal()  # Emitted after child geometry is updated

    def __init__(self, child: QtWidgets.QWidget, aspect_ratio: float = 16 / 9, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._aspect_ratio = aspect_ratio
        self._child = child
        child.setParent(self)
        # Don't set minimum on container - let it be flexible

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_child_geometry()
        self.resized.emit()

    def _update_child_geometry(self) -> None:
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        # Calculate the largest 16:9 rect that fits
        target_h = int(w / self._aspect_ratio)
        if target_h <= h:
            # Width-constrained
            child_w = w
            child_h = target_h
        else:
            # Height-constrained
            child_h = h
            child_w = int(h * self._aspect_ratio)
        # Center the child
        x = (w - child_w) // 2
        y = (h - child_h) // 2
        self._child.setGeometry(x, y, child_w, child_h)

    def child_widget(self) -> QtWidgets.QWidget:
        return self._child

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(800, 450)  # 16:9 preferred size


class SelectableLabel(QtWidgets.QLabel):
    """Label with rubberband selection, move, and resize."""

    selection_changed = QtCore.Signal(QtCore.QRect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rubberband: Optional[QtWidgets.QRubberBand] = None
        self._origin: Optional[QtCore.QPoint] = None
        self._mode: Optional[str] = None  # new, move, resize
        self._handle: Optional[str] = None
        self._rect: Optional[QtCore.QRect] = None
        self.setMouseTracking(True)  # Enable mouse tracking for cursor updates

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return
        pos = event.position().toPoint()
        if self._rect and self._rect.adjusted(-8, -8, 8, 8).contains(pos):
            if self._near_corner(pos, self._rect) or self._near_edge(pos, self._rect):
                self._mode = "resize"
                self._handle = self._get_resize_handle(pos, self._rect)
            else:
                self._mode = "move"
                self._origin = pos
        else:
            self._mode = "new"
            self._origin = pos
            self._rect = QtCore.QRect(pos, QtCore.QSize())
        if self._rubberband is None:
            self._rubberband = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._rubberband.setGeometry(self._rect or QtCore.QRect())
        self._rubberband.show()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        pos = event.position().toPoint()
        
        # Update cursor based on position (visual feedback)
        if self._rect and self._mode is None:
            if self._near_corner(pos, self._rect) or self._near_edge(pos, self._rect):
                handle = self._get_resize_handle(pos, self._rect)
                self._set_cursor_for_handle(handle)
            elif self._rect.contains(pos):
                self.setCursor(QtCore.Qt.SizeAllCursor)  # Move cursor
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
        
        if not self._rubberband:
            return
            
        if self._mode == "new" and self._origin:
            rect = QtCore.QRect(self._origin, pos).normalized()
            self._rect = rect
            self._rubberband.setGeometry(rect)
        elif self._mode == "move" and self._rect and self._origin:
            delta = pos - self._origin
            moved = self._rect.translated(delta)
            self._rect = self._clamp_rect(moved)
            self._rubberband.setGeometry(self._rect)
            self._origin = pos
        elif self._mode == "resize" and self._rect and self._handle:
            rect = QtCore.QRect(self._rect)
            if "l" in self._handle:
                rect.setLeft(pos.x())
            if "r" in self._handle:
                rect.setRight(pos.x())
            if "t" in self._handle:
                rect.setTop(pos.y())
            if "b" in self._handle:
                rect.setBottom(pos.y())
            self._rect = self._clamp_rect(rect.normalized())
            self._rubberband.setGeometry(self._rect)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._rubberband and self._rect:
            self.selection_changed.emit(self._rect.normalized())
            self._rubberband.setGeometry(self._rect)
            self._rubberband.show()
        self._origin = None
        self._mode = None
        self._handle = None
        # Reset cursor after operation
        self.setCursor(QtCore.Qt.ArrowCursor)

    def clear_rect(self) -> None:
        self._rect = None
        if self._rubberband:
            self._rubberband.hide()
        self.setCursor(QtCore.Qt.ArrowCursor)

    def set_rect(self, rect: QtCore.QRect) -> None:
        self._rect = rect
        if self._rubberband is None:
            self._rubberband = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._rubberband.setGeometry(rect)
        self._rubberband.show()

    def _near_corner(self, pos: QtCore.QPoint, rect: QtCore.QRect, thresh: int = 10) -> bool:
        return any((pos - corner).manhattanLength() <= thresh for corner in self._corners(rect))

    def _near_edge(self, pos: QtCore.QPoint, rect: QtCore.QRect, thresh: int = 10) -> bool:
        """Check if position is near any edge of the rectangle."""
        x, y = pos.x(), pos.y()
        r = rect
        # Check proximity to edges
        near_left = abs(x - r.left()) <= thresh and r.top() <= y <= r.bottom()
        near_right = abs(x - r.right()) <= thresh and r.top() <= y <= r.bottom()
        near_top = abs(y - r.top()) <= thresh and r.left() <= x <= r.right()
        near_bottom = abs(y - r.bottom()) <= thresh and r.left() <= x <= r.right()
        return near_left or near_right or near_top or near_bottom

    def _get_resize_handle(self, pos: QtCore.QPoint, rect: QtCore.QRect, thresh: int = 10) -> str:
        """Determine which resize handle (corner or edge) is being grabbed."""
        x, y = pos.x(), pos.y()
        r = rect
        
        # Check corners first (higher priority)
        corners = {
            "tl": (r.topLeft(), QtCore.Qt.SizeFDiagCursor),
            "tr": (r.topRight(), QtCore.Qt.SizeBDiagCursor),
            "bl": (r.bottomLeft(), QtCore.Qt.SizeBDiagCursor),
            "br": (r.bottomRight(), QtCore.Qt.SizeFDiagCursor),
        }
        for label, (corner, _) in corners.items():
            if (pos - corner).manhattanLength() <= thresh:
                return label
        
        # Check edges
        if abs(x - r.left()) <= thresh and r.top() <= y <= r.bottom():
            return "l"
        if abs(x - r.right()) <= thresh and r.top() <= y <= r.bottom():
            return "r"
        if abs(y - r.top()) <= thresh and r.left() <= x <= r.right():
            return "t"
        if abs(y - r.bottom()) <= thresh and r.left() <= x <= r.right():
            return "b"
        
        return "tl"  # Fallback

    def _set_cursor_for_handle(self, handle: str) -> None:
        """Set appropriate cursor based on resize handle."""
        cursor_map = {
            "tl": QtCore.Qt.SizeFDiagCursor,
            "br": QtCore.Qt.SizeFDiagCursor,
            "tr": QtCore.Qt.SizeBDiagCursor,
            "bl": QtCore.Qt.SizeBDiagCursor,
            "l": QtCore.Qt.SizeHorCursor,
            "r": QtCore.Qt.SizeHorCursor,
            "t": QtCore.Qt.SizeVerCursor,
            "b": QtCore.Qt.SizeVerCursor,
        }
        self.setCursor(cursor_map.get(handle, QtCore.Qt.ArrowCursor))

    def _corners(self, rect: QtCore.QRect):
        return [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
        ]

    def _clamp_rect(self, rect: QtCore.QRect) -> QtCore.QRect:
        bounds = self.rect()
        rect = rect.normalized()
        rect.setLeft(max(bounds.left(), rect.left()))
        rect.setTop(max(bounds.top(), rect.top()))
        rect.setRight(min(bounds.right(), rect.right()))
        rect.setBottom(min(bounds.bottom(), rect.bottom()))
        return rect


class DepthLabel(SelectableLabel):
    wheel_zoom = QtCore.Signal(float, QtCore.QPoint)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        angle = event.angleDelta().y()
        if angle == 0:
            return
        factor = 1.0 + (0.1 if angle > 0 else -0.1)
        self.wheel_zoom.emit(factor, event.position().toPoint())
        super().wheelEvent(event)


class RgbLabel(SelectableLabel):
    wheel_zoom = QtCore.Signal(float, QtCore.QPoint)
    zoom_changed = QtCore.Signal()  # Emitted when zoom or pan changes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zoom: float = 1.0
        self._pan_x: int = 0
        self._pan_y: int = 0
        self._panning: bool = False
        self._last_pan_pos: Optional[QtCore.QPoint] = None
        self._pan_start_x: int = 0  # Track if pan actually changed
        self._pan_start_y: int = 0
        self._base_pixmap: Optional[QtGui.QPixmap] = None
        self._export_settings_text: str = ""
        # Don't enable mouse tracking here - SelectableLabel already does it

    def set_base_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        """Store the base pixmap for zoom operations."""
        self._base_pixmap = pixmap
        self._update_zoom_display()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handle mouse wheel for zooming."""
        # Only zoom if not currently drawing/resizing/moving selection
        if self._mode:
            return
        
        if self._base_pixmap is None:
            return
        
        angle = event.angleDelta().y()
        if angle == 0:
            return
        
        # Get mouse position in label coordinates
        mouse_pos = event.position().toPoint()
        
        # Store old zoom
        old_zoom = self._zoom
        
        # Zoom in/out with mouse wheel
        if angle > 0:
            new_zoom = min(self._zoom * 1.2, 10.0)  # Max 10x zoom
        else:
            new_zoom = max(self._zoom / 1.2, 1.0)  # Min 1x zoom
        
        if new_zoom == old_zoom:
            return
        
        # Get image dimensions
        pw = self._base_pixmap.width()
        ph = self._base_pixmap.height()
        
        # Get label dimensions
        label_w = self.width()
        label_h = self.height()
        
        # Calculate how the image will be displayed at old zoom
        aspect_ratio = pw / ph
        label_aspect = label_w / label_h
        
        if label_aspect > aspect_ratio:
            # Height constrained
            display_h = label_h
            display_w = label_h * aspect_ratio
            offset_left = (label_w - display_w) / 2
            offset_top = 0
        else:
            # Width constrained
            display_w = label_w
            display_h = label_w / aspect_ratio
            offset_left = 0
            offset_top = (label_h - display_h) / 2
        
        # Mouse position relative to displayed image
        mouse_in_display_x = mouse_pos.x() - offset_left
        mouse_in_display_y = mouse_pos.y() - offset_top
        
        # At old_zoom, which image pixel is under the mouse?
        if old_zoom == 1.0:
            # At zoom 1.0, the full image is shown
            # Mouse position maps directly to image coordinates
            image_point_x = (mouse_in_display_x / display_w) * pw
            image_point_y = (mouse_in_display_y / display_h) * ph
        else:
            # At zoomed state, we need to account for the current crop
            # The crop is centered at (pw/2 - pan_x/zoom, ph/2 - pan_y/zoom)
            crop_w = pw / old_zoom
            crop_h = ph / old_zoom
            center_x = pw / 2 - self._pan_x / old_zoom
            center_y = ph / 2 - self._pan_y / old_zoom
            crop_x = center_x - crop_w / 2
            crop_y = center_y - crop_h / 2
            
            # Mouse maps to position within the crop
            image_point_x = crop_x + (mouse_in_display_x / display_w) * crop_w
            image_point_y = crop_y + (mouse_in_display_y / display_h) * crop_h
        
        # Now set pan so that image_point stays under the mouse at new_zoom
        if new_zoom == 1.0:
            # Zooming back to 1.0 - reset pan
            self._pan_x = 0
            self._pan_y = 0
        else:
            # We want image_point to be at mouse position after zoom
            # At new_zoom, the crop will be:
            # crop_w = pw / new_zoom, crop_h = ph / new_zoom
            # crop is centered at (pw/2 - pan_x/new_zoom, ph/2 - pan_y/new_zoom)
            # crop_x = pw/2 - pan_x/new_zoom - crop_w/2
            # 
            # We want: image_point_x = crop_x + (mouse_in_display_x / display_w) * crop_w
            # Solving for pan_x:
            # image_point_x = pw/2 - pan_x/new_zoom - pw/(2*new_zoom) + (mouse_in_display_x / display_w) * pw/new_zoom
            # pan_x = new_zoom * (pw/2 - pw/(2*new_zoom) - image_point_x + (mouse_in_display_x / display_w) * pw/new_zoom)
            # Simplify:
            # pan_x = new_zoom * pw/2 - pw/2 - new_zoom * image_point_x + (mouse_in_display_x / display_w) * pw
            
            crop_w_new = pw / new_zoom
            crop_h_new = ph / new_zoom
            
            # Position in crop where mouse should be (normalized 0-1)
            norm_x = mouse_in_display_x / display_w if display_w > 0 else 0.5
            norm_y = mouse_in_display_y / display_h if display_h > 0 else 0.5
            
            # Center of crop should be positioned such that:
            # crop_start + norm * crop_size = image_point
            # crop_start = image_point - norm * crop_size
            desired_crop_x = image_point_x - norm_x * crop_w_new
            desired_crop_y = image_point_y - norm_y * crop_h_new
            
            # crop_x = pw/2 - pan_x/new_zoom - crop_w_new/2
            # desired_crop_x = pw/2 - pan_x/new_zoom - crop_w_new/2
            # pan_x = new_zoom * (pw/2 - crop_w_new/2 - desired_crop_x)
            self._pan_x = int(new_zoom * (pw / 2 - crop_w_new / 2 - desired_crop_x))
            self._pan_y = int(new_zoom * (ph / 2 - crop_h_new / 2 - desired_crop_y))
        
        self._zoom = new_zoom
        self._update_zoom_display()
        self.zoom_changed.emit()  # Notify that zoom state changed

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press for panning or selection."""
        # If zoomed and not near selection, start panning
        if self._zoom > 1.0 and event.button() == QtCore.Qt.RightButton:
            self._panning = True
            self._last_pan_pos = event.position().toPoint()
            self._pan_start_x = self._pan_x  # Remember starting position
            self._pan_start_y = self._pan_y
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return
        
        # Otherwise, handle selection
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move for panning or selection."""
        if self._panning and self._last_pan_pos:
            delta = event.position().toPoint() - self._last_pan_pos
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._last_pan_pos = event.position().toPoint()
            self._update_zoom_display()
            self.zoom_changed.emit()  # Update bbox position during pan
            return
        
        # Update cursor for zoom/pan
        if not self._mode and not self._panning:
            if self._zoom > 1.0:
                self.setCursor(QtCore.Qt.OpenHandCursor)
            # else cursor is managed by SelectableLabel
        
        # Handle selection
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release."""
        if event.button() == QtCore.Qt.RightButton and self._panning:
            self._panning = False
            self.setCursor(QtCore.Qt.OpenHandCursor if self._zoom > 1.0 else QtCore.Qt.ArrowCursor)
            # Only emit zoom_changed if pan position actually changed
            if self._pan_x != self._pan_start_x or self._pan_y != self._pan_start_y:
                self.zoom_changed.emit()
            return
        
        super().mouseReleaseEvent(event)

    def _update_zoom_display(self) -> None:
        """Update the displayed image with current zoom and pan."""
        if self._base_pixmap is None:
            return
        
        if self._zoom == 1.0:
            # No zoom - scale to fit label size
            scaled = self._base_pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            super().setPixmap(scaled)
        else:
            # Zoomed - crop and scale
            pw = self._base_pixmap.width()
            ph = self._base_pixmap.height()
            
            # Calculate visible region (crop)
            crop_w = int(pw / self._zoom)
            crop_h = int(ph / self._zoom)
            
            # Center point with pan offset (inverted for natural movement)
            center_x = pw // 2 - int(self._pan_x / self._zoom)
            center_y = ph // 2 - int(self._pan_y / self._zoom)
            
            # Clamp crop region
            crop_x = max(0, min(center_x - crop_w // 2, pw - crop_w))
            crop_y = max(0, min(center_y - crop_h // 2, ph - crop_h))
            
            # Crop the pixmap
            cropped = self._base_pixmap.copy(crop_x, crop_y, crop_w, crop_h)
            
            # Scale to label size
            scaled = cropped.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            super().setPixmap(scaled)

    def image_to_display_rect(self, img_rect: QtCore.QRect) -> QtCore.QRect:
        """Convert image coordinates to display coordinates (accounting for zoom/pan)."""
        if self._base_pixmap is None or img_rect.isNull():
            return QtCore.QRect()
        
        pw = self._base_pixmap.width()
        ph = self._base_pixmap.height()
        
        # Get label dimensions
        label_w = self.width()
        label_h = self.height()
        
        # Calculate displayed image dimensions (with aspect ratio)
        aspect_ratio = pw / ph
        label_aspect = label_w / label_h
        
        if label_aspect > aspect_ratio:
            display_h = label_h
            display_w = label_h * aspect_ratio
            offset_left = (label_w - display_w) / 2
            offset_top = 0
        else:
            display_w = label_w
            display_h = label_w / aspect_ratio
            offset_left = 0
            offset_top = (label_h - display_h) / 2
        
        if self._zoom == 1.0:
            # No zoom - direct scaling
            scale = display_w / pw
            return QtCore.QRect(
                int(img_rect.x() * scale + offset_left),
                int(img_rect.y() * scale + offset_top),
                int(img_rect.width() * scale),
                int(img_rect.height() * scale)
            )
        else:
            # Zoomed - need to account for crop
            crop_w = pw / self._zoom
            crop_h = ph / self._zoom
            center_x = pw / 2 - self._pan_x / self._zoom
            center_y = ph / 2 - self._pan_y / self._zoom
            crop_x = max(0, min(center_x - crop_w / 2, pw - crop_w))
            crop_y = max(0, min(center_y - crop_h / 2, ph - crop_h))
            
            # Use x + width instead of right() to avoid Qt's off-by-one
            img_x2 = img_rect.x() + img_rect.width()
            img_y2 = img_rect.y() + img_rect.height()
            
            # Check if bbox is within visible crop
            if (img_x2 < crop_x or img_rect.x() > crop_x + crop_w or
                img_y2 < crop_y or img_rect.y() > crop_y + crop_h):
                # Bbox is outside visible area
                return QtCore.QRect()
            
            # Map to crop-relative coordinates
            rel_x1 = img_rect.x() - crop_x
            rel_y1 = img_rect.y() - crop_y
            rel_x2 = img_x2 - crop_x
            rel_y2 = img_y2 - crop_y
            
            # Clamp to crop bounds
            rel_x1 = max(0, min(crop_w, rel_x1))
            rel_y1 = max(0, min(crop_h, rel_y1))
            rel_x2 = max(0, min(crop_w, rel_x2))
            rel_y2 = max(0, min(crop_h, rel_y2))
            
            # Scale to display
            scale = display_w / crop_w
            return QtCore.QRect(
                int(rel_x1 * scale + offset_left),
                int(rel_y1 * scale + offset_top),
                int((rel_x2 - rel_x1) * scale),
                int((rel_y2 - rel_y1) * scale)
            )

    def display_to_image_rect(self, disp_rect: QtCore.QRect) -> QtCore.QRect:
        """Convert display coordinates to image coordinates (accounting for zoom/pan)."""
        if self._base_pixmap is None or disp_rect.isNull():
            return QtCore.QRect()
        
        pw = self._base_pixmap.width()
        ph = self._base_pixmap.height()
        
        # Get label dimensions
        label_w = self.width()
        label_h = self.height()
        
        # Calculate displayed image dimensions (with aspect ratio)
        aspect_ratio = pw / ph
        label_aspect = label_w / label_h
        
        if label_aspect > aspect_ratio:
            display_h = label_h
            display_w = label_h * aspect_ratio
            offset_left = (label_w - display_w) / 2
            offset_top = 0
        else:
            display_w = label_w
            display_h = label_w / aspect_ratio
            offset_left = 0
            offset_top = (label_h - display_h) / 2
        
        # Remove offsets (use x + width instead of right() to avoid Qt's off-by-one)
        rel_x1 = disp_rect.x() - offset_left
        rel_y1 = disp_rect.y() - offset_top
        rel_x2 = disp_rect.x() + disp_rect.width() - offset_left
        rel_y2 = disp_rect.y() + disp_rect.height() - offset_top
        
        if self._zoom == 1.0:
            # No zoom - direct inverse scaling
            scale = pw / display_w
            return QtCore.QRect(
                int(rel_x1 * scale),
                int(rel_y1 * scale),
                int((rel_x2 - rel_x1) * scale),
                int((rel_y2 - rel_y1) * scale)
            )
        else:
            # Zoomed - account for crop
            crop_w = pw / self._zoom
            crop_h = ph / self._zoom
            center_x = pw / 2 - self._pan_x / self._zoom
            center_y = ph / 2 - self._pan_y / self._zoom
            crop_x = max(0, min(center_x - crop_w / 2, pw - crop_w))
            crop_y = max(0, min(center_y - crop_h / 2, ph - crop_h))
            
            # Scale from display to crop coordinates
            scale = crop_w / display_w
            crop_rel_x1 = rel_x1 * scale
            crop_rel_y1 = rel_y1 * scale
            crop_rel_x2 = rel_x2 * scale
            crop_rel_y2 = rel_y2 * scale
            
            # Map to image coordinates
            img_x1 = int(crop_x + crop_rel_x1)
            img_y1 = int(crop_y + crop_rel_y1)
            img_x2 = int(crop_x + crop_rel_x2)
            img_y2 = int(crop_y + crop_rel_y2)
            
            # Clamp to image bounds
            img_x1 = max(0, min(pw, img_x1))
            img_y1 = max(0, min(ph, img_y1))
            img_x2 = max(0, min(pw, img_x2))
            img_y2 = max(0, min(ph, img_y2))
            
            return QtCore.QRect(img_x1, img_y1, img_x2 - img_x1, img_y2 - img_y1)

    def set_export_settings_text(self, text: str) -> None:
        """Set the export settings text to display on the bbox."""
        self._export_settings_text = text
        self.update()  # Trigger repaint

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Override to draw export settings text on the bbox."""
        super().paintEvent(event)
        
        # Only draw if we have both a bbox and export settings text
        if not self._rect or not self._export_settings_text:
            return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Font setup - small and sleek
        font = QtGui.QFont("Arial", 9)
        font.setBold(True)
        painter.setFont(font)
        
        # Calculate text position (above bbox with padding)
        text_rect = painter.fontMetrics().boundingRect(self._export_settings_text)
        text_x = self._rect.left()
        text_y = self._rect.top() - 6  # 6px above bbox
        
        # If text would go off the top, place it inside bbox instead
        if text_y - text_rect.height() < 0:
            text_y = self._rect.top() + text_rect.height() + 4
        
        # Draw semi-transparent background for text
        bg_rect = QtCore.QRect(
            text_x - 2,
            text_y - text_rect.height() - 2,
            text_rect.width() + 4,
            text_rect.height() + 4
        )
        painter.fillRect(bg_rect, QtGui.QColor(0, 0, 0, 180))
        
        # Draw text in white
        painter.setPen(QtGui.QColor(255, 255, 255))
        painter.drawText(text_x, text_y, self._export_settings_text)


class FramePair:
    def __init__(self, rgb: Path, depth: Path):
        self.rgb = rgb
        self.depth = depth


class ViewerWindow(QtWidgets.QMainWindow):
    # Tracker configuration - change to 'KCF' or 'MOSSE' for faster tracking
    TRACKER_TYPE = 'CSRT'  # Options: 'CSRT' (best accuracy), 'KCF' (balanced), 'MOSSE' (fastest)
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Depth Annotator (Skeleton)")
        self.resize(1200, 800)

        self.folder: Optional[Path] = None
        self.pairs: List[FramePair] = []
        self.current_index = 0
        self.current_depth: Optional[np.ndarray] = None
        self.current_rgb_size: Tuple[int, int] = (0, 0)
        self.current_depth_size: Tuple[int, int] = (0, 0)
        self.depth_zoom: float = 1.0
        self.depth_focus: Optional[Tuple[int, int]] = None  # in depth coords
        self.current_bbox: Optional[QtCore.QRect] = None
        self.last_valid_mask: Optional[np.ndarray] = None
        self.training_root = self._load_training_root()
        self.last_processed: Optional[Path] = self._load_last_processed()
        self.rgb_disp_info: Optional[dict] = None
        self.rgb_zoom: float = 1.0
        self.rgb_focus: Optional[Tuple[int, int]] = None
        self._rendering: bool = False
        self.rgb_last_size: Tuple[int, int] = (0, 0)
        self.depth_last_size: Tuple[int, int] = (0, 0)
        self._resize_timer = QtCore.QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_complete)
        self._last_mean_depth: Optional[float] = None
        self._last_std_depth: Optional[float] = None
        self._last_min_depth: Optional[float] = None
        self._last_max_depth: Optional[float] = None
        self._max_frame_number: int = 0  # Cache for highest frame number in folder
        # Tracker state
        self._tracker: Optional[cv2.Tracker] = None
        self._tracker_initialized: bool = False

        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout()

        top_bar = QtWidgets.QHBoxLayout()
        self.folder_edit = QtWidgets.QLineEdit()
        self.folder_edit.setPlaceholderText("Ordner mit JPG + NPY auswählen")
        browse_btn = QtWidgets.QPushButton("Ordner…")
        self.filename_label = QtWidgets.QLabel("")
        self.status_label = QtWidgets.QLabel("Bereit.")
        top_bar.addWidget(self.folder_edit)
        top_bar.addWidget(browse_btn)
        top_bar.addWidget(self.filename_label)
        top_bar.addWidget(self.status_label)

        training_bar = QtWidgets.QHBoxLayout()
        self.training_root_edit = QtWidgets.QLineEdit(self.training_root)
        self.training_root_btn = QtWidgets.QPushButton("Training-Root…")
        self.benchmark_btn = QtWidgets.QPushButton("Benchmark erstellen")
        self.benchmark_btn.setToolTip("Nicht-annotierte Frames in Benchmark-Ordner kopieren")
        self.training_status = QtWidgets.QLabel("")
        training_bar.addWidget(QtWidgets.QLabel("Training Root:"))
        training_bar.addWidget(self.training_root_edit)
        training_bar.addWidget(self.training_root_btn)
        training_bar.addWidget(self.benchmark_btn)
        training_bar.addWidget(self.training_status)

        view_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Create labels
        self.rgb_view = RgbLabel("RGB")
        self.rgb_view.setAlignment(QtCore.Qt.AlignCenter)
        self.rgb_view.setFrameStyle(QtWidgets.QFrame.Box)
        self.rgb_view.setScaledContents(False)
        
        self.depth_view = DepthLabel("Depth")
        self.depth_view.setAlignment(QtCore.Qt.AlignCenter)
        self.depth_view.setFrameStyle(QtWidgets.QFrame.Box)
        self.depth_view.setScaledContents(False)
        
        # Wrap in aspect ratio containers
        self._rgb_container = AspectRatioWidget(self.rgb_view, aspect_ratio=16/9)
        self._depth_container = AspectRatioWidget(self.depth_view, aspect_ratio=16/9)
        
        view_split.addWidget(self._rgb_container)
        view_split.addWidget(self._depth_container)
        view_split.setStretchFactor(0, 1)
        view_split.setStretchFactor(1, 1)
        self.rgb_view.installEventFilter(self)
        self.depth_view.installEventFilter(self)

        controls = QtWidgets.QHBoxLayout()
        self.prev_btn = QtWidgets.QPushButton("Vorheriges")
        self.prev5_btn = QtWidgets.QPushButton("-5")
        self.next_btn = QtWidgets.QPushButton("Nächstes")
        self.next5_btn = QtWidgets.QPushButton("+5")
        self.index_label = QtWidgets.QLabel("0 / 0")
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.prev5_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.next5_btn)
        controls.addWidget(self.index_label)
        controls.addStretch()

        annotate_group = QtWidgets.QGroupBox("Annotation")
        alayout = QtWidgets.QHBoxLayout()
        self.main_combo = QtWidgets.QComboBox()
        self.main_combo.addItems(["S", "SE", "E", "NE", "N", "NW", "W", "SW"])
        self.sub_combo = QtWidgets.QComboBox()
        self.sub_combo.addItems(["Bot", "Horizon", "Top"])
        self.mean_label = QtWidgets.QLabel("Mean depth: -")
        self.cls_combo = QtWidgets.QComboBox()
        self.cls_combo.addItems(["target_close", "target_far", "negative_sample"])
        self.rename_btn = QtWidgets.QPushButton("Exportieren")
        self.clear_btn = QtWidgets.QPushButton("Clear AOI")
        self.bbox_label = QtWidgets.QLabel("BBox: -")
        self.track_checkbox = QtWidgets.QCheckBox("Track BBox")
        self.track_checkbox.setEnabled(False)  # Disabled until bbox is drawn
        self.track_checkbox.setToolTip("Wenn aktiviert, wird die BBox beim Navigieren automatisch verfolgt")
        alayout.addWidget(QtWidgets.QLabel("Kategorie:"))
        alayout.addWidget(self.main_combo)
        alayout.addWidget(self.sub_combo)
        alayout.addWidget(QtWidgets.QLabel("YOLO-Klasse:"))
        alayout.addWidget(self.cls_combo)
        alayout.addWidget(self.mean_label)
        alayout.addWidget(self.bbox_label)
        alayout.addWidget(self.track_checkbox)
        alayout.addWidget(self.clear_btn)
        alayout.addWidget(self.rename_btn)
        annotate_group.setLayout(alayout)

        depth_ctrl = QtWidgets.QGroupBox("Depth-Visualisierung")
        dlayout = QtWidgets.QHBoxLayout()
        self.min_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.max_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.min_slider.setRange(1, 10)
        self.max_slider.setRange(10, 40)
        self.min_slider.setValue(1)
        self.max_slider.setValue(20)
        self.min_label = QtWidgets.QLabel("Min: 1 m")
        self.max_label = QtWidgets.QLabel("Max: 20 m")
        dlayout.addWidget(self.min_label)
        dlayout.addWidget(self.min_slider)
        dlayout.addWidget(self.max_label)
        dlayout.addWidget(self.max_slider)
        depth_ctrl.setLayout(dlayout)

        layout.addLayout(top_bar)
        layout.addLayout(training_bar)
        layout.addWidget(view_split)
        layout.addLayout(controls)
        layout.addWidget(depth_ctrl)
        layout.addWidget(annotate_group)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._browse_btn = browse_btn

    def _wire_signals(self) -> None:
        self._browse_btn.clicked.connect(self._choose_folder)
        self.prev_btn.clicked.connect(self._prev)
        self.prev5_btn.clicked.connect(lambda: self._jump(-5))
        self.next_btn.clicked.connect(self._next)
        self.next5_btn.clicked.connect(lambda: self._jump(5))
        self.min_slider.valueChanged.connect(self._on_depth_range_changed)
        self.max_slider.valueChanged.connect(self._on_depth_range_changed)
        self.depth_view.selection_changed.connect(self._on_aoi_selected)
        self.depth_view.wheel_zoom.connect(self._on_depth_wheel)
        self.rgb_view.wheel_zoom.connect(self._on_rgb_wheel)
        self.rename_btn.clicked.connect(self._on_rename)
        self.training_root_btn.clicked.connect(self._choose_training_root)
        self.benchmark_btn.clicked.connect(self._create_benchmark_images)
        self.training_root_edit.textChanged.connect(self._on_training_root_changed)
        self.rgb_view.selection_changed.connect(self._on_rgb_selection)
        self.clear_btn.clicked.connect(self._clear_selection)
        self.track_checkbox.stateChanged.connect(self._on_track_checkbox_changed)
        # Update export settings text when combo boxes change
        self.main_combo.currentIndexChanged.connect(self._update_export_settings_text)
        self.sub_combo.currentIndexChanged.connect(self._update_export_settings_text)
        self.cls_combo.currentIndexChanged.connect(self._update_export_settings_text)
        # Update bbox display when zoom/pan changes
        self.rgb_view.zoom_changed.connect(self._on_rgb_zoom_changed)
        # Re-render when aspect ratio containers resize
        self._rgb_container.resized.connect(self._on_container_resized)
        self._depth_container.resized.connect(self._on_container_resized)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle keyboard shortcuts for faster workflow."""
        if event.key() == QtCore.Qt.Key_Return or event.key() == QtCore.Qt.Key_Enter:
            # Enter key triggers export
            if self.current_bbox is not None and self.pairs:
                self._on_rename()
                # Auto-advance to next frame after successful export
                if self.current_index < len(self.pairs) - 1:
                    self._navigate(1)
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_container_resized(self) -> None:
        """Debounced re-render when aspect ratio containers resize."""
        if self.pairs:
            self._resize_timer.start(100)

    def _choose_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Ordner mit JPG + NPY")
        if folder:
            self.folder_edit.setText(folder)
            self._load_folder(Path(folder))

    def _load_folder(self, folder: Path) -> None:
        self.folder = folder
        # Clear tracking when changing folders
        self._clear_selection()
        
        jpgs = sorted(folder.glob("*.jpg"))
        pairs: List[FramePair] = []
        for jpg in jpgs:
            depth = jpg.with_suffix(".npy")
            if depth.exists():
                pairs.append(FramePair(jpg, depth))
        self.pairs = pairs
        
        # Calculate and cache max frame number
        self._max_frame_number = 0
        for pair in pairs:
            frame_num = self._extract_frame_number(pair.rgb.stem)
            if frame_num is not None and frame_num > self._max_frame_number:
                self._max_frame_number = frame_num
        
        # determine start index based on last processed
        self.current_index = 0
        if pairs and self.last_processed and self.last_processed.parent == folder:
            for idx, p in enumerate(pairs):
                if p.rgb.name == self.last_processed.name:
                    self.current_index = min(idx + 1, len(pairs) - 1)
                    break
        self._update_index_label()
        if pairs:
            self._show_pair(pairs[self.current_index])
            self._resize_timer.start(50)
            self.status_label.setText(f"{len(pairs)} Paare gefunden.")
        else:
            self.rgb_view.setText("Keine Paare gefunden.")
            self.depth_view.setText("Keine Paare gefunden.")
            self.status_label.setText("Keine Paare gefunden.")

    def _update_index_label(self) -> None:
        total = len(self.pairs)
        if total == 0:
            self.index_label.setText("0 / 0")
        else:
            # Extract frame number from current filename (e.g., "frame_000138.jpg" -> 138)
            current_pair = self.pairs[self.current_index]
            current_frame_num = self._extract_frame_number(current_pair.rgb.stem)
            
    def _update_index_label(self) -> None:
        total = len(self.pairs)
        if total == 0:
            self.index_label.setText("0 / 0")
        else:
            # Extract frame number from current filename (e.g., "frame_000138.jpg" -> 138)
            current_pair = self.pairs[self.current_index]
            current_frame_num = self._extract_frame_number(current_pair.rgb.stem)
            
            # Check if this frame has been annotated or is in benchmark
            frame_status = self._get_frame_status(current_pair.rgb.stem)
            
            # Set marker and styling based on status
            if frame_status == "annotated":
                marker = " ✓"
                style = "color: green; font-weight: bold;"
            elif frame_status == "benchmark":
                marker = " ✓"
                style = "color: orange; font-weight: bold;"
            else:
                marker = ""
                style = ""
            
            # Display: (position) frame_number / max_frame_number [✓ if annotated/benchmark]
            if current_frame_num is not None and self._max_frame_number > 0:
                self.index_label.setText(f"({self.current_index+1}) {current_frame_num} / {self._max_frame_number}{marker}")
            else:
                # Fallback if we can't parse frame number
                self.index_label.setText(f"{self.current_index+1} / {total}{marker}")
            
            # Color the label based on status
            self.index_label.setStyleSheet(style)
    
    def _get_frame_status(self, frame_stem: str) -> str:
        """Check frame status: 'annotated', 'benchmark', or 'none'.
        
        Returns:
            'annotated' - Frame has been exported to training buckets
            'benchmark' - Frame exists in benchmark folder
            'none' - Frame not yet processed
        """
        if not self.training_root or not self.folder:
            return "none"
        
        training_root_path = Path(self.training_root)
        if not training_root_path.exists():
            return "none"
        
        # Get the source folder name for matching
        source_folder = self.folder.name
        
        # Search pattern: frame_NNNNNN-<source_folder>-*.jpg
        search_pattern = f"{frame_stem}-{source_folder}-*.jpg"
        
        # First check benchmark folder
        benchmark_dir = training_root_path / "benchmark"
        if benchmark_dir.exists():
            matches = list(benchmark_dir.glob(search_pattern))
            if matches:
                return "benchmark"
        
        # Search in all bucket directories for annotations
        # Structure: training_root / N_Direction / Position / Distance / images
        for bucket_dir in training_root_path.glob("*"):
            if not bucket_dir.is_dir():
                continue
            
            # Skip benchmark and negative_samples folders
            if bucket_dir.name in ["benchmark", "negative_samples"]:
                continue
            
            # Check 0_far directory (target_far images)
            if bucket_dir.name == "0_far":
                matches = list(bucket_dir.glob(search_pattern))
                if matches:
                    return "annotated"
            else:
                # Check direction/position/distance structure (target_close images)
                for pos_dir in bucket_dir.glob("*"):
                    if not pos_dir.is_dir():
                        continue
                    for dist_dir in pos_dir.glob("*"):
                        if not dist_dir.is_dir():
                            continue
                        matches = list(dist_dir.glob(search_pattern))
                        if matches:
                            return "annotated"
        
        # Check negative_samples folder
        negative_dir = training_root_path / "negative_samples"
        if negative_dir.exists():
            matches = list(negative_dir.glob(search_pattern))
            if matches:
                return "annotated"
        
        return "none"
    
    def _is_frame_annotated(self, frame_stem: str) -> bool:
        """Check if a frame has been annotated (backward compatibility)."""
        return self._get_frame_status(frame_stem) == "annotated"
    
    def _remove_from_benchmark(self, frame_stem: str, training_root: Path) -> None:
        """Remove frame from benchmark folder if it exists (after successful annotation)."""
        if not self.folder:
            return
        
        benchmark_dir = training_root / "benchmark"
        if not benchmark_dir.exists():
            return
        
        source_folder = self.folder.name
        search_pattern = f"{frame_stem}-{source_folder}-*.jpg"
        
        # Find and delete any matching files in benchmark
        for benchmark_file in benchmark_dir.glob(search_pattern):
            try:
                benchmark_file.unlink()
                print(f"Removed from benchmark: {benchmark_file.name}")
            except Exception as e:
                print(f"Warning: Could not remove {benchmark_file.name} from benchmark: {e}")
    
    def _extract_frame_number(self, filename: str) -> Optional[int]:
        """Extract frame number from filename like 'frame_000138' or 'frame_000138-metadata'."""
        import re
        # Match "frame_" followed by digits (possibly with leading zeros)
        match = re.search(r'frame_(\d+)', filename)
        if match:
            return int(match.group(1))
        return None

    def _show_pair(self, pair: FramePair, keep_selection: bool = False) -> None:
        if not keep_selection:
            self._clear_selection()
        self.rgb_disp_info = self._render_rgb(pair.rgb, keep_selection=keep_selection)
        self._render_depth(pair.depth)
        self._update_index_label()
        self.filename_label.setText(pair.rgb.name)

    def _render_rgb(self, path: Path, keep_selection: bool = False) -> Optional[dict]:
        pix = QtGui.QPixmap(str(path))
        if pix.isNull():
            self.rgb_view.setText(f"Kann nicht laden: {path.name}")
            return None
        w = pix.width()
        h = pix.height()
        
        # Store full-resolution pixmap in RgbLabel for zoom/pan
        self.rgb_view.set_base_pixmap(pix)
        
        # Get displayed size (RgbLabel handles zoom internally now)
        disp_w = self.rgb_view.width()
        disp_h = self.rgb_view.height()
        offset_x = 0
        offset_y = 0
        scale = disp_w / w if w else 1.0
        
        info = {
            "orig_w": w,
            "orig_h": h,
            "disp_w": disp_w,
            "disp_h": disp_h,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "scale": scale,
            "crop_x1": 0,  # No crop at zoom level 1.0
            "crop_y1": 0,
            "crop_w": w,
            "crop_h": h,
        }
        # Restore selection display if available (using zoom-aware transformation)
        if keep_selection and self.current_bbox and isinstance(self.rgb_view, RgbLabel):
            display_rect = self.rgb_view.image_to_display_rect(self.current_bbox)
            if not display_rect.isNull():
                self.rgb_view.set_rect(display_rect)
        return info

    def _render_depth(self, path: Path) -> None:
        try:
            data = np.load(path)
        except Exception as exc:
            self.depth_view.setText(f"Depth laden fehlgeschlagen: {exc}")
            return
        # Placeholder: simple min/max clamp and grayscale mapping
        vmin = self.min_slider.value()
        vmax = max(self.max_slider.value(), vmin + 1)
        self.min_label.setText(f"Min: {vmin} m")
        self.max_label.setText(f"Max: {vmax} m")
        self.current_depth = data
        valid_mask = np.isfinite(data) & (data > 0) & (data >= vmin) & (data <= vmax)
        self.last_valid_mask = valid_mask
        clipped = np.clip(data, vmin, vmax)
        norm = (clipped - vmin) / (vmax - vmin)
        norm = np.nan_to_num(norm, nan=0.0, posinf=0.0, neginf=0.0)
        img = (norm * 255).astype(np.uint8)
        inv = 255 - img
        colored = cv2.applyColorMap(inv, cv2.COLORMAP_JET)
        # set invalid pixels to black
        if colored.shape[:2] == valid_mask.shape:
            colored[~valid_mask] = 0
        h, w, _ = colored.shape
        self.current_depth_size = (w, h)
        # apply zoom around focus
        zoom = self.depth_zoom
        center_x = self.depth_focus[0] if self.depth_focus else w // 2
        center_y = self.depth_focus[1] if self.depth_focus else h // 2
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        crop_w = max(1, min(crop_w, w))
        crop_h = max(1, min(crop_h, h))
        x1 = max(0, min(center_x - crop_w // 2, w - crop_w))
        y1 = max(0, min(center_y - crop_h // 2, h - crop_h))
        x2 = x1 + crop_w
        y2 = y1 + crop_h
        cropped = np.ascontiguousarray(colored[y1:y2, x1:x2])
        qimg = QtGui.QImage(cropped.data, cropped.shape[1], cropped.shape[0], cropped.strides[0], QtGui.QImage.Format_BGR888)
        # Account for frame border when calculating target size
        frame_w = self.depth_view.frameWidth() * 2
        target_w = max(1, self.depth_view.width() - frame_w)
        target_h = max(1, self.depth_view.height() - frame_w)
        pix = QtGui.QPixmap.fromImage(qimg).scaled(
            target_w,
            target_h,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.depth_view.setPixmap(pix)

    def _prev(self) -> None:
        if not self.pairs:
            return
        new_index = (self.current_index - 1) % len(self.pairs)
        self._navigate_to_index(new_index)

    def _next(self) -> None:
        if not self.pairs:
            return
        new_index = (self.current_index + 1) % len(self.pairs)
        self._navigate_to_index(new_index)

    def _jump(self, delta: int) -> None:
        if not self.pairs:
            return
        new_index = (self.current_index + delta) % len(self.pairs)
        self._navigate_to_index(new_index)

    def _navigate_to_index(self, new_index: int) -> None:
        """Navigate to a new frame index, optionally tracking bbox."""
        if not self.pairs:
            return
        
        print(f"\n[TRACKER DEBUG] ===== Navigation from {self.current_index} to {new_index} =====")
        print(f"[TRACKER DEBUG] Tracking enabled: {self.track_checkbox.isChecked()}, Tracker initialized: {self._tracker_initialized}")
        
        # If tracking is enabled and tracker is initialized, predict bbox
        if self.track_checkbox.isChecked() and self._tracker_initialized:
            predicted_bbox = self._track_bbox_to_frame(new_index)
            if predicted_bbox:
                print("[TRACKER DEBUG] Tracking succeeded! Updating UI with predicted bbox")
                self.current_index = new_index
                self.current_bbox = predicted_bbox
                # Use keep_selection=True to prevent _clear_selection() from resetting tracker
                self._show_pair(self.pairs[self.current_index], keep_selection=True)
                # Update stats and display for new bbox
                if self.current_depth is not None:
                    print(f"[TRACKER DEBUG] About to call _update_stats_and_bbox. Tracker initialized: {self._tracker_initialized}")
                    self._update_stats_and_bbox(predicted_bbox, show_rect=True)
                    print(f"[TRACKER DEBUG] After _update_stats_and_bbox. Tracker initialized: {self._tracker_initialized}")
                self.status_label.setText(f"BBox getrackt zu Frame {new_index}")
                print(f"[TRACKER DEBUG] Navigation complete. Tracker still initialized: {self._tracker_initialized}")
                # Note: Tracker is already updated by _track_bbox_to_frame, no need to re-init
            else:
                # Tracking failed - disable and show warning
                print("[TRACKER DEBUG] Tracking failed! Disabling tracker")
                self.status_label.setText("Tracking fehlgeschlagen - deaktiviert")
                # Block signals to avoid re-entrant calls
                self.track_checkbox.blockSignals(True)
                self.track_checkbox.setChecked(False)
                self.track_checkbox.blockSignals(False)
                self.current_index = new_index
                # Keep bbox visible even if tracking failed
                self._show_pair(self.pairs[self.current_index], keep_selection=True)
        else:
            # Normal navigation without tracking - keep bbox at same position
            print("[TRACKER DEBUG] Normal navigation (tracking disabled or not initialized)")
            self.current_index = new_index
            # Always keep bbox visible when navigating
            self._show_pair(self.pairs[self.current_index], keep_selection=True)

    def _on_depth_range_changed(self, _value: int) -> None:
        """Depth slider changed - update visualization but keep bbox."""
        if not self.pairs:
            return
        # Keep the current bbox selection when re-rendering
        self._show_pair(self.pairs[self.current_index], keep_selection=True)

    def _on_rgb_wheel(self, factor: float, pos: QtCore.QPoint) -> None:
        if not self.pairs or self.current_depth is None or not self.rgb_disp_info:
            return
        prev_zoom = self.rgb_zoom
        new_zoom = max(1.0, min(10.0, self.rgb_zoom * factor))  # Increased max zoom to 10x
        if new_zoom == prev_zoom:
            return
        self.rgb_zoom = new_zoom
        
        w = self.rgb_disp_info.get("orig_w", 0)
        h = self.rgb_disp_info.get("orig_h", 0)
        view_w = max(1, self.rgb_view.width())
        view_h = max(1, self.rgb_view.height())
        
        # Current focus (center of current crop)
        center_x = self.rgb_focus[0] if self.rgb_focus else w // 2
        center_y = self.rgb_focus[1] if self.rgb_focus else h // 2
        
        # Previous crop dimensions and position
        prev_crop_w = int(w / prev_zoom)
        prev_crop_h = int(h / prev_zoom)
        prev_crop_w = max(1, min(prev_crop_w, w))
        prev_crop_h = max(1, min(prev_crop_h, h))
        prev_x1 = max(0, min(center_x - prev_crop_w // 2, w - prev_crop_w))
        prev_y1 = max(0, min(center_y - prev_crop_h // 2, h - prev_crop_h))
        
        # Map mouse position to image coordinates (point under cursor)
        scale_x = prev_crop_w / view_w
        scale_y = prev_crop_h / view_h
        img_x = prev_x1 + pos.x() * scale_x
        img_y = prev_y1 + pos.y() * scale_y
        
        # New crop dimensions
        new_crop_w = int(w / new_zoom)
        new_crop_h = int(h / new_zoom)
        new_crop_w = max(1, min(new_crop_w, w))
        new_crop_h = max(1, min(new_crop_h, h))
        
        # Calculate new focus so that img_x, img_y stays at the same screen position
        # After zoom, mouse pos should map to same img coords:
        # new_x1 + pos.x() * new_scale_x = img_x
        # new_x1 = img_x - pos.x() * (new_crop_w / view_w)
        # new_center_x = new_x1 + new_crop_w / 2
        new_scale_x = new_crop_w / view_w
        new_scale_y = new_crop_h / view_h
        new_x1 = img_x - pos.x() * new_scale_x
        new_y1 = img_y - pos.y() * new_scale_y
        new_center_x = new_x1 + new_crop_w / 2
        new_center_y = new_y1 + new_crop_h / 2
        
        # Clamp to valid range
        new_center_x = max(new_crop_w // 2, min(w - new_crop_w // 2, new_center_x))
        new_center_y = max(new_crop_h // 2, min(h - new_crop_h // 2, new_center_y))
        
        self.rgb_focus = (int(new_center_x), int(new_center_y))
        self._show_pair(self.pairs[self.current_index], keep_selection=True)

    def _on_rgb_selection(self, rect: QtCore.QRect) -> None:
        if not self.pairs or not rect:
            return
        # Get image dimensions from RGB or depth
        if self.current_depth is not None:
            img_w, img_h = self.current_depth.shape[1], self.current_depth.shape[0]
        else:
            img_w, img_h = self.current_rgb_size
        
        # Use RgbLabel's coordinate transformation (zoom-aware)
        img_rect = self.rgb_view.display_to_image_rect(rect)
        self._update_stats_and_bbox(img_rect, show_rect=False)
        
        # Update export settings text overlay
        self._update_export_settings_text()
        
        # Re-initialize tracker with new bbox if tracking is enabled
        if self.track_checkbox.isChecked():
            pair = self.pairs[self.current_index]
            frame = self._load_frame_as_numpy(pair.rgb)
            if frame is not None and self.current_bbox:
                print("[TRACKER DEBUG] Manually adjusted bbox on RGB view - re-initializing tracker")
                if self._init_tracker(frame, self.current_bbox):
                    self.status_label.setText("Tracker mit neuer BBox neu initialisiert")
                else:
                    # Only disable if re-init fails
                    self.track_checkbox.blockSignals(True)
                    self.track_checkbox.setChecked(False)
                    self.track_checkbox.blockSignals(False)
                    self._reset_tracker()

    def _on_rgb_zoom_changed(self) -> None:
        """Update bbox display when zoom or pan changes."""
        if self.current_bbox and isinstance(self.rgb_view, RgbLabel):
            # Don't update if user is actively drawing/moving/resizing bbox
            if hasattr(self.rgb_view, '_mode') and self.rgb_view._mode is not None:
                return
            # Note: We DO update during panning so bbox stays locked to the image
            
            display_rect = self.rgb_view.image_to_display_rect(self.current_bbox)
            if not display_rect.isNull():
                # Update the rubberband position without triggering selection_changed
                if self.rgb_view._rubberband:
                    self.rgb_view._rubberband.setGeometry(display_rect)
                self.rgb_view._rect = display_rect

    def _update_export_settings_text(self) -> None:
        """Update the export settings text overlay on the RGB view."""
        if not self.current_bbox:
            # No bbox, clear text
            self.rgb_view.set_export_settings_text("")
            return
        
        # Get current selections
        direction = self.main_combo.currentText()
        position = self.sub_combo.currentText()
        cls_name = self.cls_combo.currentText()
        
        # Format: "SE-Bot" for target_close, "far" for target_far
        if cls_name == "target_far":
            text = "far"
        else:
            # Abbreviate position: Bot, Hor(izon), Top
            pos_abbr = position[:3] if position != "Horizon" else "Hor"
            text = f"{direction}-{pos_abbr}"
        
        self.rgb_view.set_export_settings_text(text)

    def _on_depth_wheel(self, factor: float, pos: QtCore.QPoint) -> None:
        if not self.pairs or self.current_depth is None:
            return
        prev_zoom = self.depth_zoom
        new_zoom = max(1.0, min(10.0, self.depth_zoom * factor))  # Increased max zoom to 10x
        if new_zoom == prev_zoom:
            return
        self.depth_zoom = new_zoom
        
        depth_h, depth_w = self.current_depth.shape[:2]
        view_w = max(1, self.depth_view.width())
        view_h = max(1, self.depth_view.height())
        
        # Current focus (center of current crop)
        center_x = self.depth_focus[0] if self.depth_focus else depth_w // 2
        center_y = self.depth_focus[1] if self.depth_focus else depth_h // 2
        
        # Previous crop dimensions and position
        prev_crop_w = int(depth_w / prev_zoom)
        prev_crop_h = int(depth_h / prev_zoom)
        prev_crop_w = max(1, min(prev_crop_w, depth_w))
        prev_crop_h = max(1, min(prev_crop_h, depth_h))
        prev_x1 = max(0, min(center_x - prev_crop_w // 2, depth_w - prev_crop_w))
        prev_y1 = max(0, min(center_y - prev_crop_h // 2, depth_h - prev_crop_h))
        
        # Map mouse position to image coordinates (point under cursor)
        scale_x = prev_crop_w / view_w
        scale_y = prev_crop_h / view_h
        img_x = prev_x1 + pos.x() * scale_x
        img_y = prev_y1 + pos.y() * scale_y
        
        # New crop dimensions
        new_crop_w = int(depth_w / new_zoom)
        new_crop_h = int(depth_h / new_zoom)
        new_crop_w = max(1, min(new_crop_w, depth_w))
        new_crop_h = max(1, min(new_crop_h, depth_h))
        
        # Calculate new focus so that img_x, img_y stays at the same screen position
        new_scale_x = new_crop_w / view_w
        new_scale_y = new_crop_h / view_h
        new_x1 = img_x - pos.x() * new_scale_x
        new_y1 = img_y - pos.y() * new_scale_y
        new_center_x = new_x1 + new_crop_w / 2
        new_center_y = new_y1 + new_crop_h / 2
        
        # Clamp to valid range
        new_center_x = max(new_crop_w // 2, min(depth_w - new_crop_w // 2, new_center_x))
        new_center_y = max(new_crop_h // 2, min(depth_h - new_crop_h // 2, new_center_y))
        
        self.depth_focus = (int(new_center_x), int(new_center_y))
        self._show_pair(self.pairs[self.current_index])

    def _on_resize_complete(self) -> None:
        """Called after resize events have stopped."""
        # Defer render to next event loop iteration to ensure geometry is finalized
        QtCore.QTimer.singleShot(10, lambda: self._rerender_current(keep_selection=True))

    def _map_rect_to_image(self, rect: QtCore.QRect, disp_info: dict, img_w: int, img_h: int) -> QtCore.QRect:
        scale = disp_info.get("scale", 1.0)
        ox = disp_info.get("offset_x", 0)
        oy = disp_info.get("offset_y", 0)
        crop_x1 = disp_info.get("crop_x1", 0)
        crop_y1 = disp_info.get("crop_y1", 0)
        x1 = (rect.left() - ox) / scale + crop_x1
        y1 = (rect.top() - oy) / scale + crop_y1
        x2 = (rect.right() - ox) / scale + crop_x1
        y2 = (rect.bottom() - oy) / scale + crop_y1
        x1 = max(0, min(img_w - 1, int(x1)))
        y1 = max(0, min(img_h - 1, int(y1)))
        x2 = max(0, min(img_w - 1, int(x2)))
        y2 = max(0, min(img_h - 1, int(y2)))
        if x2 <= x1 or y2 <= y1:
            return QtCore.QRect()
        return QtCore.QRect(x1, y1, x2 - x1, y2 - y1)

    def _update_stats_and_bbox(self, img_rect: QtCore.QRect, show_rect: bool = True) -> None:
        if img_rect.isNull():
            return
        
        x1, y1, w, h = img_rect.x(), img_rect.y(), img_rect.width(), img_rect.height()
        x2 = x1 + w
        y2 = y1 + h
        
        # Always set bbox, even without depth data
        self.current_bbox = QtCore.QRect(x1, y1, w, h)
        self.bbox_label.setText(f"BBox: {x1},{y1},{w},{h}")
        
        # Try to calculate depth stats if depth data is available
        if self.current_depth is not None:
            region = self.current_depth[y1:y2, x1:x2]
            vmin = self.min_slider.value()
            vmax = max(self.max_slider.value(), vmin + 1)
            valid = region[np.isfinite(region) & (region > 0) & (region >= vmin) & (region <= vmax)]
            if valid.size == 0:
                self.mean_label.setText("Mean depth: - (keine gültigen Werte)")
                self._last_mean_depth = None
                self._last_std_depth = None
                self._last_min_depth = None
                self._last_max_depth = None
            else:
                mean_depth = float(valid.mean())
                min_depth = float(valid.min())
                max_depth = float(valid.max())
                std_depth = float(valid.std())
                self.mean_label.setText(f"Mean: {mean_depth:.2f} m | Min: {min_depth:.2f} | Max: {max_depth:.2f} | Std: {std_depth:.2f}")
                self._last_mean_depth = mean_depth
                self._last_std_depth = std_depth
                self._last_min_depth = min_depth
                self._last_max_depth = max_depth
                self._last_region = (x1, y1, x2, y2)
        else:
            # No depth data available
            self.mean_label.setText("Mean depth: - (keine Tiefendaten)")
            self._last_mean_depth = None
            self._last_std_depth = None
            self._last_min_depth = None
            self._last_max_depth = None
        
        # Enable tracking checkbox when bbox is successfully set
        self.track_checkbox.setEnabled(True)
        
        # show rect on rgb view (use zoom-aware coordinate transformation)
        if show_rect and isinstance(self.rgb_view, RgbLabel):
            display_rect = self.rgb_view.image_to_display_rect(img_rect)
            if not display_rect.isNull():
                # Block signals to prevent _on_rgb_selection from being triggered
                # which would reset the tracker
                self.rgb_view.blockSignals(True)
                self.rgb_view.set_rect(display_rect)
                self.rgb_view.blockSignals(False)

    def _on_aoi_selected(self, rect: QtCore.QRect) -> None:
        import traceback
        print(f"[TRACKER DEBUG] _on_aoi_selected called with rect: {rect.x()},{rect.y()},{rect.width()},{rect.height()}")
        print("[TRACKER DEBUG] Call stack:")
        for line in traceback.format_stack()[-5:-1]:
            print(line.strip())
        if self.current_depth is None or not self.pairs:
            return
        if rect.isNull():
            return
        # Map depth-view selection to depth coords considering zoom/crop
        depth_h, depth_w = self.current_depth.shape[:2]
        view_w = max(1, self.depth_view.width())
        view_h = max(1, self.depth_view.height())
        # Map view rect to depth coordinates with current zoom/focus crop
        zoom = self.depth_zoom
        center_x = self.depth_focus[0] if self.depth_focus else depth_w // 2
        center_y = self.depth_focus[1] if self.depth_focus else depth_h // 2
        crop_w = int(depth_w / zoom)
        crop_h = int(depth_h / zoom)
        crop_w = max(1, min(crop_w, depth_w))
        crop_h = max(1, min(crop_h, depth_h))
        crop_x1 = max(0, min(center_x - crop_w // 2, depth_w - crop_w))
        crop_y1 = max(0, min(center_y - crop_h // 2, depth_h - crop_h))

        scale_x = crop_w / view_w
        scale_y = crop_h / view_h
        x1 = int(rect.left() * scale_x) + crop_x1
        y1 = int(rect.top() * scale_y) + crop_y1
        x2 = int(rect.right() * scale_x) + crop_x1
        y2 = int(rect.bottom() * scale_y) + crop_y1
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(depth_w - 1, x2), min(depth_h - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return
        self._update_stats_and_bbox(QtCore.QRect(x1, y1, x2 - x1, y2 - y1), show_rect=True)
        
        # Re-initialize tracker with new bbox if tracking is enabled
        if self.track_checkbox.isChecked():
            pair = self.pairs[self.current_index]
            frame = self._load_frame_as_numpy(pair.rgb)
            if frame is not None and self.current_bbox:
                print("[TRACKER DEBUG] Manually adjusted bbox - re-initializing tracker")
                if self._init_tracker(frame, self.current_bbox):
                    self.status_label.setText("Tracker mit neuer BBox neu initialisiert")
                else:
                    # Only disable if re-init fails
                    self.track_checkbox.blockSignals(True)
                    self.track_checkbox.setChecked(False)
                    self.track_checkbox.blockSignals(False)
                    self._reset_tracker()

    def _on_rename(self) -> None:
        """Export annotated frame to training bucket (never modifies source folder)."""
        if not self.pairs:
            return
        pair = self.pairs[self.current_index]
        mean_depth = getattr(self, "_last_mean_depth", None)
        std_depth = getattr(self, "_last_std_depth", None)
        yolo_class = self.cls_combo.currentText()
        
        # Handle negative samples (Phase 1 roadmap) - no bbox required
        if yolo_class == "negative_sample":
            self._export_negative_sample(pair)
            return
        
        # For target_close and target_far, bbox is required
        if self.current_bbox is None:
            self.status_label.setText("Keine BBox definiert.")
            return
        
        # For target_close without depth data, ask user for manual bucket assignment
        if yolo_class == "target_close" and mean_depth is None:
            manual_depth, bucket_choice = self._prompt_manual_depth()
            if manual_depth is None:  # User cancelled
                return
            mean_depth = manual_depth
            std_depth = 0.0  # No std for manual entry
            manual_bucket = bucket_choice  # "near", "mid", or "far"
        else:
            manual_bucket = None
        
        main = self.main_combo.currentText()
        sub = self.sub_combo.currentText()
        base = pair.rgb.stem
        
        # Get source folder name for tracking flight origin
        source_folder = self.folder.name if self.folder else "unknown"
        
        # Build target filename based on class
        if yolo_class == "target_far":
            # Simple filename without direction/position
            target_base = f"{base}-{source_folder}-far"
            # Simplified bucket: no direction/position subdirectories
            bucket = (None, None, "far")
            mean_depth = 999.0  # Sentinel value for CSV (beyond sensor range)
            std_depth = 0.0
        elif mean_depth is not None and std_depth is not None:
            # target_close with depth data
            target_base = f"{base}-{source_folder}-{main}_{sub}-depth-{mean_depth:.2f}m-std-{std_depth:.2f}m"
            # Use manual bucket if provided, otherwise calculate from depth
            if manual_bucket:
                bucket = (main, sub, manual_bucket)
            else:
                bucket = bucket_from_meta(main, sub, mean_depth)
        else:
            # target_close without depth (should have been handled by manual dialog above)
            self.status_label.setText("Fehler: target_close ohne Tiefendaten.")
            return
        
        # Prepare training bucket paths
        target_root = Path(self.training_root)
        ensure_bucket_structure(target_root)
        bucket_dir = target_dir(target_root, bucket)
        ensure_dir(bucket_dir)
        
        target_img = bucket_dir / f"{target_base}{pair.rgb.suffix}"
        target_label = bucket_dir / f"{target_base}.txt"
        
        # Check if this frame (by base name and source folder) already exists ANYWHERE in training
        # This prevents creating S_Bot and S_Hor annotations for the same frame
        existing_files = []
        pattern = f"{base}-{source_folder}-*{pair.rgb.suffix}"
        for existing in target_root.rglob(pattern):
            if existing != target_img:  # Don't count the exact target path
                existing_files.append(existing)
        
        if existing_files:
            # Found duplicate(s) in other bucket(s)
            existing_paths = "\n".join([str(f.relative_to(target_root)) for f in existing_files])
            reply = QtWidgets.QMessageBox.question(
                self,
                "Duplikat gefunden",
                f"Frame {base} aus {source_folder} existiert bereits:\n\n{existing_paths}\n\n"
                f"Alte Annotation(en) löschen und neue erstellen?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                self.status_label.setText("Export abgebrochen.")
                return
            # User accepted - delete all old files (images and labels)
            try:
                for old_img in existing_files:
                    if old_img.exists():
                        old_img.unlink()
                    old_label = old_img.with_suffix(".txt")
                    if old_label.exists():
                        old_label.unlink()
            except Exception as exc:
                self.status_label.setText(f"Löschen fehlgeschlagen: {exc}")
                return
        elif target_img.exists():
            # Exact same annotation already exists (same bucket)
            reply = QtWidgets.QMessageBox.question(
                self,
                "Duplikat gefunden",
                f"Frame {base} aus {source_folder} mit gleicher Annotation existiert bereits.\n"
                f"Überschreiben?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                self.status_label.setText("Export abgebrochen.")
                return
            # User accepted - delete old files
            try:
                if target_img.exists():
                    target_img.unlink()
                if target_label.exists():
                    target_label.unlink()
            except Exception as exc:
                self.status_label.setText(f"Löschen fehlgeschlagen: {exc}")
                return
        
        try:
            # Copy image to training bucket (never modify source!)
            target_img.write_bytes(pair.rgb.read_bytes())
            
            # Create YOLO label in training bucket
            try:
                with Image.open(pair.rgb) as im:
                    w, h = im.size
            except Exception:
                # Fallback to depth size if available
                if self.current_depth_size != (0, 0):
                    w, h = self.current_depth_size
                else:
                    self.status_label.setText("Konnte Bildgröße nicht bestimmen.")
                    return
            
            class_map = {"target_close": 0, "target_far": 1}
            class_id = class_map.get(yolo_class, 0)
            x_center = (self.current_bbox.left() + self.current_bbox.width() / 2) / w
            y_center = (self.current_bbox.top() + self.current_bbox.height() / 2) / h
            bw = self.current_bbox.width() / w
            bh = self.current_bbox.height() / h
            
            with open(target_label, "w", encoding="utf-8") as f:
                f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {bw:.6f} {bh:.6f}\n")
            
            # CSV log
            min_d = getattr(self, '_last_min_depth', None)
            max_d = getattr(self, '_last_max_depth', None)
            csv_row = {
                "filename": target_img.name,
                "source_folder": source_folder,
                "source_path": str(pair.rgb.absolute()),
                "bucket_dir": str(bucket_dir),
                "direction": bucket[0] if bucket[0] is not None else "N/A",
                "position": bucket[1] if bucket[1] is not None else "N/A",
                "distance_bucket": bucket[2],
                "mean_depth": f"{mean_depth:.2f}",
                "std_depth": f"{std_depth:.2f}",
                "min_depth": f"{min_d:.2f}" if min_d is not None else "N/A",
                "max_depth": f"{max_d:.2f}" if max_d is not None else "N/A",
                "yolo_class": yolo_class,
                "bbox": f"{self.current_bbox.x()},{self.current_bbox.y()},{self.current_bbox.width()},{self.current_bbox.height()}",
            }
            append_csv(target_root / "annotations.csv", csv_row)
            
            # Remove from benchmark folder if it exists there (Phase 1: move out when annotated)
            self._remove_from_benchmark(pair.rgb.stem, target_root)
            
            self.status_label.setText(f"Exportiert: {target_img.name}")
            self.last_processed = pair.rgb
            self._save_last_processed(pair.rgb)
            
        except Exception as exc:
            self.status_label.setText(f"Export fehlgeschlagen: {exc}")

    def _export_negative_sample(self, pair: FramePair) -> None:
        """Export frame as negative sample (no object present).
        
        Negative samples are used to train the model on background/no-target scenarios.
        Images are copied to negative_samples/ folder WITHOUT .txt annotation files.
        """
        target_root = Path(self.training_root)
        ensure_bucket_structure(target_root)  # Ensures negative_samples/ exists
        
        negative_dir = target_root / "negative_samples"
        ensure_dir(negative_dir)
        
        base = pair.rgb.stem
        source_folder = self.folder.name if self.folder else "unknown"
        
        # Filename: frame_NNNNNN-<source>-negative.jpg
        target_base = f"{base}-{source_folder}-negative"
        target_img = negative_dir / f"{target_base}{pair.rgb.suffix}"
        
        # Check for duplicate
        if target_img.exists():
            reply = QtWidgets.QMessageBox.question(
                self,
                "Duplikat gefunden",
                f"Negative sample {base} aus {source_folder} existiert bereits.\n"
                f"Überschreiben?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                self.status_label.setText("Export abgebrochen.")
                return
            try:
                target_img.unlink()
            except Exception as exc:
                self.status_label.setText(f"Löschen fehlgeschlagen: {exc}")
                return
        
        try:
            # Copy image (no .txt file - negative sample has no annotations)
            target_img.write_bytes(pair.rgb.read_bytes())
            
            # CSV log
            csv_row = {
                "filename": target_img.name,
                "source_folder": source_folder,
                "source_path": str(pair.rgb.absolute()),
                "bucket_dir": str(negative_dir),
                "direction": "N/A",
                "position": "N/A",
                "distance": "negative",
                "mean_depth": "N/A",
                "std_depth": "N/A",
                "min_depth": "N/A",
                "max_depth": "N/A",
                "yolo_class": "negative_sample",
                "bbox": "N/A",
            }
            append_csv(target_root / "annotations.csv", csv_row)
            
            # Remove from benchmark folder if it exists there
            self._remove_from_benchmark(pair.rgb.stem, target_root)
            
            self.status_label.setText(f"Negative Sample exportiert: {target_img.name}")
            self.last_processed = pair.rgb
            self._save_last_processed(pair.rgb)
            
        except Exception as exc:
            self.status_label.setText(f"Export fehlgeschlagen: {exc}")

    def _prompt_manual_depth(self) -> tuple[Optional[float], Optional[str]]:
        """Prompt user to manually select depth bucket when depth data is unavailable.
        
        Returns:
            (depth_value, bucket_name) tuple, or (None, None) if cancelled
        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Manuelle Tiefenangabe")
        dialog.setModal(True)
        
        layout = QtWidgets.QVBoxLayout()
        
        # Explanation
        label = QtWidgets.QLabel(
            "Keine Tiefendaten verfügbar.\n"
            "Bitte wählen Sie die Entfernungskategorie für target_close:"
        )
        layout.addWidget(label)
        
        # Bucket selection with example depths
        bucket_group = QtWidgets.QGroupBox("Entfernungskategorie")
        bucket_layout = QtWidgets.QVBoxLayout()
        
        near_radio = QtWidgets.QRadioButton("Near (<10m) - Beispiel: 5m")
        mid_radio = QtWidgets.QRadioButton("Mid (10-30m) - Beispiel: 15m")
        far_radio = QtWidgets.QRadioButton("Far (>30m) - Beispiel: 35m")
        mid_radio.setChecked(True)  # Default to mid
        
        bucket_layout.addWidget(near_radio)
        bucket_layout.addWidget(mid_radio)
        bucket_layout.addWidget(far_radio)
        bucket_group.setLayout(bucket_layout)
        layout.addWidget(bucket_group)
        
        # Custom depth input
        depth_layout = QtWidgets.QHBoxLayout()
        depth_label = QtWidgets.QLabel("Oder eigene Tiefe (m):")
        depth_input = QtWidgets.QDoubleSpinBox()
        depth_input.setRange(0.5, 100.0)
        depth_input.setValue(15.0)
        depth_input.setSingleStep(0.5)
        depth_layout.addWidget(depth_label)
        depth_layout.addWidget(depth_input)
        layout.addLayout(depth_layout)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            # Determine bucket based on selection or custom depth
            custom_depth = depth_input.value()
            
            if near_radio.isChecked():
                return (5.0, "near")
            elif mid_radio.isChecked():
                return (15.0, "mid")
            elif far_radio.isChecked():
                return (35.0, "far")
            else:
                # Use custom depth and calculate bucket
                if custom_depth < 10:
                    return (custom_depth, "near")
                elif custom_depth <= 30:
                    return (custom_depth, "mid")
                else:
                    return (custom_depth, "far")
        
        return (None, None)

    def _write_yolo_label(self, img_path: Path, bbox: QtCore.QRect, yolo_class: str) -> None:
        # Map class text to ID
        class_map = {"target_close": 0, "target_far": 1}
        class_id = class_map.get(yolo_class, 0)
        try:
            with Image.open(img_path) as im:
                w, h = im.size
        except Exception:
            # Fallback to depth size if available
            if self.current_depth_size != (0, 0):
                w, h = self.current_depth_size
            else:
                self.status_label.setText("Konnte Bildgröße nicht bestimmen.")
                return
        x_center = (bbox.left() + bbox.width() / 2) / w
        y_center = (bbox.top() + bbox.height() / 2) / h
        bw = bbox.width() / w
        bh = bbox.height() / h
        label_path = img_path.with_suffix(".txt")
        try:
            with open(label_path, "w", encoding="utf-8") as f:
                f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {bw:.6f} {bh:.6f}\n")
            self.status_label.setText(f"Label gespeichert: {label_path.name}")
        except Exception as exc:
            self.status_label.setText(f"Label-Fehler: {exc}")
            return
        return label_path

    # -------------------------------------------------------------------------
    # Tracking methods
    # -------------------------------------------------------------------------
    def _load_frame_as_numpy(self, path: Path) -> Optional[np.ndarray]:
        """Load an RGB image as a numpy array (BGR format for OpenCV)."""
        try:
            img = cv2.imread(str(path))
            return img
        except Exception:
            return None

    def _init_tracker(self, frame: np.ndarray, bbox: QtCore.QRect) -> bool:
        """Initialize the tracker with the given frame and bounding box.
        
        Tracker type is configured by ViewerWindow.TRACKER_TYPE:
        - CSRT: Best accuracy, slowest (~30 FPS)
        - KCF: Balanced speed/accuracy (~100+ FPS) - good for Jetson
        - MOSSE: Fastest (~1000+ FPS), lowest accuracy
        """
        try:
            print(f"[TRACKER DEBUG] Initializing {self.TRACKER_TYPE} tracker with bbox ({bbox.x()}, {bbox.y()}, {bbox.width()}, {bbox.height()}) on frame shape {frame.shape}")
            
            # Create tracker based on configuration
            if self.TRACKER_TYPE == 'KCF':
                self._tracker = cv2.legacy.TrackerKCF_create()
                tracker_name = "KCF"
            elif self.TRACKER_TYPE == 'MOSSE':
                self._tracker = cv2.legacy.TrackerMOSSE_create()
                tracker_name = "MOSSE"
            else:  # Default to CSRT
                self._tracker = cv2.legacy.TrackerCSRT_create()
                tracker_name = "CSRT"
            
            print(f"[TRACKER DEBUG] Tracker object created: {type(self._tracker)}")
            
            # Convert QRect to (x, y, w, h) tuple
            rect = (bbox.x(), bbox.y(), bbox.width(), bbox.height())
            success = self._tracker.init(frame, rect)
            self._tracker_initialized = success
            
            print(f"[TRACKER DEBUG] Tracker init returned: success={success}, initialized={self._tracker_initialized}")
            
            if success:
                self.status_label.setText(f"{tracker_name} Tracker initialisiert")
            return success
                
        except Exception as e:
            print(f"[TRACKER DEBUG] Exception during init: {e}")
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"Tracker-Init fehlgeschlagen: {e}")
            self._tracker = None
            self._tracker_initialized = False
            return False

    def _update_tracker(self, frame: np.ndarray) -> Optional[QtCore.QRect]:
        """Update tracker with new frame and return predicted bbox, or None if failed."""
        if not self._tracker or not self._tracker_initialized:
            print(f"[TRACKER DEBUG] Update failed: tracker={'exists' if self._tracker else 'None'}, initialized={self._tracker_initialized}")
            return None
        try:
            print(f"[TRACKER DEBUG] Calling tracker.update() on frame shape {frame.shape}")
            success, bbox = self._tracker.update(frame)
            print(f"[TRACKER DEBUG] Tracker update returned: success={success}, bbox={bbox if success else 'N/A'}")
            if success:
                x, y, w, h = [int(v) for v in bbox]
                print(f"[TRACKER DEBUG] Predicted bbox: ({x}, {y}, {w}, {h})")
                return QtCore.QRect(x, y, w, h)
            print("[TRACKER DEBUG] Tracking failed - success=False")
            return None
        except Exception as e:
            print(f"[TRACKER DEBUG] Exception during update: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _reset_tracker(self) -> None:
        """Reset tracker state."""
        self._tracker = None
        self._tracker_initialized = False

    def _on_track_checkbox_changed(self, state: int) -> None:
        """Handle track checkbox state change - initialize tracker when enabled."""
        if state == QtCore.Qt.Checked.value:
            # Initialize tracker with current frame and bbox
            if self.pairs and self.current_bbox:
                pair = self.pairs[self.current_index]
                frame = self._load_frame_as_numpy(pair.rgb)
                if frame is not None:
                    if self._init_tracker(frame, self.current_bbox):
                        self.status_label.setText("Tracker initialisiert")
                    else:
                        # Block signals to avoid re-entrant calls
                        self.track_checkbox.blockSignals(True)
                        self.track_checkbox.setChecked(False)
                        self.track_checkbox.blockSignals(False)
                else:
                    self.status_label.setText("Frame konnte nicht geladen werden")
                    # Block signals to avoid re-entrant calls
                    self.track_checkbox.blockSignals(True)
                    self.track_checkbox.setChecked(False)
                    self.track_checkbox.blockSignals(False)
        else:
            self._reset_tracker()

    def _track_bbox_to_frame(self, target_index: int) -> Optional[QtCore.QRect]:
        """Track bbox from current frame to target frame, stepping through intermediates."""
        if not self._tracker_initialized or not self.pairs:
            print(f"[TRACKER DEBUG] _track_bbox_to_frame: initialized={self._tracker_initialized}, pairs={len(self.pairs) if self.pairs else 0}")
            return None
        
        start_idx = self.current_index
        step = 1 if target_index > start_idx else -1
        
        print(f"[TRACKER DEBUG] Tracking from frame {start_idx} to {target_index} (step={step})")
        
        # Track through each intermediate frame
        current_bbox: Optional[QtCore.QRect] = self.current_bbox
        for idx in range(start_idx + step, target_index + step, step):
            # Handle wrap-around
            actual_idx = idx % len(self.pairs)
            print(f"[TRACKER DEBUG] Processing intermediate frame {actual_idx}")
            frame = self._load_frame_as_numpy(self.pairs[actual_idx].rgb)
            if frame is None:
                print(f"[TRACKER DEBUG] Failed to load frame {actual_idx}")
                return None
            current_bbox = self._update_tracker(frame)
            if current_bbox is None:
                print(f"[TRACKER DEBUG] Tracking failed at frame {actual_idx}")
                return None
            print(f"[TRACKER DEBUG] Successfully tracked to frame {actual_idx}: bbox={current_bbox.x()},{current_bbox.y()},{current_bbox.width()},{current_bbox.height()}")
        
        print(f"[TRACKER DEBUG] Tracking complete! Final bbox: {current_bbox.x() if current_bbox else 'None'},{current_bbox.y() if current_bbox else 'None'}")
        return current_bbox

    def _clear_selection(self) -> None:
        self.current_bbox = None
        self._last_mean_depth = None
        self._last_std_depth = None
        self._last_min_depth = None
        self._last_max_depth = None
        self.mean_label.setText("Mean depth: -")
        self.bbox_label.setText("BBox: -")
        if isinstance(self.rgb_view, SelectableLabel):
            self.rgb_view.clear_rect()
        
        # Clear export settings text overlay
        self.rgb_view.set_export_settings_text("")
        
        # Disable and reset tracking - block signals to avoid re-entrant calls
        self.track_checkbox.blockSignals(True)
        self.track_checkbox.setChecked(False)
        self.track_checkbox.blockSignals(False)
        self.track_checkbox.setEnabled(False)
        self._reset_tracker()

    def _choose_training_root(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Training Root wählen")
        if folder:
            self.training_root_edit.setText(folder)
            self._on_training_root_changed(folder)

    def _on_training_root_changed(self, text: str) -> None:
        if not text:
            return
        root_path = Path(text)
        try:
            root_path.mkdir(parents=True, exist_ok=True)
            self.training_root = str(root_path)
            self.training_status.setText("Root gesetzt.")
            self._save_training_root(self.training_root)
        except Exception as exc:
            self.training_status.setText(f"Fehler beim Setzen: {exc}")

    def _load_training_root(self) -> str:
        cfg = Path.home() / ".svo_viewer_config"
        if cfg.exists():
            try:
                return cfg.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return DEFAULT_TRAINING_ROOT

    def _save_training_root(self, value: str) -> None:
        cfg = Path.home() / ".svo_viewer_config"
        try:
            cfg.write_text(value, encoding="utf-8")
        except Exception:
            pass

    def _load_last_processed(self) -> Optional[Path]:
        state = Path.home() / ".svo_viewer_state"
        if state.exists():
            try:
                txt = state.read_text(encoding="utf-8").strip()
                if txt:
                    return Path(txt)
            except Exception:
                return None
        return None

    def _save_last_processed(self, path: Path) -> None:
        state = Path.home() / ".svo_viewer_state"
        try:
            state.write_text(str(path), encoding="utf-8")
        except Exception:
            pass

    def _rerender_current(self, keep_selection: bool = False) -> None:
        if self.pairs:
            idx = min(self.current_index, len(self.pairs) - 1)
            self._show_pair(self.pairs[idx], keep_selection=keep_selection)

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        # No special handling; resize is throttled via _schedule_render
        return super().eventFilter(source, event)

    def _create_benchmark_images(self) -> None:
        """Create benchmark images by copying all unannotated frames to benchmark/ folder."""
        if not self.training_root:
            QtWidgets.QMessageBox.warning(
                self,
                "Kein Training Root",
                "Bitte wählen Sie zuerst einen Training Root Ordner."
            )
            return
        
        if not self.folder:
            QtWidgets.QMessageBox.warning(
                self,
                "Keine Frames geladen",
                "Bitte laden Sie zuerst einen Ordner mit Frames."
            )
            return
        
        training_root_path = Path(self.training_root)
        source_folder_path = Path(self.folder)
        
        if not training_root_path.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Ordner nicht gefunden",
                f"Training Root Ordner existiert nicht:\n{self.training_root}"
            )
            return
        
        if not source_folder_path.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Ordner nicht gefunden",
                f"Frame-Ordner existiert nicht:\n{self.folder}"
            )
            return
        
        # Confirm action
        reply = QtWidgets.QMessageBox.question(
            self,
            "Benchmark erstellen",
            f"Alle nicht-annotierten Frames aus:\n{source_folder_path.name}\n\n"
            f"werden in den Benchmark-Ordner kopiert.\n\n"
            "Dies kann einige Minuten dauern. Fortfahren?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        
        # Create and show progress dialog
        progress_dialog = QtWidgets.QProgressDialog(
            "Initialisiere Benchmark-Erstellung...",
            "Abbrechen",
            0, 100,
            self
        )
        progress_dialog.setWindowTitle("Benchmark erstellen")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)  # Show immediately
        progress_dialog.setValue(0)
        
        # Create and start worker thread
        self.benchmark_worker = BenchmarkWorker(source_folder_path, training_root_path)
        
        def on_progress(current: int, total: int, msg: str) -> None:
            if total > 0:
                progress_dialog.setMaximum(total)
                progress_dialog.setValue(current)
            progress_dialog.setLabelText(msg)
        
        def on_finished(copied: int) -> None:
            progress_dialog.close()
            QtWidgets.QMessageBox.information(
                self,
                "Benchmark erstellt",
                f"Erfolgreich {copied} nicht-annotierte Frames in den Benchmark-Ordner kopiert."
            )
            self.benchmark_worker = None
        
        def on_error(error_msg: str) -> None:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self,
                "Fehler",
                f"Fehler beim Erstellen des Benchmarks:\n{error_msg}"
            )
            self.benchmark_worker = None
        
        def on_cancelled() -> None:
            if hasattr(self, 'benchmark_worker') and self.benchmark_worker:
                self.benchmark_worker.cancel()
        
        self.benchmark_worker.progress.connect(on_progress)
        self.benchmark_worker.finished.connect(on_finished)
        self.benchmark_worker.error.connect(on_error)
        progress_dialog.canceled.connect(on_cancelled)
        
        self.benchmark_worker.start()


def run() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = ViewerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
