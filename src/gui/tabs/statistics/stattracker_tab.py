from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

import core.stats.stattracker as stattracker
import services.logger as logger


def _fmt_pct(value):
    return f"{float(value):.1f}%"


def _build_table(headers, rows):
    table = QTableWidget()
    table.setSortingEnabled(False)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    for row_index, row_values in enumerate(rows):
        for col_index, value in enumerate(row_values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_index, col_index, item)

    table.setSortingEnabled(True)

    return table


def _fit_single_row_table_height(table, extra_padding=8):
    if table is None:
        return

    # Ensure row geometry is materialized before reading row/header heights.
    table.resizeRowsToContents()

    header_h = table.horizontalHeader().height()
    row_h = table.rowHeight(0) if table.rowCount() > 0 else 0
    frame_h = table.frameWidth() * 2
    table.setFixedHeight(header_h + row_h + frame_h + int(extra_padding))


def _clear_layout_item(item):
    if item is None:
        return

    widget = item.widget()
    if widget is not None:
        widget.setParent(None)
        widget.deleteLater()
        return

    child_layout = item.layout()
    if child_layout is not None:
        while child_layout.count() > 0:
            child_item = child_layout.takeAt(0)
            _clear_layout_item(child_item)
        return


def _on_player_changed(parent, combo):
    sid = combo.currentData()
    parent._stattracker_selected_player = str(sid or "")
    refresh_stattracker(parent)


def _on_main_view_changed(parent, combo):
    parent._stattracker_main_view = str(combo.currentData() or "weapons")
    refresh_stattracker(parent)


def _on_weapon_category_changed(parent, combo):
    parent._stattracker_weapon_category = str(combo.currentData() or "all")
    refresh_stattracker(parent)


