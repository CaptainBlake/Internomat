from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QSizePolicy,
    QWidget,
)

import math

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import core.stats.stattracker as stattracker
import services.logger as logger
from . import stattracker_insight_builder


# ---------------------------------------------------------------------------
# CheckableComboBox – a QComboBox whose items have checkboxes
# ---------------------------------------------------------------------------

class _CheckableCombo(QComboBox):
    """QComboBox with checkable items for multi-select."""

    def __init__(self, parent=None, label_plural=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._closing = False
        self._label_plural = label_plural  # e.g., "Weapons", "Maps", "Metrics"
        # Keep a dedicated display string so preview text is not overridden by current index.
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setFrame(False)
        self._display_text = "None selected"
        self.lineEdit().setText(self._display_text)
        self.lineEdit().installEventFilter(self)
        self.view().pressed.connect(self._on_item_pressed)

    # -- public API --

    def add_checkable_item(self, text, data=None, checked=True):
        item = QStandardItem(text)
        item.setData(data, Qt.ItemDataRole.UserRole)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._model.appendRow(item)

    def checked_data(self):
        result = []
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def set_all_checked(self, checked=True):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._model.rowCount()):
            self._model.item(i).setCheckState(state)

    # -- overrides --

    def _on_item_pressed(self, index):
        item = self._model.itemFromIndex(index)
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)
        self._update_display_text()

    def _update_display_text(self):
        checked = [self._model.item(i).text()
                    for i in range(self._model.rowCount())
                    if self._model.item(i).checkState() == Qt.CheckState.Checked]
        total = self._model.rowCount()
        
        if len(checked) == total and total > 0:
            # All items selected
            if self._label_plural:
                self._display_text = f"All {self._label_plural}"
            else:
                self._display_text = f"All ({total})"
        elif len(checked) == 1:
            # Exactly one item selected
            self._display_text = checked[0]
        elif len(checked) > 1:
            # Multiple items selected
            self._display_text = "Multiple selections"
        else:
            # None selected
            self._display_text = "None selected"

        self.lineEdit().setText(self._display_text)

    def showPopup(self):
        self._update_display_text()
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        self._update_display_text()

    def mousePressEvent(self, event):
        # Ensure the full widget surface opens the popup, not only the arrow.
        self.showPopup()
        event.accept()

    def eventFilter(self, obj, event):
        if obj == self.lineEdit() and event.type() == event.Type.MouseButtonPress:
            self.showPopup()
            return True
        return super().eventFilter(obj, event)


# ---------------------------------------------------------------------------
# Plot colours for series lines
# ---------------------------------------------------------------------------
_PLOT_COLORS = [
    "#2F6FB3", "#E05252", "#3DAA6D", "#E9963E", "#9B59B6",
    "#1ABC9C", "#E67E22", "#34495E", "#F1C40F", "#7F8C8D",
]


