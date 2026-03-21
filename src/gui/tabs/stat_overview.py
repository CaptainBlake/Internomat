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

import core.stats.leaderboard as leaderboard
import services.logger as logger


TOP3_STYLES = {
    1: {"bg": QColor("#D9E9F8"), "fg": QColor("#1F4E79"), "bold": True, "medal": "🥇"},
    2: {"bg": QColor("#E8EEF5"), "fg": QColor("#4A5A6A"), "bold": True, "medal": "🥈"},
    3: {"bg": QColor("#F7D8D8"), "fg": QColor("#7A2E2E"), "bold": True, "medal": "🥉"},
}


def _style_top3_item(item, place):
    style = TOP3_STYLES.get(place)
    if not style:
        return

    item.setBackground(QBrush(style["bg"]))
    item.setForeground(QBrush(style["fg"]))

    font = item.font()
    font.setBold(style["bold"])

    if item.text() in {"🥇", "🥈", "🥉"}:
        font.setPointSize(15)
        font.setBold(True)

    item.setFont(font)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _build_leaderboard(title_text, headers, rows, value_suffix="", top3_colorize=False):
    frame = QFrame()
    frame.setStyleSheet("""
        QFrame {
            background: rgba(255, 255, 255, 0.94);
            border: none;
            border-radius: 16px;
        }
    """)

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QLabel(title_text)
    title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    title.setStyleSheet("font-size: 15px; font-weight: 800; color: #22384D;")
    layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

    table = QTableWidget(0, len(headers))
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    table.horizontalHeader().setStretchLastSection(False)

    if len(headers) == 3:
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    else:
        for i in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

    header_font = QFont()
    header_font.setPointSize(12)
    header_font.setBold(True)

    for i, text in enumerate(headers):
        header_item = QTableWidgetItem(text)
        header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        header_item.setFont(header_font)
        table.setHorizontalHeaderItem(i, header_item)

    table.horizontalHeader().setStyleSheet("""
        QHeaderView {
            border: none;
            background: transparent;
        }
        QHeaderView::section {
            background: #DCEAF7;
            color: #2E4C69;
            padding: 10px;
            border: none;
            font-size: 12pt;
            font-weight: 800;
            text-align: center;
        }
    """)

    table.setStyleSheet("""
        QTableWidget {
            background: transparent;
            border: none;
            outline: none;
            alternate-background-color: #F7FAFD;
            color: #1E2B38;
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
            background: #DCEAF7;
            color: #1E2B38;
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

    for idx, row in enumerate(rows, start=1):
        row_index = table.rowCount()
        table.insertRow(row_index)

        medal = TOP3_STYLES.get(idx, {}).get("medal", str(idx))

        rank_item = QTableWidgetItem(medal)
        player_item = QTableWidgetItem(str(row[0]))
        value_item = QTableWidgetItem(f"{row[2]}{value_suffix}")

        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        player_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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
        leaderboard.get_top_kills(10),
        top3_colorize=True,
    )

    deaths_board = _build_leaderboard(
        "Most Deaths",
        ["#", "Player", "Deaths"],
        leaderboard.get_top_deaths(10),
        top3_colorize=True,
    )

    rating_board = _build_leaderboard(
        "Top Rating",
        ["#", "Player", "Rating"],
        leaderboard.get_top_ratings(10),
        top3_colorize=True,
    )

    damage_board = _build_leaderboard(
        "Damage per Match",
        ["#", "Player", "Avg Damage"],
        leaderboard.get_top_damage_per_match(10),
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
        if item is None:
            continue

        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)

    content = QGridLayout()
    content.setSpacing(12)

    kills_board = _build_leaderboard(
        "Most Kills",
        ["#", "Player", "Kills"],
        leaderboard.get_top_kills(10),
        top3_colorize=True,
    )

    deaths_board = _build_leaderboard(
        "Most Deaths",
        ["#", "Player", "Deaths"],
        leaderboard.get_top_deaths(10),
        top3_colorize=True,
    )

    rating_board = _build_leaderboard(
        "Top Rating",
        ["#", "Player", "Rating"],
        leaderboard.get_top_ratings(10),
        top3_colorize=True,
    )

    damage_board = _build_leaderboard(
        "Damage per Match",
        ["#", "Player", "Avg Damage"],
        leaderboard.get_top_damage_per_match(10),
        top3_colorize=True,
    )

    content.addWidget(kills_board, 0, 0)
    content.addWidget(deaths_board, 0, 1)
    content.addWidget(rating_board, 1, 0)
    content.addWidget(damage_board, 1, 1)

    layout.addLayout(content, 1)
