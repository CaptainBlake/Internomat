import math
import random

from PySide6.QtCore import Qt, QEasingCurve, Property, QPointF, QPropertyAnimation
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFrame,
)

import db
import core


class WheelWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rotation = 0.0
        self.highlight_index = None
        self.animation = None
        self.setMinimumSize(520, 520)
        self.spin_callback = None

    def getRotation(self):
        return self._rotation

    def setRotation(self, value):
        self._rotation = float(value) % 360.0
        self.update()

    rotation = Property(float, getRotation, setRotation)

    def mousePressEvent(self, event):
        if self.spin_callback is None:
            return

        rect = self.rect().adjusted(24, 24, -24, -24)
        size = min(rect.width(), rect.height())
        cx = rect.center().x()
        cy = rect.center().y()

        center_radius = 42
        dx = event.position().x() - cx
        dy = event.position().y() - cy
        distance = math.hypot(dx, dy)

        if distance <= center_radius:
            self.spin_callback()

    def color_for_index(self, i):
        palette = [
            "#1E88E5", "#E53935", "#43A047", "#8E24AA",
            "#FB8C00", "#00ACC1", "#6D4C41", "#546E7A",
            "#D81B60", "#5E35B1",
        ]
        return QColor(palette[i % len(palette)])

    def paintEvent(self, event):
        maps = db.get_maps()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        painter.fillRect(self.rect(), self.palette().window())

        rect = self.rect().adjusted(24, 24, -24, -24)
        size = min(rect.width(), rect.height())
        cx = rect.center().x()
        cy = rect.center().y()
        radius = int(size * 0.42)

        if not maps:
            painter.setBrush(QColor("#CFD8DC"))
            painter.setPen(QPen(QColor("#B0BEC5"), 3))
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

            font = QFont("Segoe UI", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#455A64"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No maps available")
            return

        angle_per_item = 360.0 / len(maps)
        start_angle = self._rotation

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#B0BEC5"), 3))
        painter.drawEllipse(cx - radius - 6, cy - radius - 6, radius * 2 + 12, radius * 2 + 12)

        font = QFont("Segoe UI", 11)
        font.setBold(True)
        painter.setFont(font)

        for i, map_name in enumerate(maps):
            fill = self.color_for_index(i).lighter(115)
            if self.highlight_index is not None and i == self.highlight_index:
                fill = QColor("#FFD54F")

            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawPie(
                cx - radius, cy - radius, radius * 2, radius * 2,
                int((-start_angle) * 16), int((-angle_per_item) * 16)
            )

            mid_angle_deg = start_angle + angle_per_item / 2.0
            mid_angle_rad = math.radians(mid_angle_deg)
            text_radius = radius * 0.66

            tx = cx + math.cos(mid_angle_rad) * text_radius
            ty = cy + math.sin(mid_angle_rad) * text_radius

            label = map_name.replace("de_", "")
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(int(tx - 80), int(ty - 10), 160, 20, Qt.AlignmentFlag.AlignCenter, label)

            start_angle += angle_per_item

        center_radius = 42
        painter.setBrush(QColor("#CFD8DC"))
        painter.setPen(QPen(QColor("#B0BEC5"), 2))
        painter.drawEllipse(cx - center_radius, cy - center_radius, center_radius * 2, center_radius * 2)

        font = QFont("Segoe UI", 11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#455A64"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "SPIN")

        painter.setBrush(QColor("#263238"))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(cx, cy - radius - 8)
        path.lineTo(cx - 12, cy - radius - 32)
        path.lineTo(cx + 12, cy - radius - 32)
        path.closeSubpath()
        painter.drawPath(path)

        if self.highlight_index is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#FFD54F"), 4))
            painter.drawEllipse(cx - radius - 12, cy - radius - 12, radius * 2 + 24, radius * 2 + 24)


def build_map_tab(parent):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    title = QLabel("Map Roulette")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: 700;")
    layout.addWidget(title)

    wheel = WheelWidget()
    layout.addWidget(wheel, 2, alignment=Qt.AlignmentFlag.AlignHCenter)

    result_label = QLabel("Selected Map: -")
    result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    result_label.setStyleSheet("font-size: 12px; font-weight: 700;")
    layout.addWidget(result_label)

    controls = QHBoxLayout()
    controls.setSpacing(10)

    entry = QLineEdit()
    entry.setPlaceholderText("Add map name")
    controls.addWidget(entry, 1)

    add_button = QPushButton("Add")
    remove_button = QPushButton("Remove")
    spin_button = QPushButton("Spin")

    controls.addWidget(add_button)
    controls.addWidget(remove_button)
    controls.addWidget(spin_button)
    layout.addLayout(controls)

    list_frame = QFrame()
    list_frame.setStyleSheet("""
        QFrame {
            background: #ECEFF1;
            border-radius: 12px;
        }
    """)
    list_layout = QVBoxLayout(list_frame)
    list_layout.setContentsMargins(12, 12, 12, 12)

    map_list = QListWidget()
    map_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    list_layout.addWidget(map_list)
    layout.addWidget(list_frame, 1)

    current_rotation = 0.0
    spinning = False

    def refresh_maps():
        map_list.clear()
        for m in db.get_maps():
            map_list.addItem(QListWidgetItem(m))
        wheel.update()

    def add_map():
        name = entry.text().strip()
        if not name:
            return
        db.add_map(name)
        entry.clear()
        refresh_maps()

    def remove_map():
        items = map_list.selectedItems()
        if not items:
            return
        for item in items:
            db.delete_map(item.text())
        refresh_maps()

    def spin():
        nonlocal current_rotation, spinning

        maps = db.get_maps()
        if not maps:
            QMessageBox.critical(parent, "Error", "No maps available")
            return
        if spinning:
            return

        spinning = True
        wheel.highlight_index = None

        winner = core.choose_random_map(maps)
        winner_index = maps.index(winner)

        angle_per_item = 360.0 / len(maps)

        # Center angle of the winning slice in the wheel's coordinate system
        winner_center_angle = winner_index * angle_per_item + angle_per_item / 2.0

        # Pointer is at the top of the wheel (270° in this coordinate system)
        pointer_angle = 270.0

        # We need to rotate the wheel so the winner center ends up under the pointer
        normalized_current = current_rotation % 360.0
        target_rotation = (pointer_angle - winner_center_angle - normalized_current) % 360.0

        # Add a few full turns for the animation
        extra_turns = random.randint(6, 9) * 360.0
        final_rotation = current_rotation + extra_turns + target_rotation

        wheel.animation = QPropertyAnimation(wheel, b"rotation", parent)
        wheel.animation.setDuration(7000)
        wheel.animation.setStartValue(current_rotation)
        wheel.animation.setEndValue(final_rotation)
        wheel.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finished():
            nonlocal current_rotation, spinning
            current_rotation = final_rotation % 360.0
            wheel.highlight_index = winner_index
            wheel.rotation = current_rotation
            wheel.update()
            result_label.setText(f"Selected Map: {winner}")
            spinning = False

        wheel.animation.finished.connect(finished)
        result_label.setText("Spinning...")
        wheel.animation.start()

    add_button.clicked.connect(add_map)
    remove_button.clicked.connect(remove_map)
    spin_button.clicked.connect(spin)

    refresh_maps()