def _build_plot_widget(plot_data, height=300, display_mode="line"):
    """Build a QWidget containing [legend sidebar | matplotlib canvas].

    plot_data may contain a flat ``series`` dict (legacy single-metric) or
    a ``multi_series`` list of ``{metric_label, series}`` dicts when multiple
    metrics are selected.
    """
    # Normalise into a list of (metric_label, {name: [values]})
    multi = plot_data.get("multi_series")
    if multi:
        groups = [(g["metric_label"], g["series"]) for g in multi]
    else:
        groups = [(plot_data.get("metric_label") or "Value",
                   plot_data.get("series") or {})]

    x_labels = plot_data.get("x_labels") or []
    all_empty = not x_labels or all(not s for _, s in groups)

    fig = Figure(figsize=(10, 3.2), dpi=100)
    fig.patch.set_facecolor("#F5F9FC")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#FAFCFE")

    _hover_bars: list = []   # (rect, x_label, series_label, value)
    _hover_lines: dict = {}  # x_idx -> {"x_label": str, "series": [(label, value)]}
    _hover_pie: list = []    # (wedge, label)
    legend_entries: list[tuple[str, str]] = []  # (color, label)
    color_idx = 0

    if all_empty:
        ax.text(0.5, 0.5, "No items selected",
                ha="center", va="center", fontsize=11, color="#7A9099",
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        x = list(range(len(x_labels)))

        plotted_series = []
        for metric_label, series in groups:
            prefix = f"{metric_label} · " if len(groups) > 1 else ""
            for name, values in series.items():
                color = _PLOT_COLORS[color_idx % len(_PLOT_COLORS)]
                color_idx += 1
                plotted_series.append((f"{prefix}{name}", values, color))

        if display_mode == "pie":
            pie_values = []
            pie_labels = []
            pie_colors = []
            for label, values, color in plotted_series:
                total = float(sum(v for v in values if v is not None))
                if total > 0:
                    pie_values.append(total)
                    pie_labels.append(label)
                    pie_colors.append(color)
                    legend_entries.append((color, label))

            if pie_values:
                pie_patches, *_ = ax.pie(
                    pie_values,
                    colors=pie_colors,
                    startangle=90,
                    wedgeprops={"linewidth": 0.7, "edgecolor": "white"},
                )
                _hover_pie.extend(zip(pie_patches, pie_labels))
                ax.set_aspect("equal")
            else:
                ax.text(0.5, 0.5, "No positive values for pie view",
                        ha="center", va="center", fontsize=11, color="#7A9099",
                        transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
        elif display_mode == "columns":
            n_series = max(1, len(plotted_series))
            width = min(0.8 / n_series, 0.32)
            start = -((n_series - 1) * width) / 2.0

            for idx, (label, values, color) in enumerate(plotted_series):
                xs = []
                ys = []
                x_idxs = []
                for i, v in enumerate(values):
                    if v is None:
                        continue
                    xs.append(i + start + idx * width)
                    ys.append(v)
                    x_idxs.append(i)
                if ys:
                    bc = ax.bar(xs, ys, width=width, color=color)
                    for rect, xi, yv in zip(bc, x_idxs, ys):
                        _hover_bars.append((
                            rect,
                            x_labels[xi] if 0 <= xi < len(x_labels) else "",
                            label, yv,
                        ))
                legend_entries.append((color, label))

            ax.set_xticks(x)
            ax.set_xticklabels(x_labels, rotation=35, ha="right", fontsize=8)
            if len(groups) == 1:
                ax.set_ylabel(groups[0][0], fontsize=9, color="#21443C")
            ax.tick_params(axis="y", labelsize=8)
            ax.grid(True, axis="y", alpha=0.3, linewidth=0.5)
        else:
            for label, values, color in plotted_series:
                xs = [i for i, v in enumerate(values) if v is not None]
                ys = [v for v in values if v is not None]
                if xs:
                    ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.8,
                            color=color, label=label)
                    for xi, yv in zip(xs, ys):
                        entry = _hover_lines.setdefault(
                            xi, {"x_label": x_labels[xi] if 0 <= xi < len(x_labels) else "", "series": []}
                        )
                        entry["series"].append((label, yv))
                legend_entries.append((color, label))

            ax.set_xticks(x)
            ax.set_xticklabels(x_labels, rotation=35, ha="right", fontsize=8)
            if len(groups) == 1:
                ax.set_ylabel(groups[0][0], fontsize=9, color="#21443C")
            ax.tick_params(axis="y", labelsize=8)
            ax.grid(True, alpha=0.3, linewidth=0.5)

    fig.tight_layout(pad=1.5)

    canvas = FigureCanvas(fig)
    canvas.setMinimumHeight(height)
    canvas.setMaximumHeight(height + 80)
    canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # Hover tooltip
    if _hover_bars or _hover_lines or _hover_pie:
        _annot = ax.annotate(
            "", xy=(0, 0), xytext=(8, 8),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFFDE7",
                      edgecolor="#BDBDBD", alpha=0.95),
            fontsize=8, zorder=10, visible=False,
        )
        if _hover_bars:
            def _on_motion(event, _a=_annot, _ax=ax, _c=canvas, _d=_hover_bars):
                if event.inaxes != _ax:
                    if _a.get_visible():
                        _a.set_visible(False)
                        _c.draw_idle()
                    return
                for rect, x_lbl, s_lbl, val in _d:
                    if rect.contains(event)[0]:
                        _a.xy = (rect.get_x() + rect.get_width() / 2, rect.get_height())
                        _a.set_text(f"{s_lbl}\n{x_lbl}:  {val:.4g}")
                        if not _a.get_visible():
                            _a.set_visible(True)
                        _c.draw_idle()
                        return
                if _a.get_visible():
                    _a.set_visible(False)
                    _c.draw_idle()
            canvas.mpl_connect("motion_notify_event", _on_motion)
        elif _hover_lines:
            def _on_motion(event, _a=_annot, _ax=ax, _c=canvas, _d=_hover_lines):
                if event.inaxes != _ax or event.xdata is None:
                    if _a.get_visible():
                        _a.set_visible(False)
                        _c.draw_idle()
                    return
                xi = int(round(event.xdata))
                if xi in _d:
                    entry = _d[xi]
                    tip = f"[{entry['x_label']}]\n" + "\n".join(
                        f"{sl}: {v:.4g}" for sl, v in entry["series"]
                    )
                    _a.set_text(tip)
                    _a.xy = (xi, event.ydata)
                    if not _a.get_visible():
                        _a.set_visible(True)
                    _c.draw_idle()
                else:
                    if _a.get_visible():
                        _a.set_visible(False)
                        _c.draw_idle()
            canvas.mpl_connect("motion_notify_event", _on_motion)
        elif _hover_pie:
            def _on_motion(event, _a=_annot, _ax=ax, _c=canvas, _d=_hover_pie):
                if event.inaxes != _ax:
                    if _a.get_visible():
                        _a.set_visible(False)
                        _c.draw_idle()
                    return
                for wedge, lbl in _d:
                    if wedge.contains(event)[0]:
                        theta = (wedge.theta1 + wedge.theta2) / 2.0
                        _a.xy = (
                            0.5 * math.cos(math.radians(theta)),
                            0.5 * math.sin(math.radians(theta)),
                        )
                        _a.set_text(lbl)
                        if not _a.get_visible():
                            _a.set_visible(True)
                        _c.draw_idle()
                        return
                if _a.get_visible():
                    _a.set_visible(False)
                    _c.draw_idle()
            canvas.mpl_connect("motion_notify_event", _on_motion)

    if not legend_entries:
        return canvas

    # Legend sidebar
    legend_frame = QFrame()
    legend_frame.setFixedWidth(140)
    legend_frame.setStyleSheet(
        "QFrame { background: rgba(255,255,255,0.96); border: 1px solid #D5E0EA; "
        "border-radius: 8px; }"
    )
    legend_layout = QVBoxLayout(legend_frame)
    legend_layout.setContentsMargins(6, 6, 6, 6)
    legend_layout.setSpacing(3)

    for color, label_text in legend_entries:
        row = QHBoxLayout()
        row.setSpacing(4)
        swatch = QLabel("●")
        swatch.setStyleSheet(f"color: {color}; font-size: 10px; border: none;")
        swatch.setFixedWidth(12)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 9px; color: #21443C; border: none;")
        lbl.setWordWrap(True)
        row.addWidget(swatch)
        row.addWidget(lbl, 1)
        legend_layout.addLayout(row)

    legend_layout.addStretch(1)

    wrapper = QWidget()
    wrapper_layout = QHBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.setSpacing(6)
    wrapper_layout.addWidget(legend_frame)
    wrapper_layout.addWidget(canvas, 1)
    wrapper.setMinimumHeight(height)
    wrapper.setMaximumHeight(height + 80)
    wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return wrapper


