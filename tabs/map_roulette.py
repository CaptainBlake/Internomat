import math
import random

from PySide6.QtCore import Qt, QTimer, QSize, QPoint
from PySide6.QtGui import QColor, QPainter, QBrush
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
    QSizePolicy,
    QGraphicsOpacityEffect,
    QGraphicsBlurEffect,
)

import db
import core


class MapListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._item_height = 48

        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setWrapping(False)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(16)
        self.setUniformItemSizes(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_grid()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_grid()

    def _update_grid(self):
        viewport_width = max(120, self.viewport().width())
        available_width = max(120, viewport_width - 8)

        self.setGridSize(QSize(available_width, self._item_height))

        for i in range(self.count()):
            item = self.item(i)
            item.setSizeHint(QSize(available_width, self._item_height))

    def addItem(self, item):
        super().addItem(item)
        self._update_grid()


class FireworksWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._particles = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_particles)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.hide()

    def burst(self):
        colors = [
            QColor("#FF5252"),
            QColor("#FFB300"),
            QColor("#69F0AE"),
            QColor("#40C4FF"),
            QColor("#EA80FC"),
            QColor("#FFD54F"),
            QColor("#FFFFFF"),
        ]

        w = max(1, self.width())
        h = max(1, self.height())
        cx = w / 2
        cy = h / 2

        self._particles = []

        # Big central explosion
        for _ in range(70):
            angle = random.uniform(0, 6.283185307179586)
            speed = random.uniform(2.5, 10.5)
            self._particles.append({
                "x": cx + random.uniform(-16, 16),
                "y": cy + random.uniform(-16, 16),
                "vx": math.cos(angle) * speed + random.uniform(-1.5, 1.5),
                "vy": math.sin(angle) * speed + random.uniform(-1.5, 1.5),
                "life": random.randint(40, 90),
                "color": random.choice(colors),
                "size": random.randint(4, 11),
            })

        # Outer sparks / rockets
        for _ in range(28):
            angle = random.uniform(0, 6.283185307179586)
            speed = random.uniform(4.5, 13.0)
            self._particles.append({
                "x": cx + random.uniform(-30, 30),
                "y": cy + random.uniform(-30, 30),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": random.randint(28, 65),
                "color": random.choice(colors),
                "size": random.randint(2, 7),
            })

        # Side bursts
        for side in (-1, 1):
            for _ in range(18):
                angle = random.uniform(-0.9, 0.9)
                speed = random.uniform(3.5, 9.5)
                self._particles.append({
                    "x": cx + (side * random.uniform(30, 80)),
                    "y": cy + random.uniform(-20, 20),
                    "vx": side * abs(math.cos(angle) * speed),
                    "vy": math.sin(angle) * speed,
                    "life": random.randint(30, 75),
                    "color": random.choice(colors),
                    "size": random.randint(3, 9),
                })

        if not self._timer.isActive():
            self._timer.start(25)
        self.show()
        self.raise_()
        self.update()

    def _update_particles(self):
        if not self._particles:
            self._timer.stop()
            self.hide()
            return

        next_particles = []
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.20
            p["life"] -= 1
            if p["life"] > 0:
                next_particles.append(p)

        self._particles = next_particles
        self.update()

    def paintEvent(self, event):
        if not self._particles:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for p in self._particles:
            life_ratio = p["life"] / 90
            alpha = max(0, min(255, int(255 * life_ratio)))
            color = QColor(p["color"])
            color.setAlpha(alpha)

            painter.setPen(Qt.PenStyle.NoPen)

            x = int(p["x"])
            y = int(p["y"])
            size = int(p["size"] * (0.75 + (life_ratio * 0.9)))

            glow = QColor(color)
            glow.setAlpha(max(0, alpha // 3))
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPoint(x, y), size + 6, size + 6)

            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPoint(x, y), size, size)


class SlotMachineWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid #BBDEFB;
                border-radius: 18px;
            }
        """)

        self._items = []
        self._running = False
        self._sequence = []
        self._step = 0
        self._display_count = 7
        self._winner = None
        self._pulse_active = False
        self._pulse_phase = 0.0
        self._on_finished = None

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(4)

        self.hint = QLabel("Ready")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
                color: #607D8B;
                font-size: 12px;
                font-weight: 600;
            }
        """)
        layout.addWidget(self.hint)

        self.track = QFrame()
        self.track.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        track_layout = QVBoxLayout(self.track)
        track_layout.setContentsMargins(6, 6, 6, 6)
        track_layout.setSpacing(0)

        self.rows = []
        for _ in range(self._display_count):
            row = QLabel("—")
            row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.setMinimumHeight(20)
            row.setStyleSheet("""
                QLabel {
                    background: transparent;
                    border: none;
                    padding: 0px 4px;
                    font-size: 17px;
                    font-weight: 600;
                    color: #607D8B;
                }
            """)

            opacity = QGraphicsOpacityEffect(row)
            row.setGraphicsEffect(opacity)

            blur = QGraphicsBlurEffect(row)
            row._blur_effect = blur

            self.rows.append(row)
            track_layout.addWidget(row)

        self.center_row = self.rows[3]
        layout.addWidget(self.track, 1)

        self.fireworks = FireworksWidget(self.track)
        self.fireworks.hide()

        self._apply_visuals(idle=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fireworks.setGeometry(self.track.rect())

    def set_items(self, items):
        self._items = [item.replace("de_", "") for item in items]
        self._fill_idle_state()

    def _update_pulse(self):
        if not self._pulse_active:
            self._pulse_timer.stop()
            return

        self._pulse_phase += 0.16
        self._apply_visuals(idle=False, winner=self._winner, center_glow=True)
        self.update()

    def _apply_visuals(self, idle=False, winner=None, center_glow=False):
        for idx, row in enumerate(self.rows):
            distance = abs(idx - 3)

            eff = row.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                if idx == 3:
                    eff.setOpacity(1.0)
                else:
                    eff.setOpacity(max(0.40, 0.90 - (distance * 0.15)))

            blur = getattr(row, "_blur_effect", None)
            if blur is not None:
                if idx == 3:
                    blur.setBlurRadius(0.0)
                else:
                    blur.setBlurRadius(0.85 + (distance * 0.95))

            if idx == 3:
                if center_glow:
                    row.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            border: none;
                            padding: 1px 4px;
                            font-size: 30px;
                            font-weight: 900;
                            color: #0D47A1;
                        }
                    """)
                else:
                    row.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            border: none;
                            padding: 0px 4px;
                            font-size: 27px;
                            font-weight: 800;
                            color: #0D47A1;
                        }
                    """)
            else:
                font_size = max(12, 17 - distance)
                row.setStyleSheet(f"""
                    QLabel {{
                        background: transparent;
                        border: none;
                        padding: 0px 4px;
                        font-size: {font_size}px;
                        font-weight: 600;
                        color: #607D8B;
                    }}
                """)

        if winner is not None:
            self.center_row.setStyleSheet("""
                QLabel {
                    background: transparent;
                    border: none;
                    padding: 1px 4px;
                    font-size: 30px;
                    font-weight: 900;
                    color: #0D47A1;
                }
            """)

    def _fill_idle_state(self):
        if not self._items:
            for row in self.rows:
                row.setText("—")
            self._apply_visuals(idle=True)
            return

        padded = self._items[:]
        while len(padded) < self._display_count:
            padded.extend(self._items)
        padded = padded[:self._display_count]

        for row, text in zip(self.rows, padded):
            row.setText(text)

        self._apply_visuals(idle=True)

    def start_spin(self, winner, on_finished):
        if self._running or not self._items:
            return

        self._running = True
        self._step = 0
        self._winner = winner.replace("de_", "")
        self.hint.setText("Spinning...")
        self.fireworks.hide()

        winner_text = self._winner
        winner_index = self._items.index(winner_text)

        prefix = [random.choice(self._items) for _ in range(random.randint(28, 42))]
        tail = [
            self._items[(winner_index - 3) % len(self._items)],
            self._items[(winner_index - 2) % len(self._items)],
            self._items[(winner_index - 1) % len(self._items)],
            winner_text,
            self._items[(winner_index + 1) % len(self._items)],
            self._items[(winner_index + 2) % len(self._items)],
            self._items[(winner_index + 3) % len(self._items)],
        ]
        self._sequence = prefix + tail

        def render_window(center_index):
            indexes = [
                max(0, center_index - 3),
                max(0, center_index - 2),
                max(0, center_index - 1),
                center_index,
                min(len(self._sequence) - 1, center_index + 1),
                min(len(self._sequence) - 1, center_index + 2),
                min(len(self._sequence) - 1, center_index + 3),
            ]

            for row_idx, seq_idx in enumerate(indexes):
                self.rows[row_idx].setText(self._sequence[seq_idx])

            self._apply_visuals(idle=False)

        def tick():
            if self._step < len(self._sequence):
                render_window(self._step)
                self._step += 1

                remaining = len(self._sequence) - self._step
                if remaining <= 10:
                    delay = 70 + remaining * 34
                elif remaining <= 18:
                    delay = 46
                else:
                    delay = 38

                QTimer.singleShot(delay, tick)
                return

            self.rows[0].setText(self._items[(winner_index - 3) % len(self._items)])
            self.rows[1].setText(self._items[(winner_index - 2) % len(self._items)])
            self.rows[2].setText(self._items[(winner_index - 1) % len(self._items)])
            self.rows[3].setText(winner_text)
            self.rows[4].setText(self._items[(winner_index + 1) % len(self._items)])
            self.rows[5].setText(self._items[(winner_index + 2) % len(self._items)])
            self.rows[6].setText(self._items[(winner_index + 3) % len(self._items)])

            self._pulse_active = True
            self._pulse_timer.start(55)
            QTimer.singleShot(1200, self._stop_pulse_and_finish)

        tick()

    def _stop_pulse_and_finish(self):
        self._pulse_active = False
        self._pulse_timer.stop()
        self._apply_visuals(idle=False, winner=self._winner, center_glow=True)
        self.hint.setText("Winner!")
        self.fireworks.burst()
        self._running = False
        self.update()


