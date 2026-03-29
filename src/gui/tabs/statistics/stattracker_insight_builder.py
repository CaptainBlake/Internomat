"""
Builders and handlers for the Stat Tracker Insight Selection section.

This module encapsulates all logic related to the filter row, content area,
and event handlers for the insight/comparison view in the Stat Tracker tab.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import core.stats.stattracker as stattracker


# ---------------------------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------------------------

def _on_main_view_changed(parent, combo):
    parent._stattracker_main_view = str(combo.currentData() or "weapons")
    parent._stattracker_selected_map = "all"
    parent._stattracker_selected_weapon = "all"
    parent._stattracker_timeline = False  # reset timeline on view switch
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_weapon_category_changed(parent, combo):
    parent._stattracker_weapon_category = str(combo.currentData() or "all")
    parent._stattracker_selected_weapon = "all"
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_map_selected_changed(parent, combo):
    parent._stattracker_selected_map = str(combo.currentData() or "all")
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_weapon_selected_changed(parent, combo):
    parent._stattracker_selected_weapon = str(combo.currentData() or "all")
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_timeline_toggled(parent, checked):
    parent._stattracker_timeline = checked
    # Clear stored multi-select so timeline always re-initialises from current
    # single-select state, preventing desync when switching between modes.
    parent._stattracker_selected_timeline_items = []
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_timeline_selection_changed(parent):
    """Re-render the plot when any multi-select combo changes."""
    item_combo = getattr(parent, "_stattracker_timeline_combo", None)
    if item_combo is not None:
        parent._stattracker_selected_timeline_items = list(item_combo.checked_data() or [])

    metric_combo = getattr(parent, "_stattracker_metric_combo", None)
    if metric_combo is not None:
        parent._stattracker_selected_plot_metrics = list(metric_combo.checked_data() or [])

    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_chart_mode_changed(parent, combo):
    parent._stattracker_chart_mode = str(combo.currentData() or "line")
    _on_timeline_selection_changed(parent)


def _on_compare_player_changed(parent, combo):
    parent._stattracker_compare_player = str(combo.currentData() or "")
    _on_timeline_selection_changed(parent)


def _create_weapon_table_click_handler_internal(parent):
    def handler(row, col, table, headers, rows):
        _on_weapon_table_cell_clicked(parent, row, col, table, headers, rows)
    return handler


def _create_map_table_click_handler_internal(parent):
    def handler(row, col, table, headers, rows):
        _on_map_table_cell_clicked(parent, row, col, table, headers, rows)
    return handler


def _on_weapon_table_cell_clicked(parent, row, col, table, headers, rows):
    cell_text = str(table.item(row, col).text())
    if col == 0:
        parent._stattracker_selected_weapon = cell_text
        weapon_combo = getattr(parent, "_stattracker_weapon_combo", None)
        if weapon_combo:
            idx = weapon_combo.findData(cell_text)
            if idx >= 0:
                weapon_combo.blockSignals(True)
                weapon_combo.setCurrentIndex(idx)
                weapon_combo.blockSignals(False)
        from .stattracker_tab import refresh_stattracker
        refresh_stattracker(parent)
    elif col == 1:
        parent._stattracker_weapon_category = cell_text
        parent._stattracker_selected_weapon = "all"
        from .stattracker_tab import refresh_stattracker
        refresh_stattracker(parent)


def _on_map_table_cell_clicked(parent, row, col, table, headers, rows):
    cell_text = str(table.item(row, col).text())
    if col == 0:
        parent._stattracker_selected_map = cell_text
        map_combo = getattr(parent, "_stattracker_map_combo", None)
        if map_combo:
            idx = map_combo.findData(cell_text)
            if idx >= 0:
                map_combo.blockSignals(True)
                map_combo.setCurrentIndex(idx)
                map_combo.blockSignals(False)
        from .stattracker_tab import refresh_stattracker
        refresh_stattracker(parent)


# ---------------------------------------------------------------------------
# Insight Section Builder
# ---------------------------------------------------------------------------

def build_insight_section(parent, layout, dashboard, selected_sid, selected_category):
    """
    Build and add the entire insight selection section to the layout.
    
    This includes:
    - The filter row (view toggle, category, selector, metric, badges, timeline toggle)
    - The content title
    - The content area (timeline plot OR table/statboard)
    """
    from .stattracker_tab import (
        _CheckableCombo,
        _build_table,
        _build_statboard_section,
        _fmt_pct,
        _refresh_plot_only,
    )

    # --- Insight Selection title ---
    insight_title = QLabel("Insight Selection")
    insight_title.setStyleSheet("font-size: 14px; font-weight: 900; color: #21443C; margin-top: 4px;")
    layout.addWidget(insight_title)

    map_rows = dashboard.get("map_rows") or []
    weapon_rows = dashboard.get("weapon_rows") or []
    main_view = str(getattr(parent, "_stattracker_main_view", "weapons") or "weapons")
    is_timeline = bool(getattr(parent, "_stattracker_timeline", False))

    # --- Single unified filter row ---
    insight_row = QHBoxLayout()
    insight_row.setSpacing(8)

    # [1] View toggle: Weapons / Maps
    view_combo = QComboBox()
    view_combo.addItem("Weapons", "weapons")
    view_combo.addItem("Maps", "maps")
    idx = view_combo.findData(main_view)
    if idx < 0:
        idx = 0
        main_view = "weapons"
        parent._stattracker_main_view = main_view
    view_combo.setCurrentIndex(idx)
    view_combo.currentIndexChanged.connect(lambda _i: _on_main_view_changed(parent, view_combo))
    insight_row.addWidget(view_combo)

    # [2] Category filter (weapons only, both modes)
    if main_view == "weapons":
        category_combo = QComboBox()
        categories = stattracker.get_player_weapon_categories(selected_sid) if selected_sid else ["all"]
        for category in categories:
            label = "All Categories" if category == "all" else category.title()
            category_combo.addItem(label, category)
        cidx = category_combo.findData(selected_category)
        if cidx < 0:
            cidx = 0
        category_combo.setCurrentIndex(cidx)
        category_combo.currentIndexChanged.connect(lambda _i: _on_weapon_category_changed(parent, category_combo))
        insight_row.addWidget(category_combo)

    # [3] Item selector – single-select QComboBox (table) or multi-select _CheckableCombo (timeline)
    selected_weapon = str(getattr(parent, "_stattracker_selected_weapon", "all") or "all")
    selected_map = str(getattr(parent, "_stattracker_selected_map", "all") or "all")
    stored_timeline_items = list(getattr(parent, "_stattracker_selected_timeline_items", []) or [])

    if is_timeline:
        item_label = "Maps" if main_view == "maps" else "Weapons"
        item_multi = _CheckableCombo(label_plural=item_label)
        item_multi.setMinimumWidth(200)
        if main_view == "maps":
            for mr in (map_rows or []):
                name = str(mr.get("map_name", "?"))
                if stored_timeline_items:
                    checked = name in stored_timeline_items
                else:
                    checked = True if selected_map == "all" else (name == selected_map)
                item_multi.add_checkable_item(name, data=name, checked=checked)
        else:
            filtered = weapon_rows or []
            if selected_category != "all":
                filtered = [w for w in filtered if w.get("category") == selected_category]
            filtered = sorted(filtered, key=lambda w: int(w.get("shots_fired") or 0), reverse=True)
            for wr in filtered:
                name = str(wr.get("weapon", "?"))
                if stored_timeline_items:
                    checked = name in stored_timeline_items
                else:
                    checked = True if selected_weapon == "all" else (name == selected_weapon)
                item_multi.add_checkable_item(name, data=name, checked=checked)
        item_multi._update_display_text()
        # Use dataChanged (fires after state is committed) for reliable live update.
        item_multi._model.dataChanged.connect(lambda *_: _on_timeline_selection_changed(parent))
        parent._stattracker_timeline_combo = item_multi
        insight_row.addWidget(item_multi)
    else:
        parent._stattracker_timeline_combo = None
        if main_view == "weapons":
            weapon_combo = QComboBox()
            weapon_combo.addItem("All Weapons", "all")
            filtered_weapons = weapon_rows if selected_category == "all" else [w for w in weapon_rows if w.get("category") == selected_category]
            for wr in filtered_weapons:
                weapon_combo.addItem(wr.get("weapon", "unknown"), wr.get("weapon", "unknown"))
            widx = weapon_combo.findData(selected_weapon)
            if widx < 0:
                widx = 0
            weapon_combo.setCurrentIndex(widx)
            weapon_combo.currentIndexChanged.connect(lambda _i: _on_weapon_selected_changed(parent, weapon_combo))
            insight_row.addWidget(weapon_combo)
            parent._stattracker_weapon_combo = weapon_combo
        else:
            map_combo = QComboBox()
            map_combo.addItem("All Maps", "all")
            for mr in map_rows:
                map_combo.addItem(mr.get("map_name", "unknown"), mr.get("map_name", "unknown"))
            midx = map_combo.findData(selected_map)
            if midx < 0:
                midx = 0
            map_combo.setCurrentIndex(midx)
            map_combo.currentIndexChanged.connect(lambda _i: _on_map_selected_changed(parent, map_combo))
            insight_row.addWidget(map_combo)
            parent._stattracker_map_combo = map_combo

    # [4] Metric selector (timeline only) – multi-select _CheckableCombo
    if is_timeline:
        metric_multi = _CheckableCombo(label_plural="Metrics")
        metric_multi.setMinimumWidth(160)
        if main_view == "maps":
            opts = stattracker.get_map_plot_metric_options()
            default_metric = "kd_ratio"
        else:
            opts = stattracker.get_plot_metric_options()
            default_metric = "accuracy"
        current_metric = str(getattr(parent, "_stattracker_plot_metric", default_metric) or default_metric)
        stored_metrics = list(getattr(parent, "_stattracker_selected_plot_metrics", []) or [])
        for opt in opts:
            checked = (opt["key"] in stored_metrics) if stored_metrics else (opt["key"] == current_metric)
            metric_multi.add_checkable_item(opt["label"], data=opt["key"], checked=checked)
        metric_multi._update_display_text()
        # Use dataChanged for reliable live update (same pattern as item_multi).
        metric_multi._model.dataChanged.connect(lambda *_: _on_timeline_selection_changed(parent))
        parent._stattracker_metric_combo = metric_multi
        insight_row.addWidget(QLabel("Metric:"))
        insight_row.addWidget(metric_multi)

        chart_mode_combo = QComboBox()
        chart_mode_combo.addItem("Line chart", "line")
        chart_mode_combo.addItem("Columns", "columns")
        chart_mode_combo.addItem("Pie", "pie")
        chart_mode = str(getattr(parent, "_stattracker_chart_mode", "line") or "line")
        chart_mode_idx = chart_mode_combo.findData(chart_mode)
        if chart_mode_idx < 0:
            chart_mode_idx = 0
            parent._stattracker_chart_mode = "line"
        chart_mode_combo.setCurrentIndex(chart_mode_idx)
        chart_mode_combo.currentIndexChanged.connect(lambda _i: _on_chart_mode_changed(parent, chart_mode_combo))
        insight_row.addWidget(QLabel("Display:"))
        insight_row.addWidget(chart_mode_combo)

        compare_combo = QComboBox()
        compare_combo.setMinimumWidth(160)
        compare_combo.addItem("none", "")
        player_options = getattr(parent, "_stattracker_player_options", []) or []
        for opt in player_options:
            sid_opt = str(opt.get("steamid64") or "")
            if sid_opt and sid_opt != str(selected_sid or ""):
                compare_combo.addItem(str(opt.get("player_name") or sid_opt), sid_opt)

        compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
        compare_idx = compare_combo.findData(compare_sid)
        if compare_idx < 0:
            compare_idx = 0
            parent._stattracker_compare_player = ""
        compare_combo.setCurrentIndex(compare_idx)
        compare_combo.currentIndexChanged.connect(lambda _i: _on_compare_player_changed(parent, compare_combo))
        insight_row.addWidget(QLabel("Compare to player:"))
        insight_row.addWidget(compare_combo)
    else:
        parent._stattracker_metric_combo = None

    # [5] Best/Worst badges (maps table mode only)
    if main_view == "maps" and not is_timeline:
        insight_row.addSpacing(12)
        best_map = str(dashboard.get("best_map") or "-")
        worst_map = str(dashboard.get("worst_map") or "-")
        best_badge = QLabel(f"Best: {best_map}")
        best_badge.setStyleSheet(
            "font-size: 11px; color: #21443C; font-weight: 700; "
            "background: rgba(245, 249, 252, 0.4); border: 1px solid #D5E0EA; "
            "border-radius: 6px; padding: 4px 8px;"
        )
        worst_badge = QLabel(f"Worst: {worst_map}")
        worst_badge.setStyleSheet(
            "font-size: 11px; color: #21443C; font-weight: 700; "
            "background: rgba(245, 249, 252, 0.4); border: 1px solid #D5E0EA; "
            "border-radius: 6px; padding: 4px 8px;"
        )
        insight_row.addWidget(best_badge)
        insight_row.addWidget(worst_badge)

    # [6] Timeline toggle (always visible, right-aligned)
    insight_row.addStretch(1)
    timeline_cb = QCheckBox("Timeline")
    timeline_cb.setChecked(is_timeline)
    timeline_cb.setStyleSheet("font-size: 11px; font-weight: 700;")
    timeline_cb.toggled.connect(lambda checked: _on_timeline_toggled(parent, checked))
    insight_row.addWidget(timeline_cb)

    layout.addLayout(insight_row)
    layout.addSpacing(8)

    # --- Content title ---
    if is_timeline:
        if main_view == "maps":
            main_title_text = "Map Performance Timeline"
        else:
            cat_label = "All" if selected_category == "all" else selected_category.title()
            main_title_text = f"{cat_label} Weapon Timeline"
    elif main_view == "maps":
        main_title_text = f"Map Details: {selected_map}" if selected_map != "all" else "All Maps"
    elif main_view == "weapons":
        if selected_weapon != "all":
            main_title_text = f"Weapon: {selected_weapon}"
        else:
            category_label = "All" if selected_category == "all" else selected_category.title()
            main_title_text = f"{category_label} Weapons"
    else:
        main_title_text = "Insight"

    main_title = QLabel(main_title_text)
    main_title.setStyleSheet("font-size: 13px; font-weight: 900; color: #21443C;")
    layout.addWidget(main_title)

    # --- Content area ---
    if is_timeline:
        # Plot container (refreshed independently via _refresh_plot_only)
        plot_container = QWidget()
        plot_container_layout = QVBoxLayout(plot_container)
        plot_container_layout.setContentsMargins(0, 0, 0, 0)
        parent._stattracker_plot_container = plot_container
        layout.addWidget(plot_container, 1)
        _refresh_plot_only(parent)

    elif main_view == "maps":
        if selected_map != "all":
            map_detail = next((r for r in map_rows if r.get("map_name") == selected_map), None)
            if map_detail:
                statboard = _build_statboard_section(
                    f"{selected_map} Performance",
                    {
                        "Matches Played": int(map_detail.get("maps_played") or 0),
                        "Wins": int(map_detail.get("wins") or 0),
                        "Win Rate": _fmt_pct(map_detail.get("win_rate") or 0.0),
                        "K/D Ratio": f"{float(map_detail.get('kdr') or 0.0):.2f}",
                        "ADR": f"{float(map_detail.get('adr') or 0.0):.1f}",
                    },
                )
                layout.addWidget(statboard)
            else:
                hint = QLabel("Selected map is not available for this player.")
                hint.setStyleSheet("font-size: 12px; color: #5B7A72;")
                layout.addWidget(hint)
        else:
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
                on_cell_clicked=_create_map_table_click_handler_internal(parent),
            )
            layout.addWidget(map_table, 1)

    else:  # weapons (table or statboard)
        if selected_weapon != "all":
            weapon_detail = next((r for r in weapon_rows if r.get("weapon") == selected_weapon), None)
            if weapon_detail:
                statboard = _build_statboard_section(
                    f"{selected_weapon.upper()} Statistics",
                    {
                        "Category": weapon_detail.get("category", "unknown"),
                        "Total Shots": int(weapon_detail.get("shots_fired") or 0),
                        "Shots Hit": int(weapon_detail.get("shots_hit") or 0),
                        "Accuracy": _fmt_pct(weapon_detail.get("accuracy") or 0.0),
                        "Kills": int(weapon_detail.get("kills") or 0),
                        "Headshot %": _fmt_pct(weapon_detail.get("headshot_pct") or 0.0),
                        "Total Damage": int(weapon_detail.get("damage") or 0),
                        "Rounds Active": int(weapon_detail.get("rounds_with_weapon") or 0),
                    },
                )
                layout.addWidget(statboard)
            else:
                hint = QLabel("Selected weapon is not available for this player/category.")
                hint.setStyleSheet("font-size: 12px; color: #5B7A72;")
                layout.addWidget(hint)
        else:
            filtered_weapon_rows = weapon_rows if selected_category == "all" else [w for w in weapon_rows if w.get("category") == selected_category]
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
                    for r in filtered_weapon_rows
                ],
                on_cell_clicked=_create_weapon_table_click_handler_internal(parent),
            )
            layout.addWidget(weapon_table, 1)