def _fmt_pct(value):
    return f"{float(value):.1f}%"


def _build_table(headers, rows, on_cell_clicked=None):
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

    if on_cell_clicked:
        table.cellClicked.connect(lambda row, col: on_cell_clicked(row, col, table, headers, rows))
        table.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

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
    if str(getattr(parent, "_stattracker_compare_player", "") or "") == parent._stattracker_selected_player:
        parent._stattracker_compare_player = ""
    refresh_stattracker(parent)


def _build_statboard_section(title, stats_dict):
    """Build a stat section panel with paired label/value rows (2 pairs per row)."""
    frame = QFrame()
    frame.setStyleSheet(
        """
        QFrame {
            background: rgba(255, 255, 255, 0.96);
            border: 1px solid #D5E0EA;
            border-radius: 10px;
        }
        """
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #21443C;")
    title_label.setMaximumHeight(20)
    layout.addWidget(title_label)

    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(8)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(2, 1)
    grid.setColumnStretch(3, 1)

    for idx, (key, value) in enumerate(stats_dict.items()):
        row = idx // 2
        pair = idx % 2
        label_col = pair * 2
        value_col = label_col + 1

        key_label = QLabel(f"{key}:")
        key_label.setStyleSheet(
            "font-size: 11px; color: #6C8790; font-weight: 600; "
            "background: rgba(245, 249, 252, 0.55); border: 1px solid #E8EFF4; "
            "border-radius: 6px; padding: 5px 8px;"
        )
        val_label = QLabel(str(value))
        val_label.setStyleSheet(
            "font-size: 13px; color: #21443C; font-weight: 800; "
            "background: rgba(255, 255, 255, 0.98); border: 1px solid #DCE6EE; "
            "border-radius: 6px; padding: 5px 8px;"
        )

        grid.addWidget(key_label, row, label_col)
        grid.addWidget(val_label, row, value_col)

    layout.addLayout(grid)
    return frame


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _refresh_plot_only(parent):
    """Re-render only the plot canvas without rebuilding the full tab."""
    container = getattr(parent, "_stattracker_plot_container", None)
    if container is None:
        return

    layout = container.layout()
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.setParent(None)
            w.deleteLater()

    sid = str(getattr(parent, "_stattracker_selected_player", "") or "")
    main_view = str(getattr(parent, "_stattracker_main_view", "weapons") or "weapons")
    compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
    if compare_sid == sid:
        compare_sid = ""

    # Gather checked metrics
    metric_combo = getattr(parent, "_stattracker_metric_combo", None)
    if metric_combo and isinstance(metric_combo, _CheckableCombo):
        metrics = metric_combo.checked_data()
        parent._stattracker_selected_plot_metrics = list(metrics)
    else:
        metrics = list(getattr(parent, "_stattracker_selected_plot_metrics", []) or [])
        if not metrics:
            metrics = [str(getattr(parent, "_stattracker_plot_metric", "accuracy") or "accuracy")]

    # Gather checked items
    item_combo = getattr(parent, "_stattracker_timeline_combo", None)
    checked_items = item_combo.checked_data() if item_combo else None
    if item_combo:
        parent._stattracker_selected_timeline_items = list(checked_items or [])
    else:
        checked_items = list(getattr(parent, "_stattracker_selected_timeline_items", []) or [])

    # Important: keep [] as "show none". Only None means "no filter / all".
    selected_items_filter = checked_items if checked_items is not None else None

    def _player_label(target_sid):
        for opt in (getattr(parent, "_stattracker_player_options", []) or []):
            if str(opt.get("steamid64") or "") == str(target_sid or ""):
                return str(opt.get("player_name") or target_sid)
        return str(target_sid or "Player")

    def _build_plot_data_for(target_sid):
        if main_view == "maps":
            if len(metrics) == 1:
                return stattracker.get_map_match_series(
                    target_sid, maps=selected_items_filter, metric=metrics[0],
                )
            first = stattracker.get_map_match_series(target_sid, maps=selected_items_filter, metric=metrics[0])
            multi = [{"metric_label": first["metric_label"], "series": first["series"]}]
            for m in metrics[1:]:
                r = stattracker.get_map_match_series(target_sid, maps=selected_items_filter, metric=m)
                multi.append({"metric_label": r["metric_label"], "series": r["series"]})
            return {"x_labels": first["x_labels"], "multi_series": multi}

        selected_map = str(getattr(parent, "_stattracker_selected_map", "all") or "all")
        map_name = selected_map if selected_map != "all" else None
        if len(metrics) == 1:
            return stattracker.get_weapon_match_series(
                target_sid, weapons=selected_items_filter, metric=metrics[0], map_name=map_name,
            )
        first = stattracker.get_weapon_match_series(target_sid, weapons=selected_items_filter, metric=metrics[0], map_name=map_name)
        multi = [{"metric_label": first["metric_label"], "series": first["series"]}]
        for m in metrics[1:]:
            r = stattracker.get_weapon_match_series(target_sid, weapons=selected_items_filter, metric=m, map_name=map_name)
            multi.append({"metric_label": r["metric_label"], "series": r["series"]})
        return {"x_labels": first["x_labels"], "multi_series": multi}

    def _prefixed(data, prefix):
        if data.get("multi_series"):
            merged_groups = []
            for group in (data.get("multi_series") or []):
                prefixed_series = {
                    f"{prefix} · {name}": values
                    for name, values in (group.get("series") or {}).items()
                }
                merged_groups.append({
                    "metric_label": group.get("metric_label") or "Value",
                    "series": prefixed_series,
                })
            return {
                "x_labels": list(data.get("x_labels") or []),
                "multi_series": merged_groups,
            }

        return {
            "x_labels": list(data.get("x_labels") or []),
            "metric_label": data.get("metric_label") or "Value",
            "series": {
                f"{prefix} · {name}": values
                for name, values in (data.get("series") or {}).items()
            },
        }

    plot_data = _prefixed(_build_plot_data_for(sid), _player_label(sid))

    if compare_sid:
        compare_data = _prefixed(_build_plot_data_for(compare_sid), _player_label(compare_sid))
        if plot_data.get("multi_series"):
            merged = {
                g.get("metric_label") or "Value": dict(g.get("series") or {})
                for g in (plot_data.get("multi_series") or [])
            }
            for group in (compare_data.get("multi_series") or []):
                label = group.get("metric_label") or "Value"
                merged.setdefault(label, {})
                merged[label].update(group.get("series") or {})

            plot_data = {
                "x_labels": list(plot_data.get("x_labels") or compare_data.get("x_labels") or []),
                "multi_series": [
                    {"metric_label": label, "series": series}
                    for label, series in merged.items()
                ],
            }
        else:
            merged_series = dict(plot_data.get("series") or {})
            merged_series.update(compare_data.get("series") or {})
            plot_data = {
                "x_labels": list(plot_data.get("x_labels") or compare_data.get("x_labels") or []),
                "metric_label": plot_data.get("metric_label") or compare_data.get("metric_label") or "Value",
                "series": merged_series,
            }

    display_mode = str(getattr(parent, "_stattracker_chart_mode", "line") or "line")
    widget = _build_plot_widget(plot_data, display_mode=display_mode)
    layout.addWidget(widget)



# ---------------------------------------------------------------------------
# Tab init + refresh
# ---------------------------------------------------------------------------

def build_stattracker_tab(parent):
    logger.log("[UI] Build Stat Tracker tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(16, 8, 16, 12)
    layout.setSpacing(8)

    title = QLabel("Stat Tracker")
    title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    title.setStyleSheet("font-size: 16px; font-weight: 900; color: #21443C;")
    layout.addWidget(title)

    parent._stattracker_cache_dirty = True
    parent._stattracker_overview = None
    parent._stattracker_player_options = []
    parent._stattracker_selected_player = ""
    parent._stattracker_main_view = "weapons"
    parent._stattracker_weapon_category = "all"
    parent._stattracker_selected_map = "all"
    parent._stattracker_selected_weapon = "all"
    parent._stattracker_timeline = False
    parent._stattracker_plot_metric = "accuracy"
    parent._stattracker_chart_mode = "line"
    parent._stattracker_compare_player = ""
    parent._stattracker_selected_timeline_items = []
    parent._stattracker_selected_plot_metrics = []
    parent._stattracker_plot_container = None
    parent._stattracker_timeline_combo = None
    parent._stattracker_on_update = lambda: on_stattracker_data_updated(parent)
    parent._stattracker_refresh = lambda: refresh_stattracker(parent)
    refresh_stattracker(parent)


def refresh_stattracker(parent):
    logger.log("[UI] Refresh Stat Tracker tab", level="DEBUG")

    layout = parent.layout()
    if layout is None:
        return

    while layout.count() > 1:
        item = layout.takeAt(1)
        _clear_layout_item(item)

    cache_dirty = getattr(parent, "_stattracker_cache_dirty", True)
    if cache_dirty:
        parent._stattracker_cache_dirty = False

    player_options = getattr(parent, "_stattracker_player_options", None)
    if cache_dirty or not isinstance(player_options, list) or not player_options:
        player_options = stattracker.get_player_options()
        parent._stattracker_player_options = player_options

    # --- Player Selection Panel ---
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
        label = option.get("player_name") or sid
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

    panel_row = QHBoxLayout()
    panel_row.setContentsMargins(0, 0, 0, 0)
    panel_row.setSpacing(0)
    panel_row.addWidget(panel)
    panel_row.addStretch(1)
    layout.addLayout(panel_row)

    if not selected_sid:
        hint = QLabel("No player data available yet. Parse demos to populate Stat Tracker.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 16px;")
        layout.addWidget(hint, 1)
        return

    selected_category = str(getattr(parent, "_stattracker_weapon_category", "all") or "all")

    # Global stats must always represent the full player profile, independent of insight filters.
    dashboard = stattracker.get_player_dashboard(
        selected_sid,
        min_weapon_shots=1,
        weapon_category="all",
    )
    kpis = dashboard.get("kpis") or {}

    # --- Global Stats ---
    global_title = QLabel("Global Stats")
    global_title.setStyleSheet("font-size: 13px; font-weight: 900; color: #21443C;")
    layout.addWidget(global_title)

    global_table = _build_table(
        [
            "Maps Played", "Win Rate", "K/D", "ADR",
            "Avg Kills", "Avg Deaths", "Avg Assists", "HS%",
            "Avg KAST", "Avg Impact", "Avg Rating", "Avg Performance",
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

    # --- Insight Selection ---
    selected_category = str(getattr(parent, "_stattracker_weapon_category", "all") or "all")
    stattracker_insight_builder.build_insight_section(parent, layout, dashboard, selected_sid, selected_category)


def on_stattracker_data_updated(parent):
    logger.log("[UI] Stat Tracker data update triggered", level="DEBUG")
    parent._stattracker_cache_dirty = True
    refresh_stattracker(parent)
