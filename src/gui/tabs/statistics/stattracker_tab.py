from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QSizePolicy,
    QWidget,
)

import math

try:
    import seaborn as sns
except Exception:  # pragma: no cover - optional runtime dependency guard
    sns = None
    _SEABORN_IMPORT_ERROR = "unknown"
else:
    _SEABORN_IMPORT_ERROR = ""

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except Exception as exc:  # pragma: no cover - optional runtime dependency guard
    FigureCanvas = None
    Figure = None
    _MPL_IMPORT_ERROR = str(exc)
else:
    _MPL_IMPORT_ERROR = ""

import core.stats.stattracker as stattracker
import services.logger as logger
from . import stattracker_insight_builder
from . import stattracker_playercard


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

_SEABORN_THEME_APPLIED = False


def _ensure_seaborn_theme():
    """Apply a single shared Seaborn/Matplotlib style for stattracker charts."""
    global _SEABORN_THEME_APPLIED
    if _SEABORN_THEME_APPLIED or sns is None:
        return

    sns.set_theme(
        style="whitegrid",
        context="notebook",
        rc={
            "figure.facecolor": "#F5F9FC",
            "axes.facecolor": "#FAFCFE",
            "axes.edgecolor": "#D7E2EB",
            "axes.labelcolor": "#21443C",
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "grid.color": "#DCE6EE",
            "grid.alpha": 0.62,
            "grid.linewidth": 0.65,
            "xtick.color": "#40615B",
            "ytick.color": "#40615B",
            "font.size": 9,
            "legend.frameon": False,
        },
    )
    _SEABORN_THEME_APPLIED = True