def build_map_tab(parent):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(10)

    title = QLabel("Map Roulette")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: 700; color: #21443C;")
    layout.addWidget(title)

    content = QHBoxLayout()
    content.setSpacing(10)

    left_panel = QVBoxLayout()
    left_panel.setSpacing(6)

    list_frame = QFrame()
    list_frame.setStyleSheet("""
        QFrame {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid #C9ECE2;
            border-radius: 14px;
        }
    """)
    list_layout = QVBoxLayout(list_frame)
    list_layout.setContentsMargins(10, 10, 10, 10)
    list_layout.setSpacing(4)

    map_list = MapListWidget()
    map_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    map_list.setStyleSheet("""
        QListWidget {
            background: transparent;
            border: none;
            padding: 0px;
        }
        QListWidget::item {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 #FFFFFF, stop:1 #F7FFFC);
            border: 1px solid #D7EEE7;
            border-radius: 12px;
            padding: 7px 10px;
            color: #21443C;
            margin: 1px;
            margin-bottom: 8px;
        }
        QListWidget::item:hover {
            background: #ECFBF6;
            border: 1px solid #BEE8D9;
        }
        QListWidget::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 #D7F5EC, stop:1 #C7F0E4);
            color: #0C755B;
            border: 1px solid #9EDCCB;
        }
    """)
    list_layout.addWidget(map_list, 1)

    left_panel.addWidget(list_frame, 0)

    controls = QHBoxLayout()
    controls.setSpacing(8)

    entry = QLineEdit()
    entry.setPlaceholderText("Add map name")
    controls.addWidget(entry, 1)

    add_button = QPushButton("Add")
    remove_button = QPushButton("Remove")
    spin_button = QPushButton("Spin")

    controls.addWidget(add_button)
    controls.addWidget(remove_button)
    controls.addWidget(spin_button)
    left_panel.addLayout(controls)

    result_label = QLabel("Selected Map: -")
    result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    result_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #21443C;")
    left_panel.addWidget(result_label)

    right_panel = QVBoxLayout()
    right_panel.setSpacing(6)

    spin_machine = SlotMachineWidget()
    right_panel.addWidget(spin_machine, 1)

    content.addLayout(left_panel, 0)
    content.addLayout(right_panel, 1)
    layout.addLayout(content)

    spinning = False

    def refresh_maps():
        map_list.clear()
        maps = db.get_maps()
        for m in maps:
            item = QListWidgetItem(m.replace("de_", ""))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            map_list.addItem(item)
        map_list._update_grid()
        spin_machine.set_items(maps)

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

    def finish_spin(winner):
        nonlocal spinning
        result_label.setText(f"Selected Map: {winner}")
        spinning = False

    def spin():
        nonlocal spinning

        maps = db.get_maps()
        if not maps:
            QMessageBox.critical(parent, "Error", "No maps available")
            return
        if spinning:
            return

        spinning = True
        result_label.setText("Spinning...")

        winner = core.choose_random_map(maps)
        spin_machine.set_items(maps)
        spin_machine.start_spin(winner, lambda: finish_spin(winner))

    add_button.clicked.connect(add_map)
    remove_button.clicked.connect(remove_map)
    spin_button.clicked.connect(spin)

    refresh_maps()