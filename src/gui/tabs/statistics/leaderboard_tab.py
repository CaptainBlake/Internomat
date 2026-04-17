from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

import core.stats.leaderboard as leaderboard
import services.logger as logger


TOP3_STYLES = {
    1: {"bg": QColor("#DCE7B0"), "fg": QColor("#2E4B57"), "bold": True, "medal": "🥇"},
    2: {"bg": QColor("#E7EEE9"), "fg": QColor("#34675C"), "bold": True, "medal": "🥈"},
    3: {"bg": QColor("#D7E2EB"), "fg": QColor("#4F6D68"), "bold": True, "medal": "🥉"},
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
            background: rgba(50, 72, 81, 0.92);
            border: 1px solid #4F6D68;
            border-radius: 16px;
        }
    """)

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QLabel(title_text)
    title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    title.setStyleSheet("font-size: 14px; font-weight: 800; color: #F7FAF5;")
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
            background: #324851;
            color: #DCE7E0;
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
            alternate-background-color: #36545A;
            color: #F2F6F4;
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
        QTableWidget::item:hover {
            background: rgba(134, 172, 65, 0.16);
        }
        QTableWidget::item:selected {
            background: #34675C;
            color: #FFFFFF;
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


def _compute_stat_overview_payload(season=None):
    return {
        "kills": leaderboard.get_top_kills(10, season=season),
        "deaths": leaderboard.get_top_deaths(10, season=season),
        "ratings": leaderboard.get_top_ratings(50, season=season),
        "damage": leaderboard.get_top_damage_per_match(10, season=season),
    }


def _render_stat_overview_content(layout, payload):
    content = QGridLayout()
    content.setSpacing(14)

    kills_board = _build_leaderboard(
        "Most Kills",
        ["#", "Player", "Kills"],
        payload.get("kills") or [],
        top3_colorize=True,
    )

    deaths_board = _build_leaderboard(
        "Most Deaths",
        ["#", "Player", "Deaths"],
        payload.get("deaths") or [],
        top3_colorize=True,
    )

    rating_board = _build_leaderboard(
        "Top Rating",
        ["#", "Player", "Rating"],
        payload.get("ratings") or [],
        top3_colorize=True,
    )

    damage_board = _build_leaderboard(
        "Damage per Match",
        ["#", "Player", "Avg Damage"],
        payload.get("damage") or [],
        top3_colorize=True,
    )

    content.addWidget(kills_board, 0, 0)
    content.addWidget(deaths_board, 0, 1)
    content.addWidget(rating_board, 1, 0)
    content.addWidget(damage_board, 1, 1)

    layout.addLayout(content, 1)


def _sync_season_combo(parent):
    combo = getattr(parent, "_stat_overview_season_combo", None)
    if combo is None:
        return

    selected = getattr(parent, "_stat_overview_selected_season", None)
    options = [int(s) for s in (leaderboard.get_season_options() or [])]

    was_blocked = combo.blockSignals(True)
    combo.clear()
    combo.addItem("ALL Seasons", None)
    for season_id in options:
        combo.addItem(f"Season {season_id}", int(season_id))

    if selected is not None and int(selected) in options:
        idx = combo.findData(int(selected))
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        parent._stat_overview_selected_season = int(selected)
    else:
        combo.setCurrentIndex(0)
        parent._stat_overview_selected_season = None

    combo.blockSignals(was_blocked)


def build_stat_overview_tab(parent):
    logger.log("[UI] Build Stat Overview tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    title = QLabel("Stat Overview")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 900; color: #F7FAF5;")
    layout.addWidget(title)

    info = QLabel("Top Leaderboards aus den Match-Statistiken")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #DCE7E0;")
    layout.addWidget(info)

    parent._stat_overview_selected_season = None

    season_row = QHBoxLayout()
    season_row.addStretch(1)
    season_row.addWidget(QLabel("Season:"))
    season_combo = QComboBox()
    season_combo.setMinimumWidth(190)
    season_combo.addItem("ALL Seasons", None)
    for season_id in leaderboard.get_season_options():
        season_combo.addItem(f"Season {season_id}", int(season_id))

    def _on_season_changed(_idx):
        parent._stat_overview_selected_season = season_combo.currentData()
        parent._stat_overview_cache_dirty = True
        refresh_stat_overview(parent)

    season_combo.currentIndexChanged.connect(_on_season_changed)
    season_row.addWidget(season_combo)
    season_row.addStretch(1)
    layout.addLayout(season_row)
    parent._stat_overview_season_combo = season_combo

    parent._stat_overview_cache_dirty = True
    parent._stat_overview_payload = None

    refresh_stat_overview(parent)
    parent._stat_overview_on_update = lambda: on_stat_overview_data_updated(parent)
    parent._stat_overview_refresh = lambda: refresh_stat_overview(parent)


def refresh_stat_overview(parent):
    logger.log("[UI] Refresh Stat Overview tab", level="DEBUG")

    layout = parent.layout()
    if layout is None:
        return

    _sync_season_combo(parent)

    while layout.count() > 3:
        item = layout.takeAt(3)
        if item is None:
            continue

        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)

    cache_dirty = getattr(parent, "_stat_overview_cache_dirty", True)
    payload = getattr(parent, "_stat_overview_payload", None)
    selected_season = getattr(parent, "_stat_overview_selected_season", None)

    if cache_dirty or not isinstance(payload, dict):
        payload = _compute_stat_overview_payload(season=selected_season)
        parent._stat_overview_payload = payload
        parent._stat_overview_cache_dirty = False

    _render_stat_overview_content(layout, payload)


def on_stat_overview_data_updated(parent):
    logger.log("[UI] Stat Overview data update triggered", level="DEBUG")
    parent._stat_overview_cache_dirty = True
    _sync_season_combo(parent)
    refresh_stat_overview(parent)