def _build_plot_widget(plot_data, height=340, display_mode="line"):
    """Build a QWidget containing [legend sidebar | Seaborn/Matplotlib plot].

    plot_data may contain a flat ``series`` dict (legacy single-metric) or
    a ``multi_series`` list of ``{metric_label, series}`` dicts when multiple
    metrics are selected.
    """
    if sns is None or FigureCanvas is None or Figure is None:
        details = []
        if sns is None:
            details.append("seaborn import failed")
        if FigureCanvas is None or Figure is None:
            reason = _MPL_IMPORT_ERROR or "matplotlib Qt backend import failed"
            details.append(reason)
        detail_text = "; ".join(details) if details else "plot backend unavailable"
        missing = QLabel(
            "Seaborn/Matplotlib plot backend unavailable. "
            f"Reason: {detail_text}"
        )
        missing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        missing.setStyleSheet(
            "font-size: 12px; color: #7A9099; background: rgba(255,255,255,0.96);"
            "border: 1px solid #D5E0EA; border-radius: 8px; padding: 12px;"
        )
        return missing

    _ensure_seaborn_theme()

    # Normalise into a list of (metric_label, {name: [values]})
    multi = plot_data.get("multi_series")
    if multi:
        groups = [(g["metric_label"], g["series"]) for g in multi]
    else:
        groups = [(plot_data.get("metric_label") or "Value",
                   plot_data.get("series") or {})]

    x_labels = plot_data.get("x_labels") or []
    axis_labels = plot_data.get("axis_labels") or x_labels

    def _compute_tick_positions(total_count, max_labels=24):
        if total_count <= 0:
            return []
        if total_count <= max_labels:
            return list(range(total_count))

        step = int(math.ceil(float(total_count) / float(max_labels)))
        ticks = list(range(0, total_count, step))
        if ticks[-1] != (total_count - 1):
            ticks.append(total_count - 1)
        return ticks
    all_empty = not x_labels or all(not s for _, s in groups)

    fig = Figure(figsize=(10, 3.8), dpi=100)
    fig.patch.set_facecolor("#F5F9FC")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#FAFCFE")
    for spine in ax.spines.values():
        spine.set_color("#D7E2EB")
        spine.set_linewidth(0.9)

    _hover_bars = []
    _hover_lines = {}
    _hover_pie = []
    legend_entries: list[tuple[str, str]] = []  # (color, label)
    series_count = sum(len(series) for _, series in groups)
    palette = [
        c if isinstance(c, str) else "#2F6FB3"
        for c in sns.color_palette("deep", max(series_count, len(_PLOT_COLORS))).as_hex()
    ]
    color_idx = 0

    info_label = None

    if all_empty:
        ax.text(
            0.5,
            0.5,
            "No items selected",
            ha="center",
            va="center",
            fontsize=11,
            color="#7A9099",
            transform=ax.transAxes,
        )
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        x = list(range(len(x_labels)))
        tick_positions = _compute_tick_positions(len(x_labels), max_labels=24)
        tick_labels = [axis_labels[i] if i < len(axis_labels) else str(i + 1) for i in tick_positions]

        plotted_series = []
        for metric_label, series in groups:
            prefix = f"{metric_label} · " if len(groups) > 1 else ""
            for name, values in series.items():
                color = palette[color_idx % len(palette)]
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
                wedges, *_ = ax.pie(
                    pie_values,
                    colors=pie_colors,
                    startangle=90,
                    wedgeprops={"linewidth": 0.8, "edgecolor": "white"},
                )
                _hover_pie.extend(zip(wedges, pie_labels))
                ax.set_aspect("equal")
            else:
                info_label = QLabel("No positive values for pie view")
                info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                info_label.setStyleSheet("font-size: 11px; color: #7A9099;")
        elif display_mode == "columns":
            n_series = max(1, len(plotted_series))
            width = min(0.8 / n_series, 0.32)
            start = -((n_series - 1) * width) / 2.0

            for idx, (label, values, color) in enumerate(plotted_series):
                xs = []
                ys = []
                for i, v in enumerate(values):
                    if v is None:
                        continue
                    xs.append(i + start + idx * width)
                    ys.append(v)
                if ys:
                    bars = ax.bar(xs, ys, width=width, color=color, alpha=0.92)
                    x_idxs = [i for i, v in enumerate(values) if v is not None]
                    for rect, xi, yv in zip(bars, x_idxs, ys):
                        _hover_bars.append((
                            rect,
                            x_labels[xi] if 0 <= xi < len(x_labels) else "",
                            label,
                            float(yv),
                        ))
                for i, v in enumerate(values):
                    if v is None:
                        continue
                    entry = _hover_lines.setdefault(
                        i,
                        {"x_label": x_labels[i] if 0 <= i < len(x_labels) else "", "series": []},
                    )
                    entry["series"].append((label, float(v)))
                legend_entries.append((color, label))

            ax.set_xticks(tick_positions)
            ax.set_xticklabels(tick_labels, rotation=30, ha="right", fontsize=8)
            if len(groups) == 1:
                ax.set_ylabel(groups[0][0], fontsize=9, color="#21443C")
            ax.margins(y=0.18)
            ax.tick_params(axis="y", labelsize=8)
            ax.grid(True, axis="y", alpha=0.42, linewidth=0.65)
        else:
            for label, values, color in plotted_series:
                xs = [i for i, v in enumerate(values) if v is not None]
                ys = [v for v in values if v is not None]
                if xs:
                    ax.plot(
                        xs,
                        ys,
                        marker="o",
                        markersize=4,
                        linewidth=1.9,
                        color=color,
                    )
                    for xi, yv in zip(xs, ys):
                        entry = _hover_lines.setdefault(
                            xi, {"x_label": x_labels[xi] if 0 <= xi < len(x_labels) else "", "series": []}
                        )
                        entry["series"].append((label, float(yv)))
                legend_entries.append((color, label))

            ax.set_xticks(tick_positions)
            ax.set_xticklabels(tick_labels, rotation=30, ha="right", fontsize=8)
            if len(groups) == 1:
                ax.set_ylabel(groups[0][0], fontsize=9, color="#21443C")
            ax.margins(y=0.18)
            ax.tick_params(axis="y", labelsize=8)
            ax.grid(True, axis="y", alpha=0.42, linewidth=0.65)

    fig.tight_layout(pad=1.4)

    canvas = FigureCanvas(fig)
    canvas.setMinimumHeight(height)
    canvas.setMaximumHeight(height + 80)
    canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    if _hover_bars or _hover_lines or _hover_pie:
        annot = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(8, -26),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFFDE7", edgecolor="#BDBDBD", alpha=0.95),
            fontsize=8,
            zorder=10,
            visible=False,
            annotation_clip=False,
        )

        if _hover_bars:
            def _on_motion(event):
                if event.inaxes != ax:
                    if annot.get_visible():
                        annot.set_visible(False)
                        canvas.draw_idle()
                    return
                for rect, x_lbl, s_lbl, val in _hover_bars:
                    if rect.contains(event)[0]:
                        annot.xy = (rect.get_x() + rect.get_width() / 2, rect.get_height())
                        annot.set_text(f"{s_lbl}\n{x_lbl}:  {val:.4g}")
                        if not annot.get_visible():
                            annot.set_visible(True)
                        canvas.draw_idle()
                        return
                if annot.get_visible():
                    annot.set_visible(False)
                    canvas.draw_idle()
            canvas.mpl_connect("motion_notify_event", _on_motion)
        elif _hover_lines:
            def _on_motion(event):
                if event.inaxes != ax or event.xdata is None:
                    if annot.get_visible():
                        annot.set_visible(False)
                        canvas.draw_idle()
                    return
                xi = int(round(event.xdata))
                if xi in _hover_lines:
                    entry = _hover_lines[xi]
                    tip = f"[{entry['x_label']}]\n" + "\n".join(
                        f"{sl}: {v:.4g}" for sl, v in entry["series"]
                    )
                    annot.set_text(tip)
                    annot.xy = (xi, event.ydata)
                    if not annot.get_visible():
                        annot.set_visible(True)
                    canvas.draw_idle()
                else:
                    if annot.get_visible():
                        annot.set_visible(False)
                        canvas.draw_idle()
            canvas.mpl_connect("motion_notify_event", _on_motion)
        elif _hover_pie:
            def _on_motion(event):
                if event.inaxes != ax:
                    if annot.get_visible():
                        annot.set_visible(False)
                        canvas.draw_idle()
                    return
                for wedge, lbl in _hover_pie:
                    if wedge.contains(event)[0]:
                        theta = (wedge.theta1 + wedge.theta2) / 2.0
                        annot.xy = (
                            0.5 * math.cos(math.radians(theta)),
                            0.5 * math.sin(math.radians(theta)),
                        )
                        annot.set_text(lbl)
                        if not annot.get_visible():
                            annot.set_visible(True)
                        canvas.draw_idle()
                        return
                if annot.get_visible():
                    annot.set_visible(False)
                    canvas.draw_idle()
            canvas.mpl_connect("motion_notify_event", _on_motion)

    if not legend_entries:
        if info_label is None:
            return canvas
        info_wrapper = QWidget()
        info_layout = QVBoxLayout(info_wrapper)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        info_layout.addWidget(info_label)
        info_layout.addWidget(canvas)
        info_wrapper.setMinimumHeight(height)
        info_wrapper.setMaximumHeight(height + 80)
        info_wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return info_wrapper

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
    chart_area = QWidget()
    chart_area_layout = QVBoxLayout(chart_area)
    chart_area_layout.setContentsMargins(0, 0, 0, 0)
    chart_area_layout.setSpacing(4)
    if info_label is not None:
        chart_area_layout.addWidget(info_label)
    chart_area_layout.addWidget(canvas, 1)
    wrapper_layout.addWidget(chart_area, 1)
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
    compare_players = [
        s for s in (getattr(parent, "_stattracker_compare_players", []) or [])
        if str(s or "") and str(s or "") != parent._stattracker_selected_player
    ]
    parent._stattracker_compare_players = compare_players
    if compare_players:
        parent._stattracker_compare_player = str(compare_players[0])
    refresh_stattracker(parent)


