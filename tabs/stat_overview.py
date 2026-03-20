from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

import db
import services.logger as logger


TOP3_STYLES = {
    1: {"bg": QColor("#FFF3C4"), "fg": QColor("#7A5A00"), "bold": True},   # Gold
    2: {"bg": QColor("#E8EEF5"), "fg": QColor("#4A5A6A"), "bold": True},   # Silver
    3: {"bg": QColor("#F6D9B8"), "fg": QColor("#7A3E00"), "bold": True},   # Bronze
}


def _style_top3_item(item, place):
    style = TOP3_STYLES.get(place)
    if not style:
        return

    item.setBackground(QBrush(style["bg"]))
    item.setForeground(QBrush(style["fg"]))

    font = item.font()
    font.setBold(style["bold"])
    item.setFont(font)


def _build_leaderboard(title_text, headers, rows, value_suffix="", top3_colorize=False):
    frame = QFrame()
    frame.setStyleSheet("""
        QFrame {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid #D5EEE6;
            border-radius: 16px;
        }
    """)

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QLabel(title_text)
    title.setStyleSheet("font-size: 15px; font-weight: 800; color: #21443C;")
    layout.addWidget(title)

    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(False)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    table.setStyleSheet("""
        QTableWidget {
            background: transparent;
            border: none;
            alternate-background-color: #F8FCFA;
            color: #20443D;
        }
        QHeaderView::section {
            background: #EAF8F3;
            color: #4A7168;
            padding: 6px;
            border: none;
            font-weight: 700;
        }
        QTableWidget::item {
            padding: 6px;
        }
    """)

    for idx, row in enumerate(rows, start=1):
        row_index = table.rowCount()
        table.insertRow(row_index)

        rank_item = QTableWidgetItem(str(idx))
        player_item = QTableWidgetItem(str(row[0]))
        value_item = QTableWidgetItem(f"{row[2]}{value_suffix}")

        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        value_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if top3_colorize:
            _style_top3_item(rank_item, idx)
            _style_top3_item(player_item, idx)
            _style_top3_item(value_item, idx)

        table.setItem(row_index, 0, rank_item)
        table.setItem(row_index, 1, player_item)
        table.setItem(row_index, 2, value_item)

    layout.addWidget(table, 1)
    return frame


def build_stat_overview_tab(parent):
    logger.log("[UI] Build Stat Overview tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("Stat Overview")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 900; color: #21443C;")
    layout.addWidget(title)

    info = QLabel("Top Leaderboards aus den Match-Statistiken")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(info)

    content = QGridLayout()
    content.setSpacing(12)

    kills_board = _build_leaderboard(
        "Most Kills",
        ["#", "Player", "Kills"],
        db.get_top_kills(10),
        top3_colorize=True,
    )

    deaths_board = _build_leaderboard(
        "Most Deaths",
        ["#", "Player", "Deaths"],
        db.get_top_deaths(10),
        top3_colorize=True,
    )

    rating_board = _build_leaderboard(
        "Top Rating",
        ["#", "Player", "Rating"],
        db.get_top_ratings(10),
        top3_colorize=True,
    )

    damage_board = _build_leaderboard(
        "Damage per Match",
        ["#", "Player", "Avg Damage"],
        db.get_top_damage_per_match(10),
        top3_colorize=True,
    )

    content.addWidget(kills_board, 0, 0)
    content.addWidget(deaths_board, 0, 1)
    content.addWidget(rating_board, 1, 0)
    content.addWidget(damage_board, 1, 1)

    layout.addLayout(content, 1)

    parent._stat_overview_refresh = lambda: refresh_stat_overview(parent)


def refresh_stat_overview(parent):
    logger.log("[UI] Refresh Stat Overview tab", level="DEBUG")

    layout = parent.layout()
    if layout is None:
        return

    while layout.count() > 2:
        item = layout.takeAt(2)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

    content = QGridLayout()
    content.setSpacing(12)

    kills_board = _build_leaderboard(
        "Most Kills",
        ["#", "Player", "Kills"],
        db.get_top_kills(10),
        top3_colorize=True,
    )

    deaths_board = _build_leaderboard(
        "Most Deaths",
        ["#", "Player", "Deaths"],
        db.get_top_deaths(10),
        top3_colorize=True,
    )

    rating_board = _build_leaderboard(
        "Top Rating",
        ["#", "Player", "Rating"],
        db.get_top_ratings(10),
        top3_colorize=True,
    )

    damage_board = _build_leaderboard(
        "Damage per Match",
        ["#", "Player", "Avg Damage"],
        db.get_top_damage_per_match(10),
        top3_colorize=True,
    )

    content.addWidget(kills_board, 0, 0)
    content.addWidget(deaths_board, 0, 1)
    content.addWidget(rating_board, 1, 0)
    content.addWidget(damage_board, 1, 1)

    layout.addLayout(content, 1)