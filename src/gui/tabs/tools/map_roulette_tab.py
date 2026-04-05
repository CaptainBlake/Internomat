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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFrame,
    QSizePolicy,
    QGraphicsOpacityEffect,
    QGraphicsBlurEffect,
)

import core.maps.service as maps_service
from core.maps.service import choose_map
from core.settings.settings import settings

# TODO: add map display for map in database & a seperate display for map pool from which to gamble from

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
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #131A23,
                    stop: 0.5 #1A2230,
                    stop: 1 #10151C
                );
                border: 1px solid rgba(63, 136, 217, 0.28);
                border-radius: 22px;
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

        self.setMinimumHeight(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.hint = QLabel("Ready")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
                color: #C8B57A;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }
        """)
        layout.addWidget(self.hint)

        self.track = QFrame()
        self.track.setStyleSheet("""
            QFrame {
                background: rgba(15, 20, 28, 0.78);
                border: 1px solid rgba(63, 136, 217, 0.22);
                border-radius: 18px;
            }
        """)
        track_layout = QVBoxLayout(self.track)
        track_layout.setContentsMargins(10, 10, 10, 10)
        track_layout.setSpacing(2)

        self.rows = []
        for _ in range(self._display_count):
            row = QLabel("—")
            row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.setMinimumHeight(20)
            row.setStyleSheet("""
                QLabel {
                    background: transparent;
                    border: none;
                    padding: 2px 6px;
                    font-size: 16px;
                    font-weight: 600;
                    color: #9AA4B2;
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

        self._pulse_phase += 0.18
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
                    eff.setOpacity(max(0.25, 0.82 - (distance * 0.17)))

            blur = getattr(row, "_blur_effect", None)
            if blur is not None:
                if idx == 3:
                    blur.setBlurRadius(0.0)
                else:
                    blur.setBlurRadius(1.0 + (distance * 1.4))

            if idx == 3:
                if center_glow:
                    row.setStyleSheet("""
                        QLabel {
                            background: rgba(63, 136, 217, 0.16);
                            border: 1px solid rgba(63, 136, 217, 0.34);
                            border-radius: 10px;
                            padding: 4px 6px;
                            font-size: 30px;
                            font-weight: 900;
                            color: #DCEAF7;
                        }
                    """)
                else:
                    row.setStyleSheet("""
                        QLabel {
                            background: rgba(63, 136, 217, 0.08);
                            border: 1px solid rgba(63, 136, 217, 0.22);
                            border-radius: 10px;
                            padding: 4px 6px;
                            font-size: 28px;
                            font-weight: 900;
                            color: #AFC8E8;
                        }
                    """)
            else:
                font_size = max(11, 16 - distance)
                alpha = max(0.38, 0.88 - (distance * 0.16))
                row.setStyleSheet(f"""
                    QLabel {{
                        background: transparent;
                        border: none;
                        padding: 2px 6px;
                        font-size: {font_size}px;
                        font-weight: 600;
                        color: rgba(185, 198, 212, {alpha});
                    }}
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

        self._on_finished = on_finished

        self._running = True
        self._step = 0
        self._winner = winner.replace("de_", "")
        self.hint.setText("Spinning...")
        self.fireworks.hide()

        winner_text = self._winner
        winner_index = self._items.index(winner_text)

        prefix = [random.choice(self._items) for _ in range(random.randint(34, 48))]
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

                # Sanftes, gleichmäßiges Ausbremsen über einen längeren Zeitraum
                slow_down_steps = 40
                max_delay = 180
                min_delay = 34

                if remaining <= slow_down_steps:
                    progress = (slow_down_steps - remaining) / slow_down_steps
                    delay = int(min_delay + (max_delay - min_delay) * progress)
                else:
                    delay = min_delay

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
            QTimer.singleShot(1250, self._stop_pulse_and_finish)

        tick()

    def _stop_pulse_and_finish(self):
        self._pulse_active = False
        self._pulse_timer.stop()
        self._apply_visuals(idle=False, winner=self._winner, center_glow=True)
        self.hint.setText("Winner!")
        self.fireworks.burst()
        self._running = False
        if self._on_finished:
            self._on_finished()
        self.update()


def _apply_pool_table_style(table):
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().hide()
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

    table.setStyleSheet("""
        QTableWidget {
            background: transparent;
            border: none;
            outline: none;
            alternate-background-color: #F8FCFA;
            color: #20443D;
        }
        QTableWidget:focus {
            border: none;
            outline: none;
        }
        QTableWidget::item {
            padding: 6px;
            border: none;
            outline: none;
        }
        QTableWidget::item:selected {
            background: #DFF7EF;
            color: #4A7168;
            border: none;
            outline: none;
        }
        QTableWidget::item:focus {
            border: none;
            outline: none;
        }
        QAbstractItemView {
            outline: none;
        }
        QAbstractItemView::item {
            border: none;
            outline: none;
        }
        QAbstractItemView::item:selected {
            border: none;
            outline: none;
        }
    """)


def _build_pool_card(title_text, table):
    card = QFrame()
    card.setStyleSheet("""
        QFrame {
            background: rgba(255, 255, 255, 0.94);
            border: none;
            border-radius: 16px;
        }
    """)

    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(0, 0, 0, 0)
    card_layout.setSpacing(0)

    title = QLabel(title_text)
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("""
        QLabel {
            background: #EAF8F3;
            color: #4A7168;
            padding: 8px 12px;
            font-size: 13px;
            font-weight: 800;
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
        }
    """)

    card_layout.addWidget(title)
    card_layout.addWidget(table, 1)
    return card


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

    available_map_table = QTableWidget(0, 1)
    available_map_table.setHorizontalHeaderLabels(["Map"])
    _apply_pool_table_style(available_map_table)
    available_map_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    selected_map_table = QTableWidget(0, 2)
    selected_map_table.setHorizontalHeaderLabels(["#", "Map"])
    _apply_pool_table_style(selected_map_table)
    selected_map_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    selected_map_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    lists_row = QHBoxLayout()
    lists_row.setSpacing(10)

    button_col = QVBoxLayout()
    button_col.setSpacing(8)
    button_col.addStretch(1)

    add_to_pool_button = QPushButton(">")
    remove_from_pool_button = QPushButton("<")
    add_to_pool_button.setFixedWidth(40)
    remove_from_pool_button.setFixedWidth(40)

    button_col.addWidget(add_to_pool_button, alignment=Qt.AlignmentFlag.AlignHCenter)
    button_col.addWidget(remove_from_pool_button, alignment=Qt.AlignmentFlag.AlignHCenter)
    button_col.addStretch(1)

    lists_row.addWidget(_build_pool_card("Map Pool", available_map_table), 1)
    lists_row.addLayout(button_col)
    lists_row.addWidget(_build_pool_card("Selected Maps", selected_map_table), 1)
    left_panel.addLayout(lists_row, 1)

    db_controls = QHBoxLayout()
    db_controls.setSpacing(8)

    entry = QLineEdit()
    entry.setPlaceholderText("Add map name")
    db_controls.addWidget(entry, 1)

    add_button = QPushButton("Add")
    remove_button = QPushButton("Remove")
    db_controls.addWidget(add_button)
    db_controls.addWidget(remove_button)
    left_panel.addLayout(db_controls)

    spin_controls = QHBoxLayout()
    spin_controls.setSpacing(8)

    clear_pool_button = QPushButton("Clear Pool")
    spin_button = QPushButton("Spin")

    spin_controls.addWidget(clear_pool_button)
    spin_controls.addWidget(spin_button)
    left_panel.addLayout(spin_controls)

    result_label = QLabel("Selected Map: -")
    result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    result_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #1E2B38;")
    left_panel.addWidget(result_label)

    right_panel = QVBoxLayout()
    right_panel.setSpacing(6)
    spin_machine = SlotMachineWidget()
    right_panel.addWidget(spin_machine, 1)

    content.addLayout(left_panel, 0)
    content.addLayout(right_panel, 1)
    layout.addLayout(content)

    spinning = False

    def _selected_rows(table, reverse=False):
        rows = sorted({idx.row() for idx in table.selectedIndexes()})
        return list(reversed(rows)) if reverse else rows

    def _contains_selected_map(raw_name):
        for row in range(selected_map_table.rowCount()):
            item = selected_map_table.item(row, 1)
            if item is None:
                continue
            if str(item.data(Qt.ItemDataRole.UserRole)) == str(raw_name):
                return True
        return False

    def _refresh_selected_index_labels():
        for row in range(selected_map_table.rowCount()):
            index_item = QTableWidgetItem(str(row + 1))
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            selected_map_table.setItem(row, 0, index_item)

    def _append_selected_map(raw_name):
        if _contains_selected_map(raw_name):
            return

        row = selected_map_table.rowCount()
        selected_map_table.insertRow(row)

        map_item = QTableWidgetItem(str(raw_name).replace("de_", ""))
        map_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        map_item.setData(Qt.ItemDataRole.UserRole, raw_name)
        selected_map_table.setItem(row, 1, map_item)

        _refresh_selected_index_labels()

    def _selected_pool_maps():
        maps = []
        for row in range(selected_map_table.rowCount()):
            item = selected_map_table.item(row, 1)
            if item is not None:
                maps.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return maps

    def _sync_slot_machine_items():
        spin_machine.set_items(_selected_pool_maps())

    def refresh_available_maps():
        available_map_table.setRowCount(0)
        maps = maps_service.get_maps()
        map_set = set(maps)

        for raw_name in maps:
            row = available_map_table.rowCount()
            available_map_table.insertRow(row)
            item = QTableWidgetItem(raw_name.replace("de_", ""))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, raw_name)
            available_map_table.setItem(row, 0, item)

        selected_raw = _selected_pool_maps()
        selected_map_table.setRowCount(0)
        for raw_name in selected_raw:
            if raw_name in map_set:
                _append_selected_map(raw_name)

        _sync_slot_machine_items()

    def add_map():
        name = entry.text().strip()
        if not name:
            return

        if not name.startswith("de_"):
            name = f"de_{name}"

        maps_service.add_map(name)
        entry.clear()
        refresh_available_maps()

    def remove_map():
        rows = _selected_rows(available_map_table, reverse=True)
        if not rows:
            return

        for row in rows:
            item = available_map_table.item(row, 0)
            if item is None:
                continue
            maps_service.delete_map(str(item.data(Qt.ItemDataRole.UserRole)))

        refresh_available_maps()

    def add_to_pool():
        rows = _selected_rows(available_map_table)
        if not rows:
            return

        for row in rows:
            item = available_map_table.item(row, 0)
            if item is None:
                continue
            _append_selected_map(str(item.data(Qt.ItemDataRole.UserRole)))

        _sync_slot_machine_items()

    def remove_from_pool():
        rows = _selected_rows(selected_map_table, reverse=True)
        if not rows:
            return

        for row in rows:
            selected_map_table.removeRow(row)

        _refresh_selected_index_labels()
        _sync_slot_machine_items()

    def clear_pool():
        selected_map_table.setRowCount(0)
        _sync_slot_machine_items()

    def on_available_map_double_clicked(index):
        """Handle double-click on available map pool to add map."""
        row = index.row()
        item = available_map_table.item(row, 0)
        if item is None:
            return
        _append_selected_map(str(item.data(Qt.ItemDataRole.UserRole)))
        _sync_slot_machine_items()

    def finish_spin(winner):
        nonlocal spinning
        result_label.setText(f"Selected Map: {winner}")
        spinning = False

    def spin():
        nonlocal spinning

        maps = _selected_pool_maps()
        if not maps:
            QMessageBox.critical(parent, "Error", "No maps selected for roulette")
            return
        if spinning:
            return

        spinning = True
        result_label.setText("Spinning...")

        winner = choose_map(maps, use_history=settings.maproulette_use_history)
        spin_machine.set_items(maps)
        spin_machine.start_spin(winner, lambda: finish_spin(winner))

    add_button.clicked.connect(add_map)
    remove_button.clicked.connect(remove_map)
    add_to_pool_button.clicked.connect(add_to_pool)
    remove_from_pool_button.clicked.connect(remove_from_pool)
    clear_pool_button.clicked.connect(clear_pool)
    available_map_table.doubleClicked.connect(on_available_map_double_clicked)
    spin_button.clicked.connect(spin)

    refresh_available_maps()
    return refresh_available_maps