def _on_compare_changed_top(parent, combo):
    selected = str(combo.currentData() or "")
    parent._stattracker_compare_player = selected
    parent._stattracker_compare_players = [selected] if selected else []
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
    compare_sids = list(getattr(parent, "_stattracker_compare_players", []) or [])
    legacy_compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
    if not compare_sids and legacy_compare_sid:
        compare_sids = [legacy_compare_sid]
    compare_sids = [
        str(s or "") for s in compare_sids
        if str(s or "") and str(s or "") != sid
    ]
    deduped_compare_sids = []
    for s in compare_sids:
        if s not in deduped_compare_sids:
            deduped_compare_sids.append(s)
    compare_sids = deduped_compare_sids
    parent._stattracker_compare_players = list(compare_sids)
    parent._stattracker_compare_player = compare_sids[0] if compare_sids else ""

    # Gather checked metrics
    metric_combo = getattr(parent, "_stattracker_metric_combo", None)
    if metric_combo and isinstance(metric_combo, _CheckableCombo):
        metrics = metric_combo.checked_data()
        parent._stattracker_selected_plot_metrics = list(metrics)
    elif isinstance(metric_combo, QComboBox):
        selected_metric = str(metric_combo.currentData() or "").strip()
        metrics = [selected_metric] if selected_metric else []
        parent._stattracker_selected_plot_metrics = list(metrics)
    else:
        metrics = list(getattr(parent, "_stattracker_selected_plot_metrics", []) or [])
        if not metrics:
            metrics = [str(getattr(parent, "_stattracker_plot_metric", "accuracy") or "accuracy")]

    if not metrics:
        if main_view in {"maps", "players"}:
            fallback_metric = "kd_ratio"
        elif main_view == "movement":
            fallback_metric = "avg_speed_m_s"
        else:
            fallback_metric = "accuracy"
        metrics = [fallback_metric]
        parent._stattracker_selected_plot_metrics = list(metrics)
        parent._stattracker_plot_metric = fallback_metric

    # Gather checked items
    item_combo = getattr(parent, "_stattracker_timeline_combo", None)
    checked_items = None
    if item_combo and isinstance(item_combo, _CheckableCombo):
        checked_items = item_combo.checked_data()
        parent._stattracker_selected_timeline_items = list(checked_items or [])
    elif isinstance(item_combo, QComboBox):
        selected_item = str(item_combo.currentData() or "").strip()
        if selected_item == "all":
            checked_items = None
            parent._stattracker_selected_timeline_items = []
        elif selected_item:
            checked_items = [selected_item]
            parent._stattracker_selected_timeline_items = [selected_item]
        else:
            checked_items = None
            parent._stattracker_selected_timeline_items = []
    else:
        checked_items = list(getattr(parent, "_stattracker_selected_timeline_items", []) or [])

    # Important: keep [] as "show none". Only None means "no filter / all".
    selected_items_filter = checked_items if checked_items is not None else None
    timeline_scale = str(getattr(parent, "_stattracker_timeline_scale", "match") or "match")
    selected_seasons = getattr(parent, "_stattracker_selected_seasons", None)
    if main_view not in {"movement", "weapons"}:
        timeline_scale = "match"
        parent._stattracker_timeline_scale = "match"
    elif timeline_scale == "tick":
        # Tick-level raw timeline is not persisted yet; use round scale as closest granularity.
        timeline_scale = "round"
        parent._stattracker_timeline_scale = "round"

    def _normalize_category(category):
        value = str(category or "").strip().lower()
        if value.endswith("s") and len(value) > 3:
            value = value[:-1]
        return value or "unknown"

    def _category_matches(left, right):
        return _normalize_category(left) == _normalize_category(right)

    def _aggregate_map_series(series_dict, metric_key):
        """Collapse per-map lines into one logical player line for map view timelines."""
        if not isinstance(series_dict, dict) or not series_dict:
            return {}

        first_values = next(iter(series_dict.values())) or []
        length = len(first_values)
        aggregated = []

        ratio_metrics = {"kd_ratio", "adr"}

        for i in range(length):
            vals = []
            for values in series_dict.values():
                if i < len(values):
                    v = values[i]
                    if v is not None:
                        vals.append(float(v))

            if not vals:
                aggregated.append(None)
                continue

            if metric_key in ratio_metrics:
                aggregated.append(sum(vals) / len(vals))
            else:
                aggregated.append(sum(vals))

        return {"All Maps": aggregated}

    def _resolve_weapon_filter_for_player(target_sid):
        selected_category = str(getattr(parent, "_stattracker_weapon_category", "all") or "all")

        # Explicit empty selection means show nothing.
        if selected_items_filter == []:
            return []

        # Explicit item selection (single or multi) wins.
        if selected_items_filter is not None:
            return selected_items_filter

        # No explicit item selection: apply current category filter if not all.
        if selected_category != "all":
            dash = stattracker.get_player_dashboard(
                str(target_sid or ""),
                min_weapon_shots=1,
                weapon_category="all",
                seasons=selected_seasons,
            )
            rows = dash.get("weapon_rows") or []
            return [
                str(r.get("weapon") or "")
                for r in rows
                if str(r.get("weapon") or "").strip()
                and _category_matches(r.get("category"), selected_category)
            ]

        return None

    def _player_label(target_sid):
        for opt in (getattr(parent, "_stattracker_player_options", []) or []):
            if str(opt.get("steamid64") or "") == str(target_sid or ""):
                return str(opt.get("player_name") or target_sid)
        return str(target_sid or "Player")

    def _aggregate_weapon_series_by_category(series_dict, target_sid, metric_key):
        if not isinstance(series_dict, dict) or not series_dict:
            return {}

        dashboard = stattracker.get_player_dashboard(
            str(target_sid or ""),
            min_weapon_shots=1,
            weapon_category="all",
            seasons=selected_seasons,
        )
        weapon_rows = dashboard.get("weapon_rows") or []
        weapon_to_category = {
            str(r.get("weapon") or ""): str(r.get("category") or "unknown").title()
            for r in weapon_rows
            if str(r.get("weapon") or "").strip()
        }

        ratio_metrics = {"accuracy", "hs_pct"}
        aggregated = {}
        counts = {}

        for weapon_name, values in series_dict.items():
            category = weapon_to_category.get(str(weapon_name or ""), "Unknown")
            if category not in aggregated:
                aggregated[category] = [0.0] * len(values)
                counts[category] = [0] * len(values)

            for idx, value in enumerate(values):
                if value is None:
                    continue
                aggregated[category][idx] += float(value)
                counts[category][idx] += 1

        if metric_key in ratio_metrics:
            for category, values in aggregated.items():
                for idx, val in enumerate(values):
                    c = counts[category][idx]
                    values[idx] = (val / c) if c > 0 else None

        for category, values in aggregated.items():
            for idx, val in enumerate(values):
                if counts[category][idx] == 0:
                    values[idx] = None

        return aggregated

    def _build_plot_data_for(target_sid):
        if main_view == "maps":
            if len(metrics) == 1:
                data = stattracker.get_map_match_series(
                    target_sid, maps=selected_items_filter, metric=metrics[0], seasons=selected_seasons,
                )
                data["series"] = _aggregate_map_series(data.get("series") or {}, metrics[0])
                return data
            first = stattracker.get_map_match_series(target_sid, maps=selected_items_filter, metric=metrics[0], seasons=selected_seasons)
            multi = [{
                "metric_label": first["metric_label"],
                "series": _aggregate_map_series(first.get("series") or {}, metrics[0]),
            }]
            for m in metrics[1:]:
                r = stattracker.get_map_match_series(target_sid, maps=selected_items_filter, metric=m, seasons=selected_seasons)
                multi.append({
                    "metric_label": r["metric_label"],
                    "series": _aggregate_map_series(r.get("series") or {}, m),
                })
            return {"x_labels": first["x_labels"], "multi_series": multi}

        if main_view == "movement":
            fetch_fn = stattracker.get_movement_round_series if timeline_scale == "round" else stattracker.get_movement_match_series
            if len(metrics) == 1:
                return fetch_fn(
                    target_sid,
                    maps=selected_items_filter,
                    metric=metrics[0],
                    seasons=selected_seasons,
                )
            first = fetch_fn(
                target_sid,
                maps=selected_items_filter,
                metric=metrics[0],
                seasons=selected_seasons,
            )
            multi = [{"metric_label": first["metric_label"], "series": first["series"]}]
            for m in metrics[1:]:
                r = fetch_fn(
                    target_sid,
                    maps=selected_items_filter,
                    metric=m,
                    seasons=selected_seasons,
                )
                multi.append({"metric_label": r["metric_label"], "series": r["series"]})
            return {"x_labels": first["x_labels"], "match_keys": first.get("match_keys") or [], "multi_series": multi}

        if main_view == "players":
            season_param = None
            if selected_seasons and len(selected_seasons) == 1:
                season_param = int(selected_seasons[0])

            def _fetch_player_metric(sid, metric, season):
                if metric == "premier":
                    return stattracker.get_player_premier_history_series(sid)
                return stattracker.get_player_elo_history_series(sid, metric=metric, season=season)

            # Premier uses a different data source (Leetify match history) than
            # Elo metrics (local elo_history table), so their x-axes don't align.
            # When multiple metrics are selected, only combine elo-family metrics.
            # If premier is among them, show premier alone (first wins).
            has_premier = "premier" in metrics
            elo_metrics = [m for m in metrics if m != "premier"]

            if has_premier and not elo_metrics:
                return _fetch_player_metric(target_sid, "premier", season_param)

            if has_premier and elo_metrics:
                # Premier can't share x-axis with elo; show premier only
                return _fetch_player_metric(target_sid, "premier", season_param)

            if len(elo_metrics) == 1:
                return _fetch_player_metric(target_sid, elo_metrics[0], season_param)

            first = _fetch_player_metric(target_sid, elo_metrics[0], season_param)
            multi = [{"metric_label": first["metric_label"], "series": first["series"]}]
            for m in elo_metrics[1:]:
                r = _fetch_player_metric(target_sid, m, season_param)
                multi.append({"metric_label": r["metric_label"], "series": r["series"]})
            return {"x_labels": first["x_labels"], "match_keys": first.get("match_keys") or [], "multi_series": multi}

        selected_map = str(getattr(parent, "_stattracker_selected_map", "all") or "all")
        map_name = selected_map if selected_map != "all" else None
        weapon_filter = _resolve_weapon_filter_for_player(target_sid)
        group_mode = str(getattr(parent, "_stattracker_group_mode", "weapon") or "weapon")
        fetch_weapon_fn = stattracker.get_weapon_round_series if timeline_scale == "round" else stattracker.get_weapon_match_series
        if len(metrics) == 1:
            result = fetch_weapon_fn(
                target_sid, weapons=weapon_filter, metric=metrics[0], map_name=map_name, seasons=selected_seasons,
            )
            if group_mode == "category":
                result["series"] = _aggregate_weapon_series_by_category(
                    result.get("series") or {},
                    target_sid,
                    metrics[0],
                )
            return result
        first = fetch_weapon_fn(target_sid, weapons=weapon_filter, metric=metrics[0], map_name=map_name, seasons=selected_seasons)
        first_series = first["series"]
        if group_mode == "category":
            first_series = _aggregate_weapon_series_by_category(first_series, target_sid, metrics[0])
        multi = [{"metric_label": first["metric_label"], "series": first_series}]
        for m in metrics[1:]:
            r = fetch_weapon_fn(target_sid, weapons=weapon_filter, metric=m, map_name=map_name, seasons=selected_seasons)
            metric_series = r["series"]
            if group_mode == "category":
                metric_series = _aggregate_weapon_series_by_category(metric_series, target_sid, m)
            multi.append({"metric_label": r["metric_label"], "series": metric_series})
        return {"x_labels": first["x_labels"], "match_keys": first.get("match_keys") or [], "multi_series": multi}

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
                "match_keys": list(data.get("match_keys") or []),
                "multi_series": merged_groups,
            }

        return {
            "x_labels": list(data.get("x_labels") or []),
            "match_keys": list(data.get("match_keys") or []),
            "metric_label": data.get("metric_label") or "Value",
            "series": {
                f"{prefix} · {name}": values
                for name, values in (data.get("series") or {}).items()
            },
        }

    def _align_plot_data(plot_data_a, plot_data_b):
        keys_a = list(plot_data_a.get("match_keys") or [])
        keys_b = list(plot_data_b.get("match_keys") or [])
        labels_a = list(plot_data_a.get("x_labels") or [])
        labels_b = list(plot_data_b.get("x_labels") or [])

        if not keys_a and not keys_b:
            return plot_data_a, plot_data_b

        ordered_keys = []
        label_by_key = {}

        for i, key in enumerate(keys_a):
            if key not in label_by_key:
                label_by_key[key] = labels_a[i] if i < len(labels_a) else "?"
            if key not in ordered_keys:
                ordered_keys.append(key)

        for i, key in enumerate(keys_b):
            if key not in label_by_key:
                label_by_key[key] = labels_b[i] if i < len(labels_b) else "?"
            if key not in ordered_keys:
                ordered_keys.append(key)

        index_map = {k: idx for idx, k in enumerate(ordered_keys)}

        def _pad_values(values, source_keys):
            aligned = [None] * len(ordered_keys)
            for i, key in enumerate(source_keys):
                if i >= len(values):
                    continue
                target_idx = index_map.get(key)
                if target_idx is not None:
                    aligned[target_idx] = values[i]
            return aligned

        def _align_single(data):
            source_keys = list(data.get("match_keys") or [])
            if data.get("multi_series"):
                multi = []
                for group in (data.get("multi_series") or []):
                    series = {}
                    for name, values in (group.get("series") or {}).items():
                        series[name] = _pad_values(list(values or []), source_keys)
                    multi.append({
                        "metric_label": group.get("metric_label") or "Value",
                        "series": series,
                    })
                return {
                    "match_keys": ordered_keys,
                    "x_labels": [label_by_key.get(k, "?") for k in ordered_keys],
                    "multi_series": multi,
                }

            series = {}
            for name, values in (data.get("series") or {}).items():
                series[name] = _pad_values(list(values or []), source_keys)
            return {
                "match_keys": ordered_keys,
                "x_labels": [label_by_key.get(k, "?") for k in ordered_keys],
                "metric_label": data.get("metric_label") or "Value",
                "series": series,
            }

        return _align_single(plot_data_a), _align_single(plot_data_b)

    plot_data = _prefixed(_build_plot_data_for(sid), _player_label(sid))

    def _merge_plot_data(base_data, extra_data):
        aligned_base, aligned_extra = _align_plot_data(base_data, extra_data)

        if aligned_base.get("multi_series"):
            merged = {
                g.get("metric_label") or "Value": dict(g.get("series") or {})
                for g in (aligned_base.get("multi_series") or [])
            }
            for group in (aligned_extra.get("multi_series") or []):
                label = group.get("metric_label") or "Value"
                merged.setdefault(label, {})
                merged[label].update(group.get("series") or {})

            return {
                "x_labels": list(aligned_base.get("x_labels") or aligned_extra.get("x_labels") or []),
                "match_keys": list(aligned_base.get("match_keys") or aligned_extra.get("match_keys") or []),
                "multi_series": [
                    {"metric_label": label, "series": series}
                    for label, series in merged.items()
                ],
            }

        merged_series = dict(aligned_base.get("series") or {})
        merged_series.update(aligned_extra.get("series") or {})
        return {
            "x_labels": list(aligned_base.get("x_labels") or aligned_extra.get("x_labels") or []),
            "match_keys": list(aligned_base.get("match_keys") or aligned_extra.get("match_keys") or []),
            "metric_label": aligned_base.get("metric_label") or aligned_extra.get("metric_label") or "Value",
            "series": merged_series,
        }

    for compare_sid in compare_sids:
        compare_data = _prefixed(_build_plot_data_for(compare_sid), _player_label(compare_sid))
        plot_data = _merge_plot_data(plot_data, compare_data)

    def _slice_plot_data(data, start_idx, end_idx):
        x_labels = list(data.get("x_labels") or [])
        axis_labels = list(data.get("axis_labels") or [])
        if not x_labels:
            return data

        lo = max(0, min(len(x_labels) - 1, int(start_idx)))
        hi = max(0, min(len(x_labels) - 1, int(end_idx)))
        if lo > hi:
            lo, hi = hi, lo

        sliced = {
            "x_labels": x_labels[lo:hi + 1],
            "match_keys": list(data.get("match_keys") or [])[lo:hi + 1],
        }
        if axis_labels:
            sliced["axis_labels"] = axis_labels[lo:hi + 1]

        if data.get("multi_series"):
            multi = []
            for group in (data.get("multi_series") or []):
                series = {}
                for name, values in (group.get("series") or {}).items():
                    vals = list(values or [])
                    series[name] = vals[lo:hi + 1]
                multi.append({
                    "metric_label": group.get("metric_label") or "Value",
                    "series": series,
                })
            sliced["multi_series"] = multi
            return sliced

        sliced["metric_label"] = data.get("metric_label") or "Value"
        sliced["series"] = {
            name: list(values or [])[lo:hi + 1]
            for name, values in (data.get("series") or {}).items()
        }
        return sliced

    def _filter_plot_data_by_match_id(data, match_id):
        target = str(match_id or "").strip()
        if not target:
            return data

        match_keys = list(data.get("match_keys") or [])
        x_labels_local = list(data.get("x_labels") or [])
        axis_labels_local = list(data.get("axis_labels") or [])
        if not match_keys:
            return data

        keep_idx = [
            i for i, key in enumerate(match_keys)
            if str(key or "").split(":", 1)[0] == target
        ]
        if not keep_idx:
            return {
                "x_labels": [],
                "match_keys": [],
                "axis_labels": [],
                "multi_series": [] if data.get("multi_series") else None,
                "metric_label": data.get("metric_label") or "Value",
                "series": {} if not data.get("multi_series") else None,
            }

        filtered = {
            "x_labels": [x_labels_local[i] for i in keep_idx if i < len(x_labels_local)],
            "match_keys": [match_keys[i] for i in keep_idx],
        }
        if axis_labels_local:
            filtered["axis_labels"] = [axis_labels_local[i] for i in keep_idx if i < len(axis_labels_local)]

        if data.get("multi_series"):
            multi = []
            for group in (data.get("multi_series") or []):
                series = {}
                for name, values in (group.get("series") or {}).items():
                    vals = list(values or [])
                    series[name] = [vals[i] if i < len(vals) else None for i in keep_idx]
                multi.append({
                    "metric_label": group.get("metric_label") or "Value",
                    "series": series,
                })
            filtered["multi_series"] = multi
            return filtered

        filtered["metric_label"] = data.get("metric_label") or "Value"
        filtered_series = {}
        for name, values in (data.get("series") or {}).items():
            vals = list(values or [])
            filtered_series[name] = [vals[i] if i < len(vals) else None for i in keep_idx]
        filtered["series"] = filtered_series
        return filtered

    # Keep full, pre-window keys/options for match-window dropdown options.
    full_match_keys = list(plot_data.get("match_keys") or [])
    full_x_labels = list(plot_data.get("x_labels") or [])
    parent._stattracker_timeline_match_keys = full_match_keys

    match_options = []
    seen_match_ids = set()
    for idx_key, key in enumerate(full_match_keys):
        parts = str(key or "").split(":")
        if not parts:
            continue
        match_id = str(parts[0] or "").strip()
        if not match_id or match_id in seen_match_ids:
            continue
        seen_match_ids.add(match_id)

        raw_label = str(full_x_labels[idx_key] if idx_key < len(full_x_labels) else "").strip()
        line0 = raw_label.split("\n", 1)[0].strip() if raw_label else ""
        # Round labels often look like "de_map R03" -> keep only map name for selector.
        if " R" in line0:
            line0 = line0.rsplit(" R", 1)[0].strip()
        if not line0:
            line0 = "unknown"

        match_options.append((match_id, f"{match_id} - {line0}"))

    parent._stattracker_timeline_match_options = match_options

    labels = list(plot_data.get("x_labels") or [])

    parent._stattracker_timeline_axis_labels = labels
    if labels:
        from_idx = int(getattr(parent, "_stattracker_timeline_from_index", 0) or 0)
        to_idx = int(getattr(parent, "_stattracker_timeline_to_index", len(labels) - 1) or (len(labels) - 1))
        parent._stattracker_timeline_from_index = max(0, min(len(labels) - 1, from_idx))
        parent._stattracker_timeline_to_index = max(0, min(len(labels) - 1, to_idx))
    else:
        parent._stattracker_timeline_from_index = 0
        parent._stattracker_timeline_to_index = 0

    range_from_combo = getattr(parent, "_stattracker_range_from_combo", None)
    range_to_combo = getattr(parent, "_stattracker_range_to_combo", None)
    window_combo = getattr(parent, "_stattracker_range_window_combo", None)
    match_combo = getattr(parent, "_stattracker_range_match_combo", None)
    range_from_label = getattr(parent, "_stattracker_range_from_label", None)
    range_to_label = getattr(parent, "_stattracker_range_to_label", None)
    range_window_label = getattr(parent, "_stattracker_range_window_label", None)
    match_label = getattr(parent, "_stattracker_range_match_label", None)
    window_mode = str(getattr(parent, "_stattracker_timeline_window_mode", "all") or "all")
    match_filter = str(getattr(parent, "_stattracker_timeline_match_filter", "") or "")
    can_range = len(labels) > 1
    available_match_options = list(getattr(parent, "_stattracker_timeline_match_options", []) or [])
    can_match_filter = bool(available_match_options)

    if window_mode == "range" and not can_range:
        window_mode = "all"
        parent._stattracker_timeline_window_mode = "all"
    if window_mode == "match" and not can_match_filter:
        window_mode = "all"
        parent._stattracker_timeline_window_mode = "all"
        parent._stattracker_timeline_match_filter = ""

    def _sync_combo(combo, labels_local, selected_index):
        if not isinstance(combo, QComboBox):
            return
        combo.blockSignals(True)
        combo.clear()
        if not labels_local:
            combo.addItem("-", 0)
            combo.setCurrentIndex(0)
        else:
            for idx_lbl, label in enumerate(labels_local):
                combo.addItem(str(label).replace("\n", " | "), idx_lbl)
            idx_sel = max(0, min(len(labels_local) - 1, int(selected_index)))
            combo.setCurrentIndex(idx_sel)
        combo.blockSignals(False)

    _sync_combo(range_from_combo, labels, getattr(parent, "_stattracker_timeline_from_index", 0))
    _sync_combo(range_to_combo, labels, getattr(parent, "_stattracker_timeline_to_index", 0))

    if isinstance(match_combo, QComboBox):
        match_combo.blockSignals(True)
        match_combo.clear()
        match_combo.addItem("All Matches", "")
        for mid, label in available_match_options:
            match_combo.addItem(str(label or mid), str(mid or ""))
        idx_match = match_combo.findData(match_filter)
        if idx_match < 0:
            idx_match = 0
            parent._stattracker_timeline_match_filter = ""
        match_combo.setCurrentIndex(idx_match)
        match_combo.blockSignals(False)

    if isinstance(range_from_combo, QComboBox):
        range_from_combo.setEnabled(window_mode == "range" and bool(labels))
    if isinstance(range_to_combo, QComboBox):
        range_to_combo.setEnabled(window_mode == "range" and bool(labels))

    show_bounds = can_range and window_mode == "range"
    show_match = can_match_filter and window_mode == "match"
    if isinstance(range_from_combo, QComboBox):
        range_from_combo.setVisible(show_bounds)
    if isinstance(range_to_combo, QComboBox):
        range_to_combo.setVisible(show_bounds)
    if isinstance(range_from_label, QLabel):
        range_from_label.setVisible(show_bounds)
    if isinstance(range_to_label, QLabel):
        range_to_label.setVisible(show_bounds)
    if isinstance(window_combo, QComboBox):
        window_combo.setVisible(can_range)
    if isinstance(range_window_label, QLabel):
        range_window_label.setVisible(can_range or can_match_filter)
    if isinstance(match_combo, QComboBox):
        match_combo.setVisible(show_match)
        match_combo.setEnabled(show_match)
    if isinstance(match_label, QLabel):
        match_label.setVisible(show_match)

    if isinstance(window_combo, QComboBox):
        idx_mode = window_combo.findData(window_mode)
        if idx_mode >= 0 and window_combo.currentIndex() != idx_mode:
            window_combo.blockSignals(True)
            window_combo.setCurrentIndex(idx_mode)
            window_combo.blockSignals(False)

    if window_mode == "match" and match_filter:
        plot_data = _filter_plot_data_by_match_id(plot_data, match_filter)
    elif window_mode == "range" and labels:
        plot_data = _slice_plot_data(
            plot_data,
            getattr(parent, "_stattracker_timeline_from_index", 0),
            getattr(parent, "_stattracker_timeline_to_index", len(labels) - 1),
        )

    if timeline_scale == "round":
        round_axis_labels = []
        for idx_key, key in enumerate(list(plot_data.get("match_keys") or [])):
            parts = str(key or "").split(":")
            if len(parts) >= 3:
                try:
                    round_num = int(parts[2])
                    round_axis_labels.append(f"R{round_num}")
                    continue
                except Exception:
                    pass
            round_axis_labels.append(f"R{idx_key + 1}")
        if round_axis_labels:
            plot_data["axis_labels"] = round_axis_labels

    display_mode = str(getattr(parent, "_stattracker_chart_mode", "line") or "line")
    widget = _build_plot_widget(plot_data, display_mode=display_mode)
    layout.addWidget(widget)