def build_stattracker_tab(parent):
    logger.log("[UI] Build Stat Tracker tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("Stat Tracker")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 900; color: #21443C;")
    layout.addWidget(title)

    info = QLabel("Player-focused analytics")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(info)

    parent._stattracker_cache_dirty = True
    parent._stattracker_overview = None
    parent._stattracker_player_options = []
    parent._stattracker_selected_player = ""
    parent._stattracker_main_view = "weapons"
    parent._stattracker_weapon_category = "all"
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
        _clear_layout_item(item)

    cache_dirty = getattr(parent, "_stattracker_cache_dirty", True)
    if cache_dirty:
        parent._stattracker_cache_dirty = False

    player_options = getattr(parent, "_stattracker_player_options", None)
    if cache_dirty or not isinstance(player_options, list) or not player_options:
        player_options = stattracker.get_player_options()
        parent._stattracker_player_options = player_options

    panel = QFrame()
    panel.setStyleSheet(
        """
        QFrame {
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid #D5E0EA;
            border-radius: 12px;
        }
        """
    )
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(12, 12, 12, 12)
    panel_layout.setSpacing(8)

    select_title = QLabel("Player Selection")
    select_title.setStyleSheet("font-size: 13px; font-weight: 900; color: #21443C;")
    panel_layout.addWidget(select_title)

    player_row = QHBoxLayout()
    player_row.setSpacing(8)

    picker = QComboBox()
    picker.setMinimumWidth(420)
    picker.blockSignals(True)
    selected_sid = str(getattr(parent, "_stattracker_selected_player", "") or "")
    for option in player_options:
        sid = str(option.get("steamid64") or "")
        label = f"{option.get('player_name', sid)} ({sid[-6:]})"
        picker.addItem(label, sid)

    if picker.count() > 0:
        if not selected_sid:
            selected_sid = str(player_options[0].get("steamid64") or "")
            parent._stattracker_selected_player = selected_sid

        idx = picker.findData(selected_sid)
        if idx < 0:
            idx = 0
            selected_sid = str(picker.itemData(0) or "")
            parent._stattracker_selected_player = selected_sid
        picker.setCurrentIndex(idx)

    picker.blockSignals(False)
    picker.currentIndexChanged.connect(lambda _i: _on_player_changed(parent, picker))
    player_row.addWidget(picker)
    player_row.addStretch(1)
    panel_layout.addLayout(player_row)

    layout.addWidget(panel)

    if not selected_sid:
        hint = QLabel("No player data available yet. Parse demos to populate Stat Tracker.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 16px;")
        layout.addWidget(hint, 1)
        return

    selected_category = str(getattr(parent, "_stattracker_weapon_category", "all") or "all")

    dashboard = stattracker.get_player_dashboard(
        selected_sid,
        min_weapon_shots=1,
        weapon_category=selected_category,
    )
    kpis = dashboard.get("kpis") or {}

    global_title = QLabel("Global Stats")
    global_title.setStyleSheet("font-size: 13px; font-weight: 900; color: #21443C;")
    layout.addWidget(global_title)

    global_table = _build_table(
        [
            "Maps Played",
            "Win Rate",
            "K/D",
            "ADR",
            "Avg Kills",
            "Avg Deaths",
            "Avg Assists",
            "HS%",
            "Avg KAST",
            "Avg Impact",
            "Avg Rating",
            "Avg Performance",
        ],
        [
            [
                int(kpis.get("maps_played") or 0),
                _fmt_pct(kpis.get("win_rate") or 0.0),
                f"{float(kpis.get('kdr') or 0.0):.2f}",
                f"{float(kpis.get('adr') or 0.0):.1f}",
                f"{float(kpis.get('avg_kills') or 0.0):.2f}",
                f"{float(kpis.get('avg_deaths') or 0.0):.2f}",
                f"{float(kpis.get('avg_assists') or 0.0):.2f}",
                _fmt_pct(kpis.get("hs_pct") or 0.0),
                "-" if kpis.get("avg_kast") is None else _fmt_pct(kpis.get("avg_kast") or 0.0),
                "-" if kpis.get("avg_impact") is None else f"{float(kpis.get('avg_impact') or 0.0):.2f}",
                "-" if kpis.get("avg_rating") is None else f"{float(kpis.get('avg_rating') or 0.0):.2f}",
                f"{float(kpis.get('performance_index') or 0.0):.2f}",
            ]
        ],
    )
    _fit_single_row_table_height(global_table)
    layout.addWidget(global_table)

    insight_title = QLabel("Insight Selection")
    insight_title.setStyleSheet("font-size: 14px; font-weight: 900; color: #21443C; margin-top: 4px;")
    layout.addWidget(insight_title)

    insight_row = QHBoxLayout()
    insight_row.setSpacing(8)

    main_view = str(getattr(parent, "_stattracker_main_view", "weapons") or "weapons")
    view_combo = QComboBox()
    view_combo.addItem("Weapons", "weapons")
    view_combo.addItem("Maps", "maps")
    view_combo.addItem("Other", "other")
    idx = view_combo.findData(main_view)
    if idx < 0:
        idx = 0
        main_view = "weapons"
        parent._stattracker_main_view = main_view
    view_combo.setCurrentIndex(idx)
    view_combo.currentIndexChanged.connect(lambda _i: _on_main_view_changed(parent, view_combo))
    insight_row.addWidget(view_combo)

    category_combo = QComboBox()
    categories = stattracker.get_player_weapon_categories(selected_sid) if selected_sid else ["all"]
    for category in categories:
        label = "All Categories" if category == "all" else category.title()
        category_combo.addItem(label, category)

    cidx = category_combo.findData(selected_category)
    if cidx < 0:
        cidx = 0
        selected_category = str(category_combo.itemData(0) or "all")
        parent._stattracker_weapon_category = selected_category
    category_combo.setCurrentIndex(cidx)
    category_combo.currentIndexChanged.connect(lambda _i: _on_weapon_category_changed(parent, category_combo))
    category_combo.setVisible(main_view == "weapons")
    insight_row.addWidget(category_combo)
    insight_row.addStretch(1)
    layout.addLayout(insight_row)

    map_rows = dashboard.get("map_rows") or []
    best_map = str(dashboard.get("best_map") or "-")
    worst_map = str(dashboard.get("worst_map") or "-")

    map_summary = QLabel(f"Best Map: {best_map} | Worst Map: {worst_map}")
    map_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
    map_summary.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(map_summary)

    weapon_rows = dashboard.get("weapon_rows") or []

    main_title = QLabel("Main Table")
    main_title.setStyleSheet("font-size: 13px; font-weight: 900; color: #21443C;")
    layout.addWidget(main_title)

    if main_view == "maps":
        map_table = _build_table(
            ["Map", "Played", "Wins", "Win%", "K/D", "ADR"],
            [
                [
                    r["map_name"],
                    r["maps_played"],
                    r["wins"],
                    _fmt_pct(r["win_rate"]),
                    f"{float(r['kdr']):.2f}",
                    f"{float(r['adr']):.1f}",
                ]
                for r in map_rows
            ],
        )
        layout.addWidget(map_table, 1)
    elif main_view == "other":
        placeholder = _build_table(
            ["Section", "Status"],
            [["Other advanced tables", "Coming next"]],
        )
        placeholder.setMinimumHeight(96)
        layout.addWidget(placeholder, 1)
    else:
        weapon_table = _build_table(
            ["Weapon", "Category", "Shots", "Hits", "Acc", "Kills", "HS%", "Damage", "Rounds"],
            [
                [
                    r["weapon"],
                    r.get("category", "unknown"),
                    r["shots_fired"],
                    r["shots_hit"],
                    _fmt_pct(r["accuracy"]),
                    r["kills"],
                    _fmt_pct(r["headshot_pct"]),
                    r["damage"],
                    r["rounds_with_weapon"],
                ]
                for r in weapon_rows
            ],
        )
        layout.addWidget(weapon_table, 1)


def on_stattracker_data_updated(parent):
    logger.log("[UI] Stat Tracker data update triggered", level="DEBUG")
    parent._stattracker_cache_dirty = True
    refresh_stattracker(parent)
