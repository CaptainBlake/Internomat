"""
Builders and handlers for the Stat Tracker Insight Selection section.

This module encapsulates all logic related to the filter row, content area,
and event handlers for the insight/comparison view in the Stat Tracker tab.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import core.stats.stattracker as stattracker


def _normalize_category(category):
    value = str(category or "").strip().lower()
    if value.endswith("s") and len(value) > 3:
        value = value[:-1]
    return value or "unknown"


def _category_display_label(category):
    value = _normalize_category(category)
    if value == "all":
        return "All Categories"
    if value == "smg":
        return "SMGs"
    if value in {"rifle", "pistol", "heavy", "utility", "melee"}:
        return f"{value.title()}s"
    return value.title()


def _category_matches(left, right):
    return _normalize_category(left) == _normalize_category(right)


def _filter_weapons_by_category(weapon_rows, selected_category):
    rows = list(weapon_rows or [])
    if str(selected_category or "all") == "all":
        return sorted(rows, key=lambda w: int(w.get("shots_fired") or 0), reverse=True)

    filtered = [
        w for w in rows
        if _category_matches(w.get("category"), selected_category)
    ]

    # Guard against stale or non-normalized category labels.
    if not filtered and rows:
        filtered = rows

    return sorted(filtered, key=lambda w: int(w.get("shots_fired") or 0), reverse=True)


# ---------------------------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------------------------

def _on_main_view_changed(parent, combo):
    parent._stattracker_main_view = str(combo.currentData() or "weapons")
    parent._stattracker_selected_map = "all"
    parent._stattracker_selected_weapon = "all"
    if parent._stattracker_main_view not in {"movement", "weapons"}:
        parent._stattracker_timeline_scale = "match"
    if parent._stattracker_main_view in ("maps", "movement"):
        # Maps default to timeline mode for consistency with current UX direction.
        parent._stattracker_timeline = True
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


def _on_season_single_changed(parent, combo):
    value = combo.currentData()
    if value is None:
        parent._stattracker_selected_seasons = None
    else:
        parent._stattracker_selected_seasons = [int(value)]
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_season_multi_changed(parent):
    season_combo = getattr(parent, "_stattracker_season_combo", None)
    if season_combo is None or not hasattr(season_combo, "checked_data"):
        parent._stattracker_selected_seasons = None
    else:
        checked = [int(s) for s in (season_combo.checked_data() or [])]
        all_known = [int(s) for s in stattracker.get_season_options()]
        parent._stattracker_selected_seasons = None if (not checked or set(checked) == set(all_known)) else checked
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_weapon_selected_changed(parent, combo):
    parent._stattracker_selected_weapon = str(combo.currentData() or "all")
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_timeline_toggled(parent, checked):
    parent._stattracker_timeline = checked
    # Reset timeline state so mode switches always rebuild from active single selections.
    parent._stattracker_selected_timeline_items = []
    parent._stattracker_selected_plot_metrics = []
    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_timeline_multi_toggled(parent, checked):
    parent._stattracker_timeline_multi = bool(checked)

    # Preserve current selections when switching between single and multi mode.
    if checked:
        item_combo = getattr(parent, "_stattracker_timeline_combo", None)
        if isinstance(item_combo, QComboBox):
            selected_item = str(item_combo.currentData() or "").strip()
            if selected_item and selected_item != "all":
                parent._stattracker_selected_timeline_items = [selected_item]
            elif not getattr(parent, "_stattracker_selected_timeline_items", None):
                parent._stattracker_selected_timeline_items = []

        metric_combo = getattr(parent, "_stattracker_metric_combo", None)
        if isinstance(metric_combo, QComboBox):
            selected_metric = str(metric_combo.currentData() or "").strip()
            if selected_metric:
                parent._stattracker_selected_plot_metrics = [selected_metric]

        compare_combo = getattr(parent, "_stattracker_compare_combo", None)
        if isinstance(compare_combo, QComboBox):
            selected_compare_sid = str(compare_combo.currentData() or "").strip()
            parent._stattracker_compare_players = [selected_compare_sid] if selected_compare_sid else []
    else:
        item_combo = getattr(parent, "_stattracker_timeline_combo", None)
        if item_combo is not None and hasattr(item_combo, "checked_data"):
            selected_items = list(item_combo.checked_data() or [])
            parent._stattracker_selected_timeline_items = selected_items

        metric_combo = getattr(parent, "_stattracker_metric_combo", None)
        if metric_combo is not None and hasattr(metric_combo, "checked_data"):
            selected_metrics = list(metric_combo.checked_data() or [])
            parent._stattracker_selected_plot_metrics = selected_metrics

        compare_combo = getattr(parent, "_stattracker_compare_combo", None)
        if compare_combo is not None and hasattr(compare_combo, "checked_data"):
            selected_compare_sids = list(compare_combo.checked_data() or [])
            parent._stattracker_compare_players = selected_compare_sids
            parent._stattracker_compare_player = selected_compare_sids[0] if selected_compare_sids else ""

    from .stattracker_tab import refresh_stattracker
    refresh_stattracker(parent)


def _on_timeline_item_single_changed(parent, combo):
    value = str(combo.currentData() or "").strip()
    if value and value != "all":
        parent._stattracker_selected_timeline_items = [value]
    else:
        parent._stattracker_selected_timeline_items = []
    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_timeline_metric_single_changed(parent, combo):
    value = str(combo.currentData() or "").strip()
    parent._stattracker_selected_plot_metrics = [value] if value else []
    if value:
        parent._stattracker_plot_metric = value
    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_timeline_selection_changed(parent):
    """Re-render the plot when any multi-select combo changes."""
    item_combo = getattr(parent, "_stattracker_timeline_combo", None)
    if item_combo is not None:
        if hasattr(item_combo, "checked_data"):
            parent._stattracker_selected_timeline_items = list(item_combo.checked_data() or [])
        else:
            selected_item = str(item_combo.currentData() or "").strip()
            if selected_item and selected_item != "all":
                parent._stattracker_selected_timeline_items = [selected_item]
            else:
                parent._stattracker_selected_timeline_items = []

    metric_combo = getattr(parent, "_stattracker_metric_combo", None)
    if metric_combo is not None:
        if hasattr(metric_combo, "checked_data"):
            parent._stattracker_selected_plot_metrics = list(metric_combo.checked_data() or [])
        else:
            selected_metric = str(metric_combo.currentData() or "").strip()
            parent._stattracker_selected_plot_metrics = [selected_metric] if selected_metric else []

    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_chart_mode_changed(parent, combo):
    parent._stattracker_chart_mode = str(combo.currentData() or "line")
    _on_timeline_selection_changed(parent)


def _on_compare_player_changed(parent, combo):
    selected = str(combo.currentData() or "")
    parent._stattracker_compare_player = selected
    parent._stattracker_compare_players = [selected] if selected else []
    _on_timeline_selection_changed(parent)


def _on_compare_players_multi_changed(parent):
    compare_combo = getattr(parent, "_stattracker_compare_combo", None)
    if compare_combo is not None and hasattr(compare_combo, "checked_data"):
        selected = list(compare_combo.checked_data() or [])
    else:
        selected = []

    parent._stattracker_compare_players = selected
    parent._stattracker_compare_player = selected[0] if selected else ""
    _on_timeline_selection_changed(parent)


def _on_group_mode_changed(parent, combo):
    parent._stattracker_group_mode = str(combo.currentData() or "weapon")
    _on_timeline_selection_changed(parent)


def _on_timeline_scale_changed(parent, combo):
    selected = str(combo.currentData() or "match")
    main_view = str(getattr(parent, "_stattracker_main_view", "weapons") or "weapons")
    if main_view not in {"movement", "weapons"} and selected != "match":
        selected = "match"
    if selected == "tick":
        # No raw tick persistence in DB; keep option visible but inactive.
        selected = "round"

    parent._stattracker_timeline_scale = selected
    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_timeline_window_mode_changed(parent, combo):
    mode = str(combo.currentData() or "all")
    parent._stattracker_timeline_window_mode = mode

    # UX default: match-window is most useful at round granularity.
    # Users can still switch back to "match" scale manually.
    main_view = str(getattr(parent, "_stattracker_main_view", "weapons") or "weapons")
    if mode == "match" and main_view in {"movement", "weapons"}:
        parent._stattracker_timeline_scale = "round"

    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_timeline_match_filter_changed(parent, combo):
    parent._stattracker_timeline_match_filter = str(combo.currentData() or "")
    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


def _on_timeline_range_changed(parent, combo_from, combo_to):
    parent._stattracker_timeline_from_index = int(combo_from.currentData() or 0)
    parent._stattracker_timeline_to_index = int(combo_to.currentData() or 0)
    from .stattracker_tab import _refresh_plot_only
    _refresh_plot_only(parent)


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

    # --- Grouped control rows (inspired by analytics tools like Grafana/Superset) ---
    controls_card = QFrame()
    controls_card.setStyleSheet(
        "QFrame {"
        "background: rgba(255, 255, 255, 0.78);"
        "border: 1px solid #D5E0EA;"
        "border-radius: 10px;"
        "}"
        "QFrame QComboBox {"
        "background: #F2F6FA;"
        "border: 1px solid #1C1C1C;"
        "border-radius: 6px;"
        "padding: 2px 22px 2px 8px;"
        "color: #21443C;"
        "min-height: 22px;"
        "}"
        "QFrame QComboBox::drop-down {"
        "border: none;"
        "width: 18px;"
        "}"
        "QFrame QComboBox QAbstractItemView {"
        "background: #FFFFFF;"
        "border: 1px solid #1C1C1C;"
        "selection-background-color: #DBE5EE;"
        "selection-color: #21443C;"
        "}"
    )
    controls_layout = QVBoxLayout(controls_card)
    controls_layout.setContentsMargins(10, 8, 10, 8)
    controls_layout.setSpacing(6)

    insight_row = QHBoxLayout()
    insight_row.setSpacing(10)
    advanced_row = QHBoxLayout()
    advanced_row.setSpacing(10)
    has_advanced_controls = False

    # [1] View toggle: Weapons / Maps
    view_combo = QComboBox()
    view_combo.addItem("Weapons", "weapons")
    view_combo.addItem("Maps", "maps")
    view_combo.addItem("Movement", "movement")
    view_combo.addItem("Players", "players")
    idx = view_combo.findData(main_view)
    if idx < 0:
        idx = 0
        main_view = "weapons"
        parent._stattracker_main_view = main_view
    view_combo.setCurrentIndex(idx)
    view_combo.currentIndexChanged.connect(lambda _i: _on_main_view_changed(parent, view_combo))
    insight_row.addWidget(QLabel("View:"))
    insight_row.addWidget(view_combo)

    # [2] Category filter (weapons only, both modes)
    if main_view == "weapons":
        category_combo = QComboBox()
        categories = stattracker.get_player_weapon_categories(
            selected_sid,
            seasons=getattr(parent, "_stattracker_selected_seasons", None),
        ) if selected_sid else ["all"]
        for category in categories:
            label = _category_display_label(category)
            category_combo.addItem(label, category)
        cidx = category_combo.findData(selected_category)
        if cidx < 0:
            cidx = 0
        category_combo.setCurrentIndex(cidx)
        category_combo.currentIndexChanged.connect(lambda _i: _on_weapon_category_changed(parent, category_combo))
        insight_row.addWidget(QLabel("Category:"))
        insight_row.addWidget(category_combo)

    # [3] Item selector – single-select QComboBox (table) or multi-select _CheckableCombo (timeline)
    selected_weapon = str(getattr(parent, "_stattracker_selected_weapon", "all") or "all")
    selected_map = str(getattr(parent, "_stattracker_selected_map", "all") or "all")
    stored_timeline_items = list(getattr(parent, "_stattracker_selected_timeline_items", []) or [])
    timeline_multi = bool(getattr(parent, "_stattracker_timeline_multi", False))

    season_options = [int(s) for s in stattracker.get_season_options()]
    selected_seasons = getattr(parent, "_stattracker_selected_seasons", None)
    if is_timeline and timeline_multi:
        season_multi = _CheckableCombo(label_plural="Seasons")
        season_multi.setMinimumWidth(160)
        for sid in season_options:
            checked = True if selected_seasons is None else (sid in selected_seasons)
            season_multi.add_checkable_item(f"Season {sid}", data=sid, checked=checked)
        season_multi._update_display_text()
        season_multi._model.dataChanged.connect(lambda *_: _on_season_multi_changed(parent))
        parent._stattracker_season_combo = season_multi
        insight_row.addWidget(QLabel("Seasons:"))
        insight_row.addWidget(season_multi)
    else:
        season_single = QComboBox()
        season_single.setMinimumWidth(160)
        season_single.addItem("ALL Seasons", None)
        for sid in season_options:
            season_single.addItem(f"Season {sid}", sid)
        if selected_seasons and len(selected_seasons) == 1:
            idx_season = season_single.findData(int(selected_seasons[0]))
            if idx_season >= 0:
                season_single.setCurrentIndex(idx_season)
        else:
            season_single.setCurrentIndex(0)
        season_single.currentIndexChanged.connect(lambda _i: _on_season_single_changed(parent, season_single))
        parent._stattracker_season_combo = season_single
        insight_row.addWidget(QLabel("Season:"))
        insight_row.addWidget(season_single)

    if is_timeline:
        if main_view == "players":
            parent._stattracker_timeline_combo = None
        elif timeline_multi:
            item_label = "Maps" if main_view in ("maps", "movement") else "Weapons"
            item_multi = _CheckableCombo(label_plural=item_label)
            item_multi.setMinimumWidth(200)
            if main_view in ("maps", "movement"):
                for mr in (map_rows or []):
                    name = str(mr.get("map_name", "?"))
                    if stored_timeline_items:
                        checked = name in stored_timeline_items
                    else:
                        checked = True if selected_map == "all" else (name == selected_map)
                    item_multi.add_checkable_item(name, data=name, checked=checked)
            else:
                filtered = _filter_weapons_by_category(weapon_rows, selected_category)
                for wr in filtered:
                    name = str(wr.get("weapon", "?"))
                    if stored_timeline_items:
                        checked = name in stored_timeline_items
                    else:
                        checked = True if selected_weapon == "all" else (name == selected_weapon)
                    item_multi.add_checkable_item(name, data=name, checked=checked)
            item_multi._update_display_text()
            item_multi._model.dataChanged.connect(lambda *_: _on_timeline_selection_changed(parent))
            parent._stattracker_timeline_combo = item_multi
            insight_row.addWidget(QLabel("Items:"))
            insight_row.addWidget(item_multi)
        else:
            item_single = QComboBox()
            item_single.setMinimumWidth(200)
            item_single.addItem("All", "all")
            if main_view in ("maps", "movement"):
                for mr in (map_rows or []):
                    name = str(mr.get("map_name", "?"))
                    item_single.addItem(name, name)
                preferred = stored_timeline_items[0] if stored_timeline_items else selected_map
            elif main_view == "players":
                preferred = "all"
            else:
                filtered = _filter_weapons_by_category(weapon_rows, selected_category)
                for wr in filtered:
                    name = str(wr.get("weapon", "?"))
                    item_single.addItem(name, name)
                preferred = stored_timeline_items[0] if stored_timeline_items else selected_weapon

            idx_item = item_single.findData(preferred if preferred else "all")
            if idx_item < 0:
                idx_item = 0
            item_single.setCurrentIndex(idx_item)
            item_single.currentIndexChanged.connect(lambda _i: _on_timeline_item_single_changed(parent, item_single))
            parent._stattracker_timeline_combo = item_single
            insight_row.addWidget(QLabel("Item:"))
            insight_row.addWidget(item_single)
    else:
        parent._stattracker_timeline_combo = None
        if main_view == "weapons":
            weapon_combo = QComboBox()
            weapon_combo.addItem("All Weapons", "all")
            filtered_weapons = _filter_weapons_by_category(weapon_rows, selected_category)
            for wr in filtered_weapons:
                weapon_combo.addItem(wr.get("weapon", "unknown"), wr.get("weapon", "unknown"))
            widx = weapon_combo.findData(selected_weapon)
            if widx < 0:
                widx = 0
            weapon_combo.setCurrentIndex(widx)
            weapon_combo.currentIndexChanged.connect(lambda _i: _on_weapon_selected_changed(parent, weapon_combo))
            insight_row.addWidget(QLabel("Weapon:"))
            insight_row.addWidget(weapon_combo)
            parent._stattracker_weapon_combo = weapon_combo
        elif main_view in {"maps", "movement"}:
            map_combo = QComboBox()
            map_combo.addItem("All Maps", "all")
            for mr in map_rows:
                map_combo.addItem(mr.get("map_name", "unknown"), mr.get("map_name", "unknown"))
            midx = map_combo.findData(selected_map)
            if midx < 0:
                midx = 0
            map_combo.setCurrentIndex(midx)
            map_combo.currentIndexChanged.connect(lambda _i: _on_map_selected_changed(parent, map_combo))
            insight_row.addWidget(QLabel("Map:"))
            insight_row.addWidget(map_combo)
            parent._stattracker_map_combo = map_combo
        else:
            parent._stattracker_map_combo = None
            parent._stattracker_weapon_combo = None

    # [4] Metric selector (timeline only) – multi-select _CheckableCombo
    if is_timeline:
        if main_view == "players":
            opts = stattracker.get_players_plot_metric_options()
            default_metric = "elo"
        elif main_view == "maps":
            opts = stattracker.get_map_plot_metric_options()
            default_metric = "kd_ratio"
        elif main_view == "movement":
            opts = stattracker.get_movement_plot_metric_options()
            default_metric = "avg_speed_m_s"
        else:
            opts = stattracker.get_plot_metric_options()
            default_metric = "accuracy"
        current_metric = str(getattr(parent, "_stattracker_plot_metric", default_metric) or default_metric)
        stored_metrics = list(getattr(parent, "_stattracker_selected_plot_metrics", []) or [])
        insight_row.addWidget(QLabel("Metric:"))
        if timeline_multi:
            metric_multi = _CheckableCombo(label_plural="Metrics")
            metric_multi.setMinimumWidth(160)
            for opt in opts:
                checked = (opt["key"] in stored_metrics) if stored_metrics else (opt["key"] == current_metric)
                metric_multi.add_checkable_item(opt["label"], data=opt["key"], checked=checked)
            metric_multi._update_display_text()
            metric_multi._model.dataChanged.connect(lambda *_: _on_timeline_selection_changed(parent))
            parent._stattracker_metric_combo = metric_multi
            insight_row.addWidget(metric_multi)
        else:
            metric_single = QComboBox()
            metric_single.setMinimumWidth(160)
            for opt in opts:
                metric_single.addItem(opt["label"], opt["key"])
            idx_metric = metric_single.findData(stored_metrics[0] if stored_metrics else current_metric)
            if idx_metric < 0:
                idx_metric = 0
            metric_single.setCurrentIndex(idx_metric)
            metric_single.currentIndexChanged.connect(lambda _i: _on_timeline_metric_single_changed(parent, metric_single))
            parent._stattracker_metric_combo = metric_single
            insight_row.addWidget(metric_single)

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
        advanced_row.addWidget(QLabel("Display:"))
        advanced_row.addWidget(chart_mode_combo)
        has_advanced_controls = True

        scale_combo = QComboBox()
        scale_combo.setMinimumWidth(130)
        scale_combo.addItem("Match", "match")
        scale_combo.addItem("Round", "round")
        scale_combo.addItem("Tick", "tick")
        scale_value = str(getattr(parent, "_stattracker_timeline_scale", "match") or "match")
        if main_view not in {"movement", "weapons"} and scale_value != "match":
            scale_value = "match"
            parent._stattracker_timeline_scale = "match"
        scale_idx = scale_combo.findData(scale_value)
        if scale_idx < 0:
            scale_idx = 0
        scale_combo.setCurrentIndex(scale_idx)

        model = scale_combo.model()
        round_idx = scale_combo.findData("round")
        tick_idx = scale_combo.findData("tick")
        if round_idx >= 0:
            model.item(round_idx).setEnabled(main_view in {"movement", "weapons"})
        if tick_idx >= 0:
            model.item(tick_idx).setEnabled(False)

        scale_combo.currentIndexChanged.connect(lambda _i: _on_timeline_scale_changed(parent, scale_combo))
        supports_scale = main_view in {"movement", "weapons"}
        scale_label = QLabel("Scale:")
        scale_label.setVisible(supports_scale)
        scale_combo.setVisible(supports_scale)
        advanced_row.addWidget(scale_label)
        advanced_row.addWidget(scale_combo)

        window_combo = QComboBox()
        window_combo.setMinimumWidth(120)
        window_combo.addItem("All Data", "all")
        window_combo.addItem("Match", "match")
        window_combo.addItem("Custom Span", "range")
        window_mode = str(getattr(parent, "_stattracker_timeline_window_mode", "all") or "all")
        window_idx = window_combo.findData(window_mode)
        if window_idx < 0:
            window_idx = 0
            parent._stattracker_timeline_window_mode = "all"
        window_combo.setCurrentIndex(window_idx)
        window_combo.currentIndexChanged.connect(lambda _i: _on_timeline_window_mode_changed(parent, window_combo))
        range_mode_label = QLabel("Window:")
        advanced_row.addWidget(range_mode_label)
        advanced_row.addWidget(window_combo)

        # Match selector for window-mode = "match".
        match_combo = QComboBox()
        match_combo.setMinimumWidth(160)
        match_combo.addItem("All Matches", "")
        match_options = list(getattr(parent, "_stattracker_timeline_match_options", []) or [])
        for match_id, label in match_options:
            sid = str(match_id or "").strip()
            if not sid:
                continue
            display = str(label or sid)
            match_combo.addItem(display, sid)

        selected_match = str(getattr(parent, "_stattracker_timeline_match_filter", "") or "")
        match_idx = match_combo.findData(selected_match)
        if match_idx < 0:
            match_idx = 0
            parent._stattracker_timeline_match_filter = ""
        match_combo.setCurrentIndex(match_idx)
        match_combo.currentIndexChanged.connect(lambda _i: _on_timeline_match_filter_changed(parent, match_combo))
        match_label = QLabel("Match:")
        show_match_filter = window_mode == "match"
        match_label.setVisible(show_match_filter)
        match_combo.setVisible(show_match_filter)
        advanced_row.addWidget(match_label)
        advanced_row.addWidget(match_combo)

        labels = list(getattr(parent, "_stattracker_timeline_axis_labels", []) or [])
        combo_from = QComboBox()
        combo_to = QComboBox()
        combo_from.setMinimumWidth(120)
        combo_to.setMinimumWidth(120)
        if not labels:
            combo_from.addItem("-", 0)
            combo_to.addItem("-", 0)
        else:
            for idx_lbl, lbl in enumerate(labels):
                short = str(lbl).replace("\n", " | ")
                combo_from.addItem(short, idx_lbl)
                combo_to.addItem(short, idx_lbl)

        from_idx = int(getattr(parent, "_stattracker_timeline_from_index", 0) or 0)
        to_default = max(0, len(labels) - 1)
        to_idx = int(getattr(parent, "_stattracker_timeline_to_index", to_default) or to_default)
        from_idx = max(0, min(combo_from.count() - 1, from_idx)) if combo_from.count() else 0
        to_idx = max(0, min(combo_to.count() - 1, to_idx)) if combo_to.count() else 0
        combo_from.setCurrentIndex(from_idx)
        combo_to.setCurrentIndex(to_idx)

        combo_from.currentIndexChanged.connect(lambda _i: _on_timeline_range_changed(parent, combo_from, combo_to))
        combo_to.currentIndexChanged.connect(lambda _i: _on_timeline_range_changed(parent, combo_from, combo_to))
        show_range_bounds = window_mode == "range"
        combo_from.setEnabled(show_range_bounds)
        combo_to.setEnabled(show_range_bounds)
        from_label = QLabel("From:")
        to_label = QLabel("To:")
        from_label.setVisible(show_range_bounds)
        combo_from.setVisible(show_range_bounds)
        to_label.setVisible(show_range_bounds)
        combo_to.setVisible(show_range_bounds)
        advanced_row.addWidget(from_label)
        advanced_row.addWidget(combo_from)
        advanced_row.addWidget(to_label)
        advanced_row.addWidget(combo_to)

        parent._stattracker_range_from_combo = combo_from
        parent._stattracker_range_to_combo = combo_to
        parent._stattracker_range_window_combo = window_combo
        parent._stattracker_range_match_combo = match_combo
        parent._stattracker_range_from_label = from_label
        parent._stattracker_range_to_label = to_label
        parent._stattracker_range_window_label = range_mode_label
        parent._stattracker_range_match_label = match_label

        if main_view == "weapons":
            group_combo = QComboBox()
            group_combo.addItem("Weapons", "weapon")
            group_combo.addItem("Categories", "category")
            group_mode = str(getattr(parent, "_stattracker_group_mode", "weapon") or "weapon")
            group_idx = group_combo.findData(group_mode)
            if group_idx < 0:
                group_idx = 0
                parent._stattracker_group_mode = "weapon"
            group_combo.setCurrentIndex(group_idx)
            group_combo.currentIndexChanged.connect(lambda _i: _on_group_mode_changed(parent, group_combo))
            advanced_row.addWidget(QLabel("Group by:"))
            advanced_row.addWidget(group_combo)

        compare_combo = None
        player_options = getattr(parent, "_stattracker_player_options", []) or []
        has_compare_candidates = False
        compare_sids_stored = list(getattr(parent, "_stattracker_compare_players", []) or [])
        legacy_compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
        if not compare_sids_stored and legacy_compare_sid:
            compare_sids_stored = [legacy_compare_sid]

        if timeline_multi:
            compare_combo = _CheckableCombo(label_plural="Players")
            compare_combo.setMinimumWidth(160)
        else:
            compare_combo = QComboBox()
            compare_combo.setMinimumWidth(160)
            compare_combo.addItem("none", "")

        for opt in player_options:
            sid_opt = str(opt.get("steamid64") or "")
            if sid_opt and sid_opt != str(selected_sid or ""):
                has_compare_candidates = True
                if timeline_multi:
                    compare_combo.add_checkable_item(
                        str(opt.get("player_name") or sid_opt),
                        data=sid_opt,
                        checked=sid_opt in compare_sids_stored,
                    )
                else:
                    compare_combo.addItem(str(opt.get("player_name") or sid_opt), sid_opt)

        if timeline_multi:
            compare_combo._update_display_text()
            compare_combo._model.dataChanged.connect(lambda *_: _on_compare_players_multi_changed(parent))
            checked_now = list(compare_combo.checked_data() or [])
            parent._stattracker_compare_players = checked_now
            parent._stattracker_compare_player = checked_now[0] if checked_now else ""
        else:
            compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
            compare_idx = compare_combo.findData(compare_sid)
            if compare_idx < 0:
                compare_idx = 0
                parent._stattracker_compare_player = ""
                parent._stattracker_compare_players = []
            compare_combo.setCurrentIndex(compare_idx)
            compare_combo.currentIndexChanged.connect(lambda _i: _on_compare_player_changed(parent, compare_combo))

        parent._stattracker_compare_combo = compare_combo
        if has_compare_candidates:
            advanced_row.addWidget(QLabel("Compare:"))
            advanced_row.addWidget(compare_combo)
    else:
        parent._stattracker_metric_combo = None
        parent._stattracker_compare_combo = None
        parent._stattracker_range_match_combo = None
        parent._stattracker_range_match_label = None

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
        advanced_row.addWidget(best_badge)
        advanced_row.addWidget(worst_badge)
        has_advanced_controls = True

    # [6] Timeline toggle (always visible, right-aligned)
    insight_row.addStretch(1)
    advanced_row.addStretch(1)
    if is_timeline:
        multi_cb = QCheckBox("Multi-select")
        multi_cb.setChecked(timeline_multi)
        multi_cb.setStyleSheet("font-size: 11px; font-weight: 700;")
        multi_cb.toggled.connect(lambda checked: _on_timeline_multi_toggled(parent, checked))
        advanced_row.addWidget(multi_cb)
        has_advanced_controls = True

    table_cb = QCheckBox("Table View")
    table_cb.setChecked(not is_timeline)
    table_cb.setStyleSheet("font-size: 11px; font-weight: 700;")
    table_cb.toggled.connect(lambda checked: _on_timeline_toggled(parent, not checked))
    if has_advanced_controls:
        advanced_row.addWidget(table_cb)
    else:
        insight_row.addWidget(table_cb)

    controls_layout.addLayout(insight_row)
    if has_advanced_controls:
        controls_layout.addLayout(advanced_row)
    layout.addWidget(controls_card)
    layout.addSpacing(8)

    # --- Content title ---
    if is_timeline:
        if main_view == "maps":
            main_title_text = "Map Performance Timeline"
        elif main_view == "movement":
            main_title_text = "Movement Timeline"
        elif main_view == "players":
            main_title_text = "Player Timeline"
        else:
            cat_label = "All" if selected_category == "all" else selected_category.title()
            main_title_text = f"{cat_label} Weapon Timeline"
    elif main_view == "maps":
        main_title_text = f"Map Details: {selected_map}" if selected_map != "all" else "All Maps"
    elif main_view == "movement":
        main_title_text = f"Movement on {selected_map}" if selected_map != "all" else "Movement Across Maps"
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

    elif main_view == "movement":
        selected_map_local = str(getattr(parent, "_stattracker_selected_map", "all") or "all")
        map_filter = None if selected_map_local == "all" else [selected_map_local]
        selected_seasons = getattr(parent, "_stattracker_selected_seasons", None)
        metric_series = {
            "avg_speed_m_s": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="avg_speed_m_s", seasons=selected_seasons),
            "max_speed_units_s": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="max_speed_units_s", seasons=selected_seasons),
            "total_distance_m": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="total_distance_m", seasons=selected_seasons),
            "alive_seconds": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="alive_seconds", seasons=selected_seasons),
            "strafe_ratio": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="strafe_ratio", seasons=selected_seasons),
            "stationary_ratio": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="stationary_ratio", seasons=selected_seasons),
            "sprint_ratio": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="sprint_ratio", seasons=selected_seasons),
            "strafe_distance_m": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="strafe_distance_m", seasons=selected_seasons),
            "camp_time_s": stattracker.get_movement_match_series(selected_sid, maps=map_filter, metric="camp_time_s", seasons=selected_seasons),
        }

        labels = list((metric_series.get("avg_speed_m_s") or {}).get("x_labels") or [])

        def _vals(metric_key):
            return list(((metric_series.get(metric_key) or {}).get("series") or {}).get("Movement") or [])

        speed_vals = _vals("avg_speed_m_s")
        max_vals = _vals("max_speed_units_s")
        dist_vals = _vals("total_distance_m")
        alive_vals = _vals("alive_seconds")
        strafe_ratio_vals = _vals("strafe_ratio")
        stationary_ratio_vals = _vals("stationary_ratio")
        sprint_ratio_vals = _vals("sprint_ratio")
        strafe_dist_vals = _vals("strafe_distance_m")
        camp_time_vals = _vals("camp_time_s")

        movement_rows = []
        for idx, label in enumerate(labels):
            movement_rows.append([
                label,
                "-" if idx >= len(speed_vals) or speed_vals[idx] is None else f"{float(speed_vals[idx]):.2f}",
                "-" if idx >= len(max_vals) or max_vals[idx] is None else f"{float(max_vals[idx]):.1f}",
                "-" if idx >= len(dist_vals) or dist_vals[idx] is None else f"{float(dist_vals[idx]):.1f}",
                "-" if idx >= len(alive_vals) or alive_vals[idx] is None else f"{float(alive_vals[idx]):.1f}",
                "-" if idx >= len(strafe_ratio_vals) or strafe_ratio_vals[idx] is None else f"{float(strafe_ratio_vals[idx]):.1f}%",
                "-" if idx >= len(stationary_ratio_vals) or stationary_ratio_vals[idx] is None else f"{float(stationary_ratio_vals[idx]):.1f}%",
                "-" if idx >= len(sprint_ratio_vals) or sprint_ratio_vals[idx] is None else f"{float(sprint_ratio_vals[idx]):.1f}%",
                "-" if idx >= len(strafe_dist_vals) or strafe_dist_vals[idx] is None else f"{float(strafe_dist_vals[idx]):.1f}",
                "-" if idx >= len(camp_time_vals) or camp_time_vals[idx] is None else f"{float(camp_time_vals[idx]):.1f}",
            ])

        if movement_rows:
            movement_table = _build_table(
                [
                    "Map",
                    "Avg Speed (m/s)",
                    "Max Speed (u/s)",
                    "Distance (m)",
                    "Alive Time (s)",
                    "Strafe %",
                    "Stationary %",
                    "Sprint %",
                    "Strafe Dist (m)",
                    "Camp Time (s)",
                ],
                movement_rows,
            )
            layout.addWidget(movement_table, 1)
        else:
            hint = QLabel("No movement data available for the selected filters.")
            hint.setStyleSheet("font-size: 12px; color: #5B7A72;")
            layout.addWidget(hint)

    elif main_view == "players":
        selected_seasons = getattr(parent, "_stattracker_selected_seasons", None)
        combat = stattracker.get_player_combat_summary(selected_sid, seasons=selected_seasons)
        relationships = stattracker.get_player_kill_relationships(selected_sid, seasons=selected_seasons)

        # --- Combat KPI cards ---
        combat_statboard = _build_statboard_section(
            "Combat Summary",
            {
                "Flashes Thrown": int(combat.get("total_flashes_thrown") or 0),
                "Enemies Flashed": int(combat.get("total_enemies_flashed") or 0),
                "Entry Attempts": int(combat.get("total_entry_attempts") or 0),
                "Entry Wins": int(combat.get("total_entry_wins") or 0),
                "Entry Win %": _fmt_pct(combat.get("entry_success_pct") or 0.0),
                "Teamkills": int(combat.get("total_teamkills") or 0),
                "1v1 Clutches": f"{int(combat.get('total_clutch_1v1_wins') or 0)}/{int(combat.get('total_clutch_1v1') or 0)}",
                "1v2 Clutches": f"{int(combat.get('total_clutch_1v2_wins') or 0)}/{int(combat.get('total_clutch_1v2') or 0)}",
                "Aces": int(combat.get("total_aces") or 0),
                "4Ks": int(combat.get("total_4ks") or 0),
                "3Ks": int(combat.get("total_3ks") or 0),
                "HS%": _fmt_pct(combat.get("hs_pct") or 0.0),
            },
        )
        layout.addWidget(combat_statboard)

        # --- Kill relationship highlights ---
        fav = relationships.get("favourite_target")
        nem = relationships.get("arch_nemesis")
        if fav or nem:
            rel_cards = {}
            if fav:
                rel_cards["Favourite Target"] = f"{fav['opponent_name']}  ({fav['kills_dealt']} kills)"
                rel_cards["  HS Dealt"] = str(fav.get("hs_dealt") or 0)
            if nem:
                rel_cards["Arch-Nemesis"] = f"{nem['opponent_name']}  (died {nem['kills_received']}x)"
                rel_cards["  HS Received"] = str(nem.get("hs_received") or 0)

            rel_statboard = _build_statboard_section("Kill Relationships", rel_cards)
            layout.addWidget(rel_statboard)

        # --- Full kill relationships table ---
        rel_rows = relationships.get("rows") or []
        if rel_rows:
            rel_table = _build_table(
                ["Opponent", "Kills Dealt", "Kills Received", "Net", "HS Dealt", "HS Received", "TK Dealt", "TK Received"],
                [
                    [
                        r["opponent_name"],
                        r["kills_dealt"],
                        r["kills_received"],
                        r["net"],
                        r["hs_dealt"],
                        r["hs_received"],
                        r["teamkills_dealt"],
                        r["teamkills_received"],
                    ]
                    for r in rel_rows
                ],
            )
            layout.addWidget(rel_table, 1)

        # --- Compared player combat summary ---
        compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
        if compare_sid and compare_sid != selected_sid:
            compare_combat = stattracker.get_player_combat_summary(compare_sid, seasons=selected_seasons)
            if compare_combat:
                def _compare_name(sid):
                    for opt in (getattr(parent, "_stattracker_player_options", []) or []):
                        if str(opt.get("steamid64") or "") == str(sid or ""):
                            return str(opt.get("player_name") or sid)
                    return str(sid or "?")

                cmp_statboard = _build_statboard_section(
                    f"Combat Summary — {_compare_name(compare_sid)}",
                    {
                        "Flashes Thrown": int(compare_combat.get("total_flashes_thrown") or 0),
                        "Enemies Flashed": int(compare_combat.get("total_enemies_flashed") or 0),
                        "Entry Attempts": int(compare_combat.get("total_entry_attempts") or 0),
                        "Entry Wins": int(compare_combat.get("total_entry_wins") or 0),
                        "Entry Win %": _fmt_pct(compare_combat.get("entry_success_pct") or 0.0),
                        "Teamkills": int(compare_combat.get("total_teamkills") or 0),
                        "1v1 Clutches": f"{int(compare_combat.get('total_clutch_1v1_wins') or 0)}/{int(compare_combat.get('total_clutch_1v1') or 0)}",
                        "1v2 Clutches": f"{int(compare_combat.get('total_clutch_1v2_wins') or 0)}/{int(compare_combat.get('total_clutch_1v2') or 0)}",
                        "Aces": int(compare_combat.get("total_aces") or 0),
                        "4Ks": int(compare_combat.get("total_4ks") or 0),
                        "3Ks": int(compare_combat.get("total_3ks") or 0),
                        "HS%": _fmt_pct(compare_combat.get("hs_pct") or 0.0),
                    },
                )
                layout.addWidget(cmp_statboard)

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
            filtered_weapon_rows = _filter_weapons_by_category(weapon_rows, selected_category)
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