# ---------------------------------------------------------------------------
# Tab init + refresh
# ---------------------------------------------------------------------------

def build_stattracker_tab(parent):
    logger.log("[UI] Build Stat Tracker tab", level="DEBUG")

    outer_layout = QVBoxLayout(parent)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    outer_layout.addWidget(scroll_area)

    scroll_content = QWidget()
    scroll_area.setWidget(scroll_content)

    layout = QVBoxLayout(scroll_content)
    layout.setContentsMargins(16, 8, 16, 12)
    layout.setSpacing(8)

    # Store scroll internals so refresh can find the inner layout
    parent._stattracker_scroll_content = scroll_content

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
    parent._stattracker_timeline = True
    parent._stattracker_timeline_multi = False
    parent._stattracker_group_mode = "weapon"
    parent._stattracker_plot_metric = "accuracy"
    parent._stattracker_chart_mode = "line"
    parent._stattracker_compare_player = ""
    parent._stattracker_compare_players = []
    parent._stattracker_player_category = "combat"
    parent._stattracker_selected_timeline_items = []
    parent._stattracker_selected_seasons = None
    parent._stattracker_selected_plot_metrics = []
    parent._stattracker_timeline_scale = "match"
    parent._stattracker_timeline_window_mode = "all"
    parent._stattracker_timeline_match_filter = ""
    parent._stattracker_timeline_from_index = 0
    parent._stattracker_timeline_to_index = 0
    parent._stattracker_timeline_axis_labels = []
    parent._stattracker_timeline_match_keys = []
    parent._stattracker_timeline_match_options = []
    parent._stattracker_range_from_combo = None
    parent._stattracker_range_to_combo = None
    parent._stattracker_range_window_combo = None
    parent._stattracker_range_match_combo = None
    parent._stattracker_range_from_label = None
    parent._stattracker_range_to_label = None
    parent._stattracker_range_window_label = None
    parent._stattracker_range_match_label = None
    parent._stattracker_plot_container = None
    parent._stattracker_timeline_combo = None
    parent._stattracker_season_combo = None
    parent._stattracker_compare_combo = None
    parent._stattracker_initial_focus_applied = False
    parent._stattracker_on_update = lambda: on_stattracker_data_updated(parent)
    parent._stattracker_refresh = lambda: refresh_stattracker(parent)
    refresh_stattracker(parent)


