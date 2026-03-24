from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

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

    title = QLabel("Recent Maps")
    title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    title.setStyleSheet("font-size: 15px; font-weight: 800; color: #22384D;")
    layout.addWidget(title)

    table = QTableWidget(0, 6)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)

    headers = ["Match", "Map", "Winner", "Score", "At", "#"]
    for i, text in enumerate(headers):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setHorizontalHeaderItem(i, item)

    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

    table.horizontalHeader().setStyleSheet(
        """
        QHeaderView::section {
            background: #DCEAF7;
            color: #2E4C69;
            padding: 8px;
            border: none;
            font-size: 11pt;
            font-weight: 800;
            text-align: center;
        }
        """
    )

    table.setStyleSheet(
        """
        QTableWidget {
            background: transparent;
            border: none;
            outline: none;
            alternate-background-color: #F7FAFD;
            color: #1E2B38;
        }
        QTableWidget::item {
            padding: 6px;
            border: none;
        }
        """
    )

    for row in rows:
        idx = table.rowCount()
        table.insertRow(idx)

        values = [
            row["match_id"],
            row["map_name"],
            row["winner"],
            f"{row['team1_score']}:{row['team2_score']}",
            row["played_at"],
            str(row["map_number"]),
        ]

        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(idx, col, item)

    layout.addWidget(table, 1)
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

    info = QLabel("Quick summary and recent map results")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(info)

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

    overview = stattracker.get_overview()
    recent_rows = stattracker.get_recent_maps(10)

    metrics = QHBoxLayout()
    metrics.setSpacing(12)
    metrics.addWidget(_build_metric_card("Total Matches", str(overview["total_matches"])))
    metrics.addWidget(_build_metric_card("Unique Players", str(overview["unique_players"])))
    metrics.addWidget(_build_metric_card("Avg Total Score", f"{overview['avg_map_total_score']:.2f}"))

    layout.addLayout(metrics)
    layout.addWidget(_build_recent_maps_table(recent_rows), 1)
