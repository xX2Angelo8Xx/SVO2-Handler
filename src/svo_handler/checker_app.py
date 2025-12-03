"""YOLO Annotation Checker - Visual verification of bounding box annotations."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
from PIL import Image, ImageDraw

# YOLO training folder structure
DIRECTIONS = ["0_far", "1_S", "2_SE", "3_E", "4_NE", "5_N", "6_NW", "7_W", "8_SW"]
POSITIONS = ["Bot", "Horizon", "Top"]
DISTANCES = ["near", "mid", "far"]


class AnnotationPair:
    """Pair of image and YOLO label file with bucket location."""
    def __init__(self, image: Path, label: Optional[Path] = None, bucket_path: str = ""):
        self.image = image
        self.label = label if label and label.exists() else None
        self.bucket_path = bucket_path  # e.g., "1_S/Bot/near"


class ZoomableLabel(QtWidgets.QLabel):
    """Label widget with zoom and pan support."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._zoom: float = 1.0
        self._pan_x: int = 0
        self._pan_y: int = 0
        self._panning: bool = False
        self._last_pos: Optional[QtCore.QPoint] = None
        self.setMouseTracking(True)
    
    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        """Set the pixmap and reset zoom/pan."""
        self._pixmap = pixmap
        self._zoom = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._update_display()
    
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handle mouse wheel for zooming."""
        if self._pixmap is None:
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
            new_zoom = min(self._zoom * 1.2, 5.0)  # Max 5x zoom
        else:
            new_zoom = max(self._zoom / 1.2, 1.0)  # Min 1x zoom
        
        if new_zoom == old_zoom:
            return
        
        # Get image dimensions
        pw = self._pixmap.width()
        ph = self._pixmap.height()
        
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
        self._update_display()
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Start panning when zoomed in."""
        if self._zoom > 1.0 and event.button() == QtCore.Qt.LeftButton:
            self._panning = True
            self._last_pos = event.position().toPoint()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Pan the image when dragging."""
        if self._panning and self._last_pos:
            delta = event.position().toPoint() - self._last_pos
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._last_pos = event.position().toPoint()
            self._update_display()
        elif self._zoom > 1.0:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Stop panning."""
        if event.button() == QtCore.Qt.LeftButton:
            self._panning = False
            self.setCursor(QtCore.Qt.OpenHandCursor if self._zoom > 1.0 else QtCore.Qt.ArrowCursor)
    
    def _update_display(self) -> None:
        """Update the displayed image with current zoom and pan."""
        if self._pixmap is None:
            return
        
        if self._zoom == 1.0:
            # No zoom - just scale to fit
            scaled = self._pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            super().setPixmap(scaled)
        else:
            # Zoomed - crop and scale
            pw = self._pixmap.width()
            ph = self._pixmap.height()
            
            # Calculate visible region (crop)
            crop_w = int(pw / self._zoom)
            crop_h = int(ph / self._zoom)
            
            # Center point with pan offset
            center_x = pw // 2 - int(self._pan_x / self._zoom)
            center_y = ph // 2 - int(self._pan_y / self._zoom)
            
            # Clamp crop region
            crop_x = max(0, min(center_x - crop_w // 2, pw - crop_w))
            crop_y = max(0, min(center_y - crop_h // 2, ph - crop_h))
            
            # Crop and scale
            cropped = self._pixmap.copy(crop_x, crop_y, crop_w, crop_h)
            scaled = cropped.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            super().setPixmap(scaled)


class BarChartWidget(QtWidgets.QWidget):
    """Custom widget to draw interactive bar charts."""
    
    bar_clicked = QtCore.Signal(str)  # Emitted when a bar is clicked (label)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: List[Tuple[str, int]] = []  # [(label, value), ...]
        self.title: str = ""
        self.selected_bar: Optional[int] = None
        self.setMinimumHeight(300)
        self.setCursor(QtCore.Qt.PointingHandCursor)
    
    def set_data(self, data: List[Tuple[str, int]], title: str = "") -> None:
        """Set chart data and title."""
        self.data = data
        self.title = title
        self.selected_bar = None
        self.update()
    
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Draw the bar chart."""
        if not self.data:
            return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Margins
        margin_left = 80
        margin_right = 20
        margin_top = 60
        margin_bottom = 80
        
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        
        if chart_width <= 0 or chart_height <= 0:
            return
        
        # Draw title
        if self.title:
            painter.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
            painter.drawText(QtCore.QRect(0, 10, width, 40), QtCore.Qt.AlignCenter, self.title)
        
        # Find max value
        max_value = max(val for _, val in self.data) if self.data else 1
        if max_value == 0:
            max_value = 1
        
        # Calculate bar dimensions
        num_bars = len(self.data)
        bar_width = (chart_width / num_bars) * 0.7  # 70% of available space
        spacing = (chart_width / num_bars) * 0.3 / 2  # Remaining space split
        
        # Draw bars
        for i, (label, value) in enumerate(self.data):
            bar_height = (value / max_value) * chart_height
            x = margin_left + i * (chart_width / num_bars) + spacing
            y = margin_top + chart_height - bar_height
            
            # Choose color
            if self.selected_bar == i:
                color = QtGui.QColor(76, 175, 80)  # Green when selected
            else:
                color = QtGui.QColor(33, 150, 243)  # Blue
            
            # Draw bar
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(x, y, bar_width, bar_height))
            
            # Draw value on top of bar
            painter.setPen(QtCore.Qt.black)
            painter.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))
            value_rect = QtCore.QRectF(x, y - 25, bar_width, 20)
            painter.drawText(value_rect, QtCore.Qt.AlignCenter, str(value))
            
            # Draw label below bar
            painter.save()
            painter.translate(x + bar_width / 2, height - margin_bottom + 10)
            painter.rotate(45)
            painter.setFont(QtGui.QFont("Arial", 9))
            painter.drawText(0, 0, label)
            painter.restore()
        
        # Draw Y-axis
        painter.setPen(QtGui.QColor(100, 100, 100))
        painter.drawLine(margin_left, margin_top, margin_left, margin_top + chart_height)
        
        # Draw X-axis
        painter.drawLine(margin_left, margin_top + chart_height, 
                        margin_left + chart_width, margin_top + chart_height)
        
        # Draw Y-axis labels
        painter.setFont(QtGui.QFont("Arial", 9))
        for i in range(6):  # 0, 20%, 40%, 60%, 80%, 100%
            val = int(max_value * i / 5)
            y_pos = margin_top + chart_height - (chart_height * i / 5)
            painter.drawText(QtCore.QRectF(0, y_pos - 10, margin_left - 10, 20), 
                           QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, str(val))
            # Draw grid line
            painter.setPen(QtGui.QColor(200, 200, 200, 100))
            painter.drawLine(margin_left, int(y_pos), margin_left + chart_width, int(y_pos))
            painter.setPen(QtGui.QColor(100, 100, 100))
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle bar clicks."""
        if not self.data:
            return
        
        margin_left = 80
        margin_top = 60
        margin_bottom = 80
        chart_width = self.width() - margin_left - 20
        chart_height = self.height() - margin_top - margin_bottom
        
        num_bars = len(self.data)
        spacing = (chart_width / num_bars) * 0.3 / 2
        bar_width = (chart_width / num_bars) * 0.7
        
        # Check which bar was clicked
        for i, (label, value) in enumerate(self.data):
            x = margin_left + i * (chart_width / num_bars) + spacing
            if x <= event.position().x() <= x + bar_width:
                self.selected_bar = i
                self.update()
                self.bar_clicked.emit(label)
                return


class StatisticsDialog(QtWidgets.QDialog):
    """Interactive statistics dialog with drill-down bar charts."""
    
    def __init__(self, training_root: Path, parent=None):
        super().__init__(parent)
        self.training_root = training_root
        self.setWindowTitle("Bucket Statistiken")
        self.resize(900, 700)
        
        # Navigation state
        self.current_level = "directions"  # "directions", "positions", "distances"
        self.selected_direction: Optional[str] = None
        
        # UI setup
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title and navigation
        nav_layout = QtWidgets.QHBoxLayout()
        self.back_btn = QtWidgets.QPushButton("← Zurück")
        self.back_btn.clicked.connect(self._go_back)
        self.back_btn.setVisible(False)
        nav_layout.addWidget(self.back_btn)
        
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #42a5f5;")
        nav_layout.addWidget(self.title_label, 1)
        layout.addLayout(nav_layout)
        
        # Bar chart
        self.chart = BarChartWidget()
        self.chart.bar_clicked.connect(self._on_bar_clicked)
        layout.addWidget(self.chart)
        
        # Close button
        close_btn = QtWidgets.QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        # Load initial data
        self._show_directions()
    
    def _show_directions(self) -> None:
        """Show main direction totals."""
        self.current_level = "directions"
        self.selected_direction = None
        self.back_btn.setVisible(False)
        
        data = []
        total = 0
        
        for direction in DIRECTIONS:
            count = self._count_direction(direction)
            if count > 0:
                data.append((direction, count))
                total += count
        
        self.title_label.setText(f"Gesamt: {total} Bilder | Klicken Sie auf einen Balken für Details")
        self.chart.set_data(data, "Bilder pro Richtung")
    
    def _show_positions(self, direction: str) -> None:
        """Show position breakdown for selected direction."""
        self.current_level = "positions"
        self.selected_direction = direction
        self.back_btn.setVisible(True)
        
        data = []
        total = 0
        
        if direction == "0_far":
            # Special case: 0_far has no position breakdown
            self.title_label.setText(f"{direction}: Keine Positions-Unterteilung")
            self.chart.set_data([], "")
            return
        
        for pos in POSITIONS:
            count = self._count_position(direction, pos)
            if count > 0:
                data.append((pos, count))
                total += count
        
        self.title_label.setText(f"{direction}: {total} Bilder | Klicken für Distanz-Details")
        self.chart.set_data(data, f"{direction} - Bilder pro Position")
    
    def _show_distances(self, direction: str) -> None:
        """Show distance breakdown across all positions for direction."""
        self.current_level = "distances"
        self.back_btn.setVisible(True)
        
        # Aggregate distances across all positions
        distance_totals = {dist: 0 for dist in DISTANCES}
        
        for pos in POSITIONS:
            for dist in DISTANCES:
                bucket_path = self.training_root / direction / pos / dist
                if bucket_path.exists():
                    count = len(list(bucket_path.glob("*.jpg")))
                    distance_totals[dist] += count
        
        data = [(dist, count) for dist, count in distance_totals.items() if count > 0]
        total = sum(count for _, count in data)
        
        self.title_label.setText(f"{direction}: {total} Bilder nach Distanz")
        self.chart.set_data(data, f"{direction} - Bilder pro Distanz (alle Positionen)")
    
    def _count_direction(self, direction: str) -> int:
        """Count total images in a direction."""
        total = 0
        if direction == "0_far":
            bucket_path = self.training_root / direction
            if bucket_path.exists():
                total = len(list(bucket_path.glob("*.jpg")))
        else:
            for pos in POSITIONS:
                for dist in DISTANCES:
                    bucket_path = self.training_root / direction / pos / dist
                    if bucket_path.exists():
                        total += len(list(bucket_path.glob("*.jpg")))
        return total
    
    def _count_position(self, direction: str, position: str) -> int:
        """Count total images in a direction/position combination."""
        total = 0
        for dist in DISTANCES:
            bucket_path = self.training_root / direction / position / dist
            if bucket_path.exists():
                total += len(list(bucket_path.glob("*.jpg")))
        return total
    
    def _on_bar_clicked(self, label: str) -> None:
        """Handle bar click for drill-down."""
        if self.current_level == "directions":
            # Clicked on a direction -> show positions
            self._show_positions(label)
        elif self.current_level == "positions":
            # Clicked on a position -> show distances for the whole direction
            if self.selected_direction:
                self._show_distances(self.selected_direction)
    
    def _go_back(self) -> None:
        """Navigate back to previous level."""
        if self.current_level == "positions":
            self._show_directions()
        elif self.current_level == "distances":
            if self.selected_direction:
                self._show_positions(self.selected_direction)


class CheckerWindow(QtWidgets.QMainWindow):
    """Main window for annotation checker."""
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YOLO Annotation Checker")
        self.resize(1400, 900)
        
        self.training_root: Optional[Path] = None
        self.current_direction: str = "0_far"
        self.view_mode: str = "all"  # "all" = all in direction, "specific" = specific bucket
        self.pairs: List[AnnotationPair] = []
        self.current_index: int = 0
        self._bucket_stats: dict = {}  # Statistics for current direction
        
        self._init_ui()
        
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        
        # Top bar: folder selection
        top_bar = QtWidgets.QHBoxLayout()
        self.folder_label = QtWidgets.QLabel("Kein Ordner geladen")
        self.folder_label.setStyleSheet("font-weight: bold;")
        folder_btn = QtWidgets.QPushButton("YOLO Training Ordner öffnen...")
        folder_btn.clicked.connect(self._choose_training_root)
        stats_btn = QtWidgets.QPushButton("📊 Statistiken anzeigen")
        stats_btn.clicked.connect(self._show_detailed_statistics)
        top_bar.addWidget(self.folder_label)
        top_bar.addWidget(folder_btn)
        top_bar.addWidget(stats_btn)
        layout.addLayout(top_bar)
        
        # Bucket navigation with mode selection
        nav_group = QtWidgets.QGroupBox("Bucket Navigation")
        nav_layout = QtWidgets.QVBoxLayout()
        
        # Row 1: Direction selector
        dir_row = QtWidgets.QHBoxLayout()
        dir_row.addWidget(QtWidgets.QLabel("Direction:"))
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(DIRECTIONS)
        self.direction_combo.currentTextChanged.connect(self._on_direction_changed)
        dir_row.addWidget(self.direction_combo)
        
        # Stats label showing image counts
        self.stats_label = QtWidgets.QLabel("")
        self.stats_label.setStyleSheet("color: #42a5f5; font-weight: bold;")
        dir_row.addWidget(self.stats_label)
        dir_row.addStretch()
        nav_layout.addLayout(dir_row)
        
        # Row 2: View mode selector
        mode_row = QtWidgets.QHBoxLayout()
        self.mode_all_radio = QtWidgets.QRadioButton("Alle Bilder in Direction")
        self.mode_all_radio.setChecked(True)
        self.mode_all_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_all_radio)
        
        self.mode_specific_radio = QtWidgets.QRadioButton("Spezifischer Bucket:")
        self.mode_specific_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_specific_radio)
        mode_row.addStretch()
        nav_layout.addLayout(mode_row)
        
        # Row 3: Specific bucket selectors (disabled when "all" mode)
        bucket_row = QtWidgets.QHBoxLayout()
        bucket_row.addWidget(QtWidgets.QLabel("Position:"))
        self.position_combo = QtWidgets.QComboBox()
        self.position_combo.addItems(POSITIONS)
        self.position_combo.currentTextChanged.connect(self._on_bucket_changed)
        bucket_row.addWidget(self.position_combo)
        
        bucket_row.addWidget(QtWidgets.QLabel("Distance:"))
        self.distance_combo = QtWidgets.QComboBox()
        self.distance_combo.addItems(DISTANCES)
        self.distance_combo.currentTextChanged.connect(self._on_bucket_changed)
        bucket_row.addWidget(self.distance_combo)
        bucket_row.addStretch()
        nav_layout.addLayout(bucket_row)
        
        nav_group.setLayout(nav_layout)
        layout.addWidget(nav_group)
        
        # Current location label
        self.location_label = QtWidgets.QLabel("Keine Bilder geladen")
        self.location_label.setStyleSheet("color: #aaa; font-style: italic;")
        layout.addWidget(self.location_label)
        
        # Image display with annotations (now with zoom support)
        self.image_label = ZoomableLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setStyleSheet("border: 2px solid #333; background-color: #1e1e1e;")
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.image_label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, stretch=1)
        
        # Navigation controls
        controls = QtWidgets.QHBoxLayout()
        self.prev_btn_5 = QtWidgets.QPushButton("◀◀ -5")
        self.prev_btn = QtWidgets.QPushButton("◀ -1")
        self.index_label = QtWidgets.QLabel("0 / 0")
        self.index_label.setAlignment(QtCore.Qt.AlignCenter)
        self.index_label.setMinimumWidth(200)
        self.next_btn = QtWidgets.QPushButton("+1 ▶")
        self.next_btn_5 = QtWidgets.QPushButton("+5 ▶▶")
        
        # Reclassify button (Phase 2)
        self.reclassify_btn = QtWidgets.QPushButton("✏️ Neu klassifizieren")
        self.reclassify_btn.setToolTip("Bild in anderen Bucket verschieben")
        self.reclassify_btn.clicked.connect(self._reclassify_current_image)
        
        self.prev_btn_5.clicked.connect(lambda: self._navigate(-5))
        self.prev_btn.clicked.connect(lambda: self._navigate(-1))
        self.next_btn.clicked.connect(lambda: self._navigate(1))
        self.next_btn_5.clicked.connect(lambda: self._navigate(5))
        
        controls.addWidget(self.prev_btn_5)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.index_label)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.next_btn_5)
        controls.addStretch()
        controls.addWidget(self.reclassify_btn)
        layout.addLayout(controls)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("Bereit - Scroll zum Zoomen, Drag zum Verschieben")
        layout.addWidget(self.status_label)
        
        # Initial state: disable navigation until folder is loaded
        self._set_navigation_enabled(False)
        
    def _set_navigation_enabled(self, enabled: bool) -> None:
        """Enable or disable navigation controls."""
        self.direction_combo.setEnabled(enabled)
        self.mode_all_radio.setEnabled(enabled)
        self.mode_specific_radio.setEnabled(enabled)
        self.prev_btn_5.setEnabled(enabled)
        self.prev_btn.setEnabled(enabled)
        self.next_btn.setEnabled(enabled)
        self.next_btn_5.setEnabled(enabled)
        self.reclassify_btn.setEnabled(enabled and len(self.pairs) > 0)
        self._update_bucket_controls()
        
    def _update_bucket_controls(self) -> None:
        """Update position/distance controls based on mode and direction."""
        direction = self.direction_combo.currentText()
        is_far = direction == "0_far"
        is_specific = self.mode_specific_radio.isChecked()
        
        # Disable position/distance for far or when in "all" mode
        enabled = not is_far and is_specific and self.training_root is not None
        self.position_combo.setEnabled(enabled)
        self.distance_combo.setEnabled(enabled)
        
    def _choose_training_root(self) -> None:
        """Open folder dialog to select YOLO training root."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, 
            "YOLO Training Ordner wählen"
        )
        if folder:
            self.training_root = Path(folder)
            self.folder_label.setText(f"Root: {self.training_root.name}")
            self._set_navigation_enabled(True)
            # Load first direction
            self._on_direction_changed()
    
    def _show_detailed_statistics(self) -> None:
        """Show enhanced interactive statistics dialog with bar charts."""
        if not self.training_root:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Daten",
                "Bitte laden Sie zuerst einen YOLO Training Ordner."
            )
            return
        
        # Create interactive statistics dialog
        dialog = StatisticsDialog(self.training_root, self)
        dialog.exec()
            
            
    def _on_mode_changed(self) -> None:
        """Handle view mode change (all vs specific bucket)."""
        if self.mode_all_radio.isChecked():
            self.view_mode = "all"
        else:
            self.view_mode = "specific"
        self._update_bucket_controls()
        self._load_images()
        
    def _on_direction_changed(self) -> None:
        """Handle direction change - calculate stats and load images."""
        if not self.training_root:
            return
        
        self.current_direction = self.direction_combo.currentText()
        self._calculate_bucket_stats()
        self._update_bucket_controls()
        self._load_images()
        
    def _on_bucket_changed(self) -> None:
        """Handle specific bucket selection change."""
        if self.view_mode == "specific":
            self._load_images()
            
    def _calculate_bucket_stats(self) -> None:
        """Calculate image counts for all buckets in current direction."""
        self._bucket_stats.clear()
        
        if not self.training_root:
            return
            
        direction = self.current_direction
        total = 0
        
        if direction == "0_far":
            # Just one folder
            bucket_path = self.training_root / direction
            if bucket_path.exists():
                count = len(list(bucket_path.glob("*.jpg")))
                self._bucket_stats["0_far"] = count
                total = count
        else:
            # Iterate through all position/distance combinations
            for pos in POSITIONS:
                for dist in DISTANCES:
                    bucket_path = self.training_root / direction / pos / dist
                    if bucket_path.exists():
                        count = len(list(bucket_path.glob("*.jpg")))
                        key = f"{pos}/{dist}"
                        self._bucket_stats[key] = count
                        total += count
        
        # Update stats label
        if total > 0:
            stats_text = f"Gesamt: {total} Bilder"
            if direction != "0_far" and len(self._bucket_stats) > 0:
                # Show breakdown
                breakdown = ", ".join([f"{k}: {v}" for k, v in self._bucket_stats.items() if v > 0])
                stats_text += f" ({breakdown})"
            self.stats_label.setText(stats_text)
        else:
            self.stats_label.setText("Keine Bilder gefunden")
            
    def _load_images(self) -> None:
        """Load images based on current mode and selection."""
        if not self.training_root:
            return
            
        self.pairs = []
        direction = self.current_direction
        
        if self.view_mode == "all":
            # Load all images from this direction
            if direction == "0_far":
                bucket_path = self.training_root / direction
                if bucket_path.exists():
                    self._load_from_bucket(bucket_path, direction)
            else:
                # Load from all position/distance combinations in order
                for pos in POSITIONS:
                    for dist in DISTANCES:
                        bucket_path = self.training_root / direction / pos / dist
                        if bucket_path.exists():
                            rel_path = f"{direction}/{pos}/{dist}"
                            self._load_from_bucket(bucket_path, rel_path)
        else:
            # Load from specific bucket only
            if direction == "0_far":
                bucket_path = self.training_root / direction
                if bucket_path.exists():
                    self._load_from_bucket(bucket_path, direction)
            else:
                position = self.position_combo.currentText()
                distance = self.distance_combo.currentText()
                bucket_path = self.training_root / direction / position / distance
                rel_path = f"{direction}/{position}/{distance}"
                if bucket_path.exists():
                    self._load_from_bucket(bucket_path, rel_path)
                    
        self.current_index = 0
        self._update_display()
        
        # Update reclassify button state based on loaded images
        self.reclassify_btn.setEnabled(len(self.pairs) > 0)
        
    def _load_from_bucket(self, bucket_path: Path, relative_path: str) -> None:
        """Load all images from a specific bucket."""
        images = sorted(bucket_path.glob("*.jpg"))
        for img in images:
            label = img.with_suffix(".txt")
            self.pairs.append(AnnotationPair(img, label, relative_path))
        
    def _navigate(self, delta: int) -> None:
        """Navigate through images with auto-advance across buckets in 'all' mode."""
        if not self.pairs:
            return
            
        new_index = self.current_index + delta
        
        # Clamp to valid range
        new_index = max(0, min(new_index, len(self.pairs) - 1))
        
        if new_index != self.current_index:
            self.current_index = new_index
            self._update_display()
            
    def _update_display(self) -> None:
        """Update image display with annotations overlay."""
        if not self.pairs:
            self.image_label.setText("Keine Bilder geladen")
            self.index_label.setText("0 / 0")
            self.location_label.setText("")
            return
            
        pair = self.pairs[self.current_index]
        
        # Show current location (bucket path)
        self.location_label.setText(f"📁 {pair.bucket_path}")
        
        # Update index label with bucket-specific info
        if self.view_mode == "all":
            # Show global position and current bucket info
            # Count images in current bucket for context
            current_bucket_images = [p for p in self.pairs if p.bucket_path == pair.bucket_path]
            bucket_index = current_bucket_images.index(pair) + 1 if pair in current_bucket_images else 0
            self.index_label.setText(
                f"Gesamt: {self.current_index + 1} / {len(self.pairs)} | "
                f"Bucket: {bucket_index} / {len(current_bucket_images)}"
            )
        else:
            # Just show position in current bucket
            self.index_label.setText(f"{self.current_index + 1} / {len(self.pairs)}")
        
        # Load and display image with annotations
        try:
            img = Image.open(pair.image)
            img_width, img_height = img.size
            
            # Draw bounding boxes if label exists
            if pair.label:
                draw = ImageDraw.Draw(img)
                
                # Try to load a font for better text rendering
                try:
                    from PIL import ImageFont
                    # Use a monospace font if available, fallback to default
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
                        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
                    except (OSError, IOError):
                        font = ImageFont.load_default()
                        font_small = font
                except ImportError:
                    font = None
                    font_small = None
                
                with open(pair.label, "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) != 5:
                            continue
                            
                        class_id, x_center, y_center, width, height = map(float, parts)
                        
                        # Convert YOLO normalized coordinates to pixel coordinates
                        x_center_px = x_center * img_width
                        y_center_px = y_center * img_height
                        w_px = width * img_width
                        h_px = height * img_height
                        
                        x1 = int(x_center_px - w_px / 2)
                        y1 = int(y_center_px - h_px / 2)
                        x2 = int(x_center_px + w_px / 2)
                        y2 = int(y_center_px + h_px / 2)
                        
                        # Color based on class: target_close (0) = green, target_far (1) = red
                        color = (0, 255, 0) if int(class_id) == 0 else (255, 0, 0)
                        
                        # Draw rectangle with thicker lines
                        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
                        
                        # Draw class label
                        class_name = "target_close" if int(class_id) == 0 else "target_far"
                        
                        # Prepare bucket info text
                        bucket_info = pair.bucket_path  # e.g., "1_S/Bot/near" or "0_far"
                        
                        # Position text above bbox (or below if too close to top)
                        text_y = max(2, y1 - 38) if y1 > 40 else y2 + 5
                        
                        # Draw text background for better readability
                        if font:
                            # Measure text size
                            bbox_class = draw.textbbox((0, 0), class_name, font=font)
                            bbox_bucket = draw.textbbox((0, 0), bucket_info, font=font_small)
                            text_width = max(bbox_class[2] - bbox_class[0], bbox_bucket[2] - bbox_bucket[0])
                            text_height = (bbox_class[3] - bbox_class[1]) + (bbox_bucket[3] - bbox_bucket[1]) + 4
                        else:
                            # Estimate text size for default font
                            text_width = max(len(class_name) * 8, len(bucket_info) * 7)
                            text_height = 32
                        
                        # Draw semi-transparent background
                        bg_x1 = x1 - 2
                        bg_y1 = text_y - 2
                        bg_x2 = x1 + text_width + 4
                        bg_y2 = text_y + text_height + 2
                        
                        # Draw black background with some transparency (PIL doesn't support alpha well, so use solid)
                        draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=(0, 0, 0))
                        
                        # Draw class name (larger, colored)
                        draw.text((x1, text_y), class_name, fill=color, font=font)
                        
                        # Draw bucket info below class name (smaller, white)
                        bucket_y = text_y + (18 if font else 16)
                        draw.text((x1, bucket_y), bucket_info, fill=(255, 255, 255), font=font_small)
            
            # Convert PIL Image to QPixmap
            img_rgb = img.convert("RGB")
            data = img_rgb.tobytes("raw", "RGB")
            qimage = QtGui.QImage(
                data, 
                img_width, 
                img_height, 
                img_width * 3, 
                QtGui.QImage.Format_RGB888
            )
            pixmap = QtGui.QPixmap.fromImage(qimage)
            
            # Use zoomable label
            self.image_label.setPixmap(pixmap)
            
            # Update status with label info
            if pair.label:
                with open(pair.label, "r") as f:
                    num_boxes = sum(1 for _ in f)
                self.status_label.setText(
                    f"{pair.image.name} - {num_boxes} Annotation(en) | "
                    f"Scroll zum Zoomen, Drag zum Verschieben"
                )
            else:
                self.status_label.setText(
                    f"{pair.image.name} - Keine Annotation! | "
                    f"Scroll zum Zoomen, Drag zum Verschieben"
                )
                
        except Exception as exc:
            self.image_label.setText(f"Fehler beim Laden: {exc}")
            self.status_label.setText(f"Fehler: {exc}")
            
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        if event.key() == QtCore.Qt.Key_Left:
            self._navigate(-1)
        elif event.key() == QtCore.Qt.Key_Right:
            self._navigate(1)
        elif event.key() == QtCore.Qt.Key_Up:
            self._navigate(-5)
        elif event.key() == QtCore.Qt.Key_Down:
            self._navigate(5)
        else:
            super().keyPressEvent(event)
    
    def _reclassify_current_image(self) -> None:
        """Open dialog to reclassify/move current image to different bucket."""
        if not self.pairs or self.current_index >= len(self.pairs):
            return
        
        current_pair = self.pairs[self.current_index]
        
        # Parse current bucket from path
        try:
            rel_path = current_pair.image.relative_to(self.training_root)
            parts = rel_path.parts
            
            if parts[0] == "0_far":
                current_direction = "0_far"
                current_position = None
                current_distance = None
            elif parts[0] == "negative_samples":
                current_direction = "negative_samples"
                current_position = None
                current_distance = None
            else:
                current_direction = parts[0]
                current_position = parts[1] if len(parts) > 1 else None
                current_distance = parts[2] if len(parts) > 2 else None
        except (ValueError, IndexError):
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                "Konnte aktuellen Bucket nicht ermitteln."
            )
            return
        
        # Create reclassification dialog
        dialog = ReclassifyDialog(current_direction, current_position, current_distance, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_direction, new_position, new_distance = dialog.get_selection()
            
            # Remember current position before move
            remembered_index = self.current_index
            
            # Perform the move
            success = self._move_to_bucket(
                current_pair,
                new_direction,
                new_position,
                new_distance
            )
            
            if success:
                # Reload images to reflect changes
                self._load_images()
                
                # Jump back to the same position (which shows next frame after removal)
                if self.pairs:
                    # Clamp to valid range
                    self.current_index = min(remembered_index, len(self.pairs) - 1)
                    self._update_display()
                
                self.status_label.setText(f"Verschoben nach: {new_direction}/{new_position or ''}/{new_distance or ''}")
    
    def _move_to_bucket(
        self,
        pair: AnnotationPair,
        new_direction: str,
        new_position: Optional[str],
        new_distance: Optional[str]
    ) -> bool:
        """Move image and label to new bucket."""
        try:
            # Determine target directory
            if new_direction == "0_far":
                target_dir = self.training_root / new_direction
            elif new_direction == "negative_samples":
                target_dir = self.training_root / new_direction
            else:
                if not new_position or not new_distance:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Fehler",
                        "Position und Distanz müssen für diese Richtung ausgewählt werden."
                    )
                    return False
                target_dir = self.training_root / new_direction / new_position / new_distance
            
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Check for duplicates
            target_img = target_dir / pair.image.name
            if target_img.exists() and target_img != pair.image:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Duplikat gefunden",
                    "Eine Datei mit diesem Namen existiert bereits im Ziel-Bucket.\n"
                    "Überschreiben?",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
                )
                if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                    return False
                # Delete existing files
                target_img.unlink()
                target_label = target_img.with_suffix(".txt")
                if target_label.exists():
                    target_label.unlink()
            
            # Move image
            import shutil
            shutil.move(str(pair.image), str(target_img))
            
            # Move/update label if it exists
            if pair.label and pair.label.exists():
                target_label = target_img.with_suffix(".txt")
                
                # Update class ID if moving between target_close (0) and target_far (1)
                old_class = 0 if new_direction != "0_far" else 1
                new_class = 1 if new_direction == "0_far" else 0
                
                if old_class != new_class:
                    # Update class ID in label
                    with open(pair.label, 'r') as f:
                        lines = f.readlines()
                    with open(target_label, 'w') as f:
                        for line in lines:
                            parts = line.strip().split()
                            if parts:
                                parts[0] = str(new_class)
                                f.write(" ".join(parts) + "\n")
                    # Delete old label
                    pair.label.unlink()
                else:
                    # Just move the label
                    shutil.move(str(pair.label), str(target_label))
            
            return True
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Fehler",
                f"Fehler beim Verschieben:\n{str(e)}"
            )
            return False


class ReclassifyDialog(QtWidgets.QDialog):
    """Dialog for selecting new bucket classification."""
    
    def __init__(
        self,
        current_direction: str,
        current_position: Optional[str],
        current_distance: Optional[str],
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Neu klassifizieren")
        self.resize(400, 300)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Current classification
        current_text = f"{current_direction}"
        if current_position:
            current_text += f" / {current_position}"
        if current_distance:
            current_text += f" / {current_distance}"
        
        current_label = QtWidgets.QLabel(f"Aktuell: <b>{current_text}</b>")
        layout.addWidget(current_label)
        
        layout.addWidget(QtWidgets.QLabel("<hr>"))
        layout.addWidget(QtWidgets.QLabel("Neue Klassifizierung:"))
        
        # Direction selection
        dir_layout = QtWidgets.QHBoxLayout()
        dir_layout.addWidget(QtWidgets.QLabel("Richtung:"))
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(DIRECTIONS + ["negative_samples"])
        self.direction_combo.setCurrentText(current_direction)
        self.direction_combo.currentTextChanged.connect(self._on_direction_changed)
        dir_layout.addWidget(self.direction_combo)
        layout.addLayout(dir_layout)
        
        # Position selection
        pos_layout = QtWidgets.QHBoxLayout()
        pos_layout.addWidget(QtWidgets.QLabel("Position:"))
        self.position_combo = QtWidgets.QComboBox()
        self.position_combo.addItems(POSITIONS)
        if current_position and current_position in POSITIONS:
            self.position_combo.setCurrentText(current_position)
        pos_layout.addWidget(self.position_combo)
        layout.addLayout(pos_layout)
        
        # Distance selection
        dist_layout = QtWidgets.QHBoxLayout()
        dist_layout.addWidget(QtWidgets.QLabel("Distanz:"))
        self.distance_combo = QtWidgets.QComboBox()
        self.distance_combo.addItems(DISTANCES)
        if current_distance and current_distance in DISTANCES:
            self.distance_combo.setCurrentText(current_distance)
        dist_layout.addWidget(self.distance_combo)
        layout.addLayout(dist_layout)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("Verschieben")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QtWidgets.QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)
        
        # Initial UI state
        self._on_direction_changed()
    
    def _on_direction_changed(self) -> None:
        """Enable/disable position/distance based on direction."""
        direction = self.direction_combo.currentText()
        needs_position = direction not in ["0_far", "negative_samples"]
        self.position_combo.setEnabled(needs_position)
        self.distance_combo.setEnabled(needs_position)
    
    def get_selection(self) -> Tuple[str, Optional[str], Optional[str]]:
        """Get selected classification."""
        direction = self.direction_combo.currentText()
        if direction in ["0_far", "negative_samples"]:
            return direction, None, None
        return direction, self.position_combo.currentText(), self.distance_combo.currentText()


def main() -> None:
    """Entry point for the annotation checker."""
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Dark theme
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(25, 25, 25))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(42, 130, 218))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
    palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
    app.setPalette(palette)
    
    window = CheckerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