def refresh_stattracker(parent):
    logger.log("[UI] Refresh Stat Tracker tab", level="DEBUG")

    scroll_content = getattr(parent, "_stattracker_scroll_content", None)
    layout = scroll_content.layout() if scroll_content else parent.layout()
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

    # --- Compare-to picker ---
    compare_label = QLabel("Compare to:")
    compare_label.setStyleSheet("font-size: 11px; font-weight: 700; color: #6C8790;")
    player_row.addWidget(compare_label)

    compare_picker = QComboBox()
    compare_picker.setMinimumWidth(200)
    compare_picker.addItem("none", "")
    compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
    for option in player_options:
        opt_sid = str(option.get("steamid64") or "")
        if opt_sid and opt_sid != selected_sid:
            compare_picker.addItem(option.get("player_name") or opt_sid, opt_sid)
    cidx = compare_picker.findData(compare_sid)
    if cidx < 0:
        cidx = 0
        parent._stattracker_compare_player = ""
        parent._stattracker_compare_players = []
    compare_picker.setCurrentIndex(cidx)
    compare_picker.currentIndexChanged.connect(lambda _i: _on_compare_changed_top(parent, compare_picker))
    parent._stattracker_compare_combo = compare_picker
    player_row.addWidget(compare_picker)

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

    # Global stats must always represent the full player profile, independent of insight filters.
    dashboard = stattracker.get_player_dashboard(
        selected_sid,
        min_weapon_shots=1,
        weapon_category="all",
        seasons=getattr(parent, "_stattracker_selected_seasons", None),
    )

    # First open defaults: rifles category with one focused weapon to avoid clutter.
    if not bool(getattr(parent, "_stattracker_initial_focus_applied", False)):
        weapon_rows = list(dashboard.get("weapon_rows") or [])
        rifle_rows = [
            row for row in weapon_rows
            if str(row.get("category") or "").strip().lower() in {"rifle", "rifles"}
        ]
        if rifle_rows:
            rifle_names = [str(row.get("weapon") or "") for row in rifle_rows if str(row.get("weapon") or "").strip()]
            if "ak-47" in rifle_names:
                preferred_weapon = "ak-47"
            else:
                preferred_weapon = sorted(rifle_names, key=lambda w: w.lower())[0]

            parent._stattracker_weapon_category = "rifles"
            parent._stattracker_selected_weapon = preferred_weapon
            parent._stattracker_selected_timeline_items = [preferred_weapon]

        parent._stattracker_initial_focus_applied = True

    kpis = dashboard.get("kpis") or {}
    relationships = stattracker.get_player_kill_relationships(
        selected_sid,
        seasons=getattr(parent, "_stattracker_selected_seasons", None),
    )
    fav = relationships.get("favourite_target")
    nem = relationships.get("arch_nemesis")
    _practice_target = f"{fav['opponent_name']} ({fav['kills_dealt']}K)" if fav else "-"
    _nemesis = f"{nem['opponent_name']} ({nem['kills_received']}D)" if nem else "-"

    # --- Player Card (replaces Global Stats table) ---
    _player_name = selected_sid
    for _opt in player_options:
        if str(_opt.get("steamid64") or "") == selected_sid:
            _player_name = str(_opt.get("player_name") or selected_sid)
            break

    player_card = stattracker_playercard.build_player_card(
        player_name=_player_name,
        kpis=kpis,
        nemesis=_nemesis,
        practice_target=_practice_target,
    )
    layout.addWidget(player_card)

    # --- Compared player card ---
    compare_sid = str(getattr(parent, "_stattracker_compare_player", "") or "")
    if compare_sid and compare_sid != selected_sid:
        compare_dashboard = stattracker.get_player_dashboard(
            compare_sid,
            min_weapon_shots=1,
            weapon_category="all",
            seasons=getattr(parent, "_stattracker_selected_seasons", None),
        )
        compare_kpis = compare_dashboard.get("kpis") or {}

        def _compare_label(sid):
            for opt in player_options:
                if str(opt.get("steamid64") or "") == str(sid or ""):
                    return str(opt.get("player_name") or sid)
            return str(sid or "?")

        cmp_rel = stattracker.get_player_kill_relationships(
            compare_sid,
            seasons=getattr(parent, "_stattracker_selected_seasons", None),
        )
        cmp_fav = cmp_rel.get("favourite_target")
        cmp_nem = cmp_rel.get("arch_nemesis")
        _cmp_practice = f"{cmp_fav['opponent_name']} ({cmp_fav['kills_dealt']}K)" if cmp_fav else "-"
        _cmp_nemesis = f"{cmp_nem['opponent_name']} ({cmp_nem['kills_received']}D)" if cmp_nem else "-"

        compare_card = stattracker_playercard.build_player_card(
            player_name=_compare_label(compare_sid),
            kpis=compare_kpis,
            nemesis=_cmp_nemesis,
            practice_target=_cmp_practice,
        )
        layout.addWidget(compare_card)

    # --- Insight Selection ---
    selected_category = str(getattr(parent, "_stattracker_weapon_category", "all") or "all")
    stattracker_insight_builder.build_insight_section(parent, layout, dashboard, selected_sid, selected_category)


def on_stattracker_data_updated(parent):
    logger.log("[UI] Stat Tracker data update triggered", level="DEBUG")
    parent._stattracker_cache_dirty = True
    refresh_stattracker(parent)
