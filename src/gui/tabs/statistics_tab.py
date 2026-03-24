from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

import core.stats.statistics as statistics
from services import executor
import services.logger as logger


class StatisticsDispatcher(QObject):
    loaded = Signal(object, object, object)
    failed = Signal(object, object)


def _fmt_optional(value):
    return "n/a" if value is None else str(value)


def _build_metric_card(title, value):
    frame = QFrame()
    frame.setStyleSheet(
        """
        QFrame {
            background: rgba(255, 255, 255, 0.94);
            border: none;
            border-radius: 16px;
        }
        """
    )

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #5A6B7C;")

    value_label = QLabel(value)
    value_label.setStyleSheet("font-size: 24px; font-weight: 900; color: #22384D;")

    layout.addWidget(title_label)
    layout.addWidget(value_label)

    return frame


def _build_recent_maps_table(rows):
    frame = QFrame()
    frame.setStyleSheet(
        """
        QFrame {
            background: rgba(255, 255, 255, 0.94);
            border: none;
            border-radius: 16px;
        }
        """
    )

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QLabel("Recent Maps (DB + Cache)")
    title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    title.setStyleSheet("font-size: 15px; font-weight: 800; color: #22384D;")
    layout.addWidget(title)

    table = QTableWidget(0, 9)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)

    headers = ["Match", "Map", "Winner", "Score", "Demo Flag", "Cached", "Rounds", "Kills", "At"]
    for i, text in enumerate(headers):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setHorizontalHeaderItem(i, item)

    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

    for row in rows:
        idx = table.rowCount()
        table.insertRow(idx)

        values = [
            row["match_id"],
            row["map_name"],
            row["winner"],
            f"{row['team1_score']}:{row['team2_score']}",
            "yes" if row["db_demo_flag"] else "no",
            "yes" if row["cached_demo"] else "no",
            _fmt_optional(row["demo_rounds"]),
            _fmt_optional(row["demo_kills"]),
            row["played_at"],
        ]

        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(idx, col, item)

    layout.addWidget(table, 1)
    return frame


def _clear_dynamic_content(layout):
    while layout.count() > 2:
        item = layout.takeAt(2)
        if item is None:
            continue

        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            while child_layout.count():
                child_item = child_layout.takeAt(0)
                child_widget = child_item.widget()
                if child_widget is not None:
                    child_widget.setParent(None)
                    child_widget.deleteLater()


def _render_statistics_content(parent, overview, recent_rows):
    layout = parent.layout()
    if layout is None:
        return

    _clear_dynamic_content(layout)

    metrics = QHBoxLayout()
    metrics.setSpacing(12)
    metrics.addWidget(_build_metric_card("Total Matches", str(overview["total_matches"])))
    metrics.addWidget(_build_metric_card("Total Maps", str(overview["total_maps"])))
    metrics.addWidget(_build_metric_card("Cached Maps", str(overview["cached_maps"])))
    metrics.addWidget(_build_metric_card("DB-only Maps", str(overview["db_only_maps"])))
    metrics.addWidget(_build_metric_card("Cache Coverage", f"{overview['cache_map_coverage']:.1f}%"))
    metrics.addWidget(_build_metric_card("Unique Players", str(overview["unique_players"])))

    layout.addLayout(metrics)
    layout.addWidget(_build_recent_maps_table(recent_rows), 1)


def _show_loading_state(parent, message):
    layout = parent.layout()
    if layout is None:
        return

    _clear_dynamic_content(layout)

    loading = QLabel(message)
    loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
    loading.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 14px;")
    layout.addWidget(loading, 1)


def _ensure_dispatcher(parent):
    if hasattr(parent, "_statistics_dispatcher"):
        return parent._statistics_dispatcher

    dispatcher = StatisticsDispatcher(parent)

    def on_loaded(request_id, overview, recent_rows):
        if request_id != getattr(parent, "_statistics_request_id", None):
            return

        parent._statistics_loading = False
        _render_statistics_content(parent, overview, recent_rows)

    def on_failed(request_id, error):
        if request_id != getattr(parent, "_statistics_request_id", None):
            return

        parent._statistics_loading = False
        logger.log_error(f"[UI] Statistics refresh failed: {error}", exc=error)
        _show_loading_state(parent, "Failed to load statistics. Check logs for details.")

    dispatcher.loaded.connect(on_loaded)
    dispatcher.failed.connect(on_failed)
    parent._statistics_dispatcher = dispatcher
    return dispatcher


def build_statistics_tab(parent):
    logger.log("[UI] Build Statistics tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("Statistics")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 900; color: #21443C;")
    layout.addWidget(title)

    info = QLabel("DB metrics plus parsed demo cache enrichment")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(info)

    parent._statistics_request_id = 0
    parent._statistics_loading = False
    _ensure_dispatcher(parent)

    parent._statistics_refresh = lambda: refresh_statistics_tab(parent)
    refresh_statistics_tab(parent)


def refresh_statistics_tab(parent):
    logger.log("[UI] Refresh Statistics tab", level="DEBUG")

    layout = parent.layout()
    if layout is None:
        return

    if getattr(parent, "_statistics_loading", False):
        logger.log("[UI] Statistics refresh skipped (already loading)", level="DEBUG")
        return

    request_id = int(getattr(parent, "_statistics_request_id", 0)) + 1
    parent._statistics_request_id = request_id
    parent._statistics_loading = True

    _show_loading_state(parent, "Loading statistics...")
    dispatcher = _ensure_dispatcher(parent)

    def worker():
        try:
            overview = statistics.get_overview()
            recent_rows = statistics.get_recent_maps(10)
            dispatcher.loaded.emit(request_id, overview, recent_rows)
        except Exception as e:
            dispatcher.failed.emit(request_id, e)

    executor.submit(worker)
