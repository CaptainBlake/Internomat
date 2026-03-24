from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

import core.stats.stattracker as stattracker
import services.logger as logger


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


def build_stattracker_tab(parent):
    logger.log("[UI] Build Stat Tracker tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("Stat Tracker")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 900; color: #21443C;")
    layout.addWidget(title)

    info = QLabel("Player-focused analytics (preparation scaffold)")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(info)

    parent._stattracker_cache_dirty = True
    parent._stattracker_overview = None
    parent._stattracker_on_update = lambda: on_stattracker_data_updated(parent)
    parent._stattracker_refresh = lambda: refresh_stattracker(parent)
    refresh_stattracker(parent)


def refresh_stattracker(parent):
    logger.log("[UI] Refresh Stat Tracker tab", level="DEBUG")

    layout = parent.layout()
    if layout is None:
        return

    while layout.count() > 2:
        item = layout.takeAt(2)
        if item is None:
            continue

        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()

    cache_dirty = getattr(parent, "_stattracker_cache_dirty", True)
    overview = getattr(parent, "_stattracker_overview", None)
    if cache_dirty or not isinstance(overview, dict):
        overview = stattracker.get_overview()
        parent._stattracker_overview = overview
        parent._stattracker_cache_dirty = False

    metrics = QHBoxLayout()
    metrics.setSpacing(12)
    metrics.addWidget(_build_metric_card("Tracked Players", str(overview["tracked_players"])))
    metrics.addWidget(_build_metric_card("Player Stat Rows", str(overview["player_stat_rows"])))
    metrics.addWidget(_build_metric_card("Unique Player-Maps", str(overview["unique_player_maps"])))
    layout.addLayout(metrics)

    hint = QLabel("Detailed player analytics widgets will be added in the next step.")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hint.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 16px;")
    layout.addWidget(hint, 1)


def on_stattracker_data_updated(parent):
    logger.log("[UI] Stat Tracker data update triggered", level="DEBUG")
    parent._stattracker_cache_dirty = True
    refresh_stattracker(parent)
