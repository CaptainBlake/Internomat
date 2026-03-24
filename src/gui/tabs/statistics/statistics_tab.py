from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)
from datetime import datetime

import core.stats.statistics as statistics
import core.stats.statistics_scoreboard as statistics_scoreboard
from gui.tabs.statistics import statistics_scoreboard_view
from services import executor
import services.logger as logger


class StatisticsDispatcher(QObject):
    loaded = Signal(object, object)
    failed = Signal(object, object)
    scoreboard_loaded = Signal(object, object, object)
    scoreboard_failed = Signal(object, object)


def _fmt_optional(value):
    return "n/a" if value is None else str(value)


def _fmt_played_at(value):
    raw = str(value or "").strip()
    if not raw:
        return "n/a"

    # SQLite timestamps are usually stored as "YYYY-MM-DD HH:MM:SS".
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
        return parsed.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return raw


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


def _on_recent_map_activated(parent, payload):
    match_id = payload.get("match_id")
    map_number = payload.get("map_number")

    logger.log(
        f"[UI] Statistics row activated match={match_id} map={map_number}",
        level="DEBUG",
    )

    callback = getattr(parent, "_statistics_row_activated", None)
    if callable(callback):
        callback(payload)


def _build_recent_maps_table(rows, on_row_activated=None):
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

    hint = QLabel("Tip: double-click a row to open the scoreboard")
    hint.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    hint.setStyleSheet("font-size: 11px; color: #5A6B7C;")
    layout.addWidget(hint)

    table = QTableWidget(0, 8)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setGridStyle(Qt.PenStyle.SolidLine)
    table.setMouseTracking(True)
    table.verticalHeader().setVisible(False)
    table.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
    table.setStyleSheet(
        """
        QTableWidget {
            background: rgba(255, 255, 255, 0.92);
            alternate-background-color: rgba(241, 246, 252, 0.88);
            gridline-color: #D2DCE8;
            border: 1px solid #D6DEE9;
            border-radius: 6px;
        }
        QHeaderView::section {
            background: #EAF2FB;
            color: #22384D;
            border: 1px solid #D2DCE8;
            padding: 6px;
            font-weight: 700;
        }
        QTableWidget::item:selected {
            background: rgba(213, 229, 248, 0.95);
            color: #22384D;
        }
        """
    )

    headers = ["Match", "Map", "Winner", "Score", "Demo", "Rounds", "Kills", "At"]
    header_tooltips = {
        "Match": "Match identifier from the database.",
        "Map": "Map name for this match map entry.",
        "Winner": "Winning team recorded for this map.",
        "Score": "Final team score (team1:team2) for this map.",
        "Demo": "Whether the match is flagged as having a demo in DB.",
        "Rounds": "Total rounds in this map (score-based or parsed fallback).",
        "Kills": "Total kills across all players for this map.",
        "At": "Played timestamp for this map.",
    }
    for i, text in enumerate(headers):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(header_tooltips.get(text, ""))
        table.setHorizontalHeaderItem(i, item)

    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

    for row in rows:
        idx = table.rowCount()
        table.insertRow(idx)

        row_payload = {
            "match_id": str(row["match_id"]),
            "map_number": int(row["map_number"]),
            "map_name": str(row["map_name"]),
        }

        values = [
            row["match_id"],
            row["map_name"],
            row["winner"],
            f"{row['team1_score']}:{row['team2_score']}",
            "yes" if row["db_demo_flag"] else "no",
            _fmt_optional(row["demo_rounds"]),
            _fmt_optional(row["demo_kills"]),
            _fmt_played_at(row["played_at"]),
        ]

        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, row_payload)
            table.setItem(idx, col, item)

    if callable(on_row_activated):
        def _emit_row_activation(row_index):
            item = table.item(row_index, 0)
            if item is None:
                return

            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                on_row_activated(payload)

        table.cellDoubleClicked.connect(lambda row, _col: _emit_row_activation(row))

    layout.addWidget(table, 1)
    return frame


def _go_back_to_match_history(parent):
    overview = getattr(parent, "_statistics_overview", None)
    recent_rows = getattr(parent, "_statistics_recent_rows", None)
    if overview is None or recent_rows is None:
        refresh_statistics_tab(parent)
        return

    _render_statistics_content(parent, overview, recent_rows)


def _show_scoreboard_loading_state(parent, payload):
    layout = parent.layout()
    if layout is None:
        return

    _clear_dynamic_content(layout)

    controls = QHBoxLayout()
    back_button = QPushButton("Back to Match History")
    back_button.clicked.connect(lambda: _go_back_to_match_history(parent))
    controls.addWidget(back_button)
    controls.addStretch(1)
    layout.addLayout(controls)

    map_name = str(payload.get("map_name") or "?")
    match_id = str(payload.get("match_id") or "?")
    map_number = int(payload.get("map_number") or 0)

    title = QLabel(f"Loading scoreboard: {map_name} (match {match_id}, map {map_number})")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 14px;")
    layout.addWidget(title, 1)


def _render_scoreboard_content(parent, payload, scoreboard):
    layout = parent.layout()
    if layout is None:
        return

    _clear_dynamic_content(layout)

    summary = scoreboard.get("summary") or {}
    rows = scoreboard.get("rows") or []
    timeline = scoreboard.get("timeline")

    controls = QHBoxLayout()
    back_button = QPushButton("Back to Match History")
    back_button.clicked.connect(lambda: _go_back_to_match_history(parent))
    controls.addWidget(back_button)
    controls.addStretch(1)
    layout.addLayout(controls)

    map_name = str(summary.get("map_name") or payload.get("map_name") or "?")
    match_id = str(summary.get("match_id") or payload.get("match_id") or "?")
    map_number = int(summary.get("map_number") or payload.get("map_number") or 0)
    winner = str(summary.get("winner") or "?")
    score = f"{int(summary.get('team1_score') or 0)}:{int(summary.get('team2_score') or 0)}"
    played_at = _fmt_played_at(summary.get("played_at"))

    summary_label = QLabel(
        f"Match {match_id} | Map {map_number}: {map_name} | Winner: {winner} | Score: {score} | {played_at}"
    )
    summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    summary_label.setStyleSheet("font-size: 13px; color: #2E4C69; padding: 6px;")
    layout.addWidget(summary_label)

    if not rows:
        empty = QLabel("No player stats found for this map.")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 14px;")
        layout.addWidget(empty, 1)
        return

    statistics_scoreboard_view.render_split_scoreboard(layout, summary, rows, timeline=timeline)


def _open_scoreboard_view(parent, payload):
    if getattr(parent, "_statistics_scoreboard_loading", False):
        return

    key = (str(payload.get("match_id")), int(payload.get("map_number") or 0))
    scoreboard_cache = getattr(parent, "_statistics_scoreboard_cache", {})
    cached_scoreboard = scoreboard_cache.get(key)
    if isinstance(cached_scoreboard, dict):
        _render_scoreboard_content(parent, payload, cached_scoreboard)
        return

    request_id = int(getattr(parent, "_statistics_scoreboard_request_id", 0)) + 1
    parent._statistics_scoreboard_request_id = request_id
    parent._statistics_scoreboard_loading = True

    _show_scoreboard_loading_state(parent, payload)
    dispatcher = _ensure_dispatcher(parent)

    def worker():
        try:
            scoreboard = statistics_scoreboard.get_map_scoreboard(
                payload.get("match_id"),
                payload.get("map_number"),
            )
            dispatcher.scoreboard_loaded.emit(request_id, payload, scoreboard)
        except Exception as e:
            dispatcher.scoreboard_failed.emit(request_id, e)

    executor.submit(worker)


def _clear_dynamic_content(layout):
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


def _render_statistics_content(parent, overview, recent_rows):
    layout = parent.layout()
    if layout is None:
        return

    parent._statistics_overview = overview
    parent._statistics_recent_rows = recent_rows

    _clear_dynamic_content(layout)

    metrics = QHBoxLayout()
    metrics.setSpacing(12)

    metrics.addWidget(_build_metric_card("Total Maps", str(overview["total_maps"])))
    metrics.addWidget(_build_metric_card("Unique Players", str(overview["unique_players"])))
    metrics.addWidget(_build_metric_card("Demo Matches", str(overview["demo_matches"])))

    layout.addLayout(metrics)
    layout.addWidget(
        _build_recent_maps_table(
            recent_rows,
            on_row_activated=lambda payload: _on_recent_map_activated(parent, payload),
        ),
        1,
    )


def _show_loading_state(parent, message):
    layout = parent.layout()
    if layout is None:
        return

    _clear_dynamic_content(layout)

    loading = QLabel(message)
    loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
    loading.setStyleSheet("font-size: 13px; color: #5B7A72; padding: 14px;")
    layout.addWidget(loading, 1)


def _ensure_dispatcher(parent):
    if hasattr(parent, "_statistics_dispatcher"):
        return parent._statistics_dispatcher

    dispatcher = StatisticsDispatcher(parent)

    def on_loaded(request_id, payload):
        if request_id != getattr(parent, "_statistics_request_id", None):
            return

        parent._statistics_update_loading = False

        if not isinstance(payload, dict):
            payload = {}

        overview = payload.get("overview") or {
            "total_maps": 0,
            "unique_players": 0,
            "demo_matches": 0,
        }
        recent_rows = payload.get("recent_rows") or []
        scoreboards = payload.get("scoreboards") or {}

        parent._statistics_overview = overview
        parent._statistics_recent_rows = recent_rows
        parent._statistics_scoreboard_cache = dict(scoreboards)
        parent._statistics_cache_dirty = False

        if getattr(parent, "_statistics_render_on_update", False):
            _render_statistics_content(parent, overview, recent_rows)

        parent._statistics_render_on_update = False

    def on_failed(request_id, error):
        if request_id != getattr(parent, "_statistics_request_id", None):
            return

        parent._statistics_update_loading = False
        logger.log_error(f"[UI] Statistics refresh failed: {error}", exc=error)
        if getattr(parent, "_statistics_render_on_update", False):
            _show_loading_state(parent, "Failed to load statistics. Check logs for details.")
        parent._statistics_render_on_update = False

    def on_scoreboard_loaded(request_id, payload, scoreboard):
        if request_id != getattr(parent, "_statistics_scoreboard_request_id", None):
            return

        parent._statistics_scoreboard_loading = False
        key = (str(payload.get("match_id")), int(payload.get("map_number") or 0))
        parent._statistics_scoreboard_cache[key] = scoreboard
        _render_scoreboard_content(parent, payload, scoreboard)

    def on_scoreboard_failed(request_id, error):
        if request_id != getattr(parent, "_statistics_scoreboard_request_id", None):
            return

        parent._statistics_scoreboard_loading = False
        logger.log_error(f"[UI] Scoreboard load failed: {error}", exc=error)
        _show_loading_state(parent, "Failed to load scoreboard. Check logs for details.")

    dispatcher.loaded.connect(on_loaded)
    dispatcher.failed.connect(on_failed)
    dispatcher.scoreboard_loaded.connect(on_scoreboard_loaded)
    dispatcher.scoreboard_failed.connect(on_scoreboard_failed)
    parent._statistics_dispatcher = dispatcher
    return dispatcher


def build_statistics_tab(parent):
    logger.log("[UI] Build Statistics tab", level="DEBUG")

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("Statistics")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 900; color: #21443C;")
    layout.addWidget(title)

    info = QLabel("DB metrics plus parsed demo cache enrichment")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info.setStyleSheet("font-size: 12px; color: #5B7A72;")
    layout.addWidget(info)

    parent._statistics_request_id = 0
    parent._statistics_scoreboard_request_id = 0
    parent._statistics_update_loading = False
    parent._statistics_scoreboard_loading = False
    parent._statistics_render_on_update = False
    parent._statistics_cache_dirty = True
    parent._statistics_overview = None
    parent._statistics_recent_rows = None
    parent._statistics_scoreboard_cache = {}
    parent._statistics_row_activated = lambda payload: _open_scoreboard_view(parent, payload)
    _ensure_dispatcher(parent)

    parent._statistics_on_update = lambda: on_statistics_data_updated(parent)
    parent._statistics_refresh = lambda: refresh_statistics_tab(parent)
    refresh_statistics_tab(parent)


def _start_statistics_update(parent, render_after_update):
    if getattr(parent, "_statistics_update_loading", False):
        parent._statistics_render_on_update = (
            getattr(parent, "_statistics_render_on_update", False) or bool(render_after_update)
        )
        logger.log("[UI] Statistics update skipped (already loading)", level="DEBUG")
        return

    request_id = int(getattr(parent, "_statistics_request_id", 0)) + 1
    parent._statistics_request_id = request_id
    parent._statistics_update_loading = True
    parent._statistics_render_on_update = bool(render_after_update)

    if render_after_update:
        _show_loading_state(parent, "Loading statistics...")

    dispatcher = _ensure_dispatcher(parent)

    def worker():
        try:
            overview = statistics.get_overview()
            recent_rows = statistics.get_recent_maps(10)

            scoreboards = {}
            for row in recent_rows:
                match_id = str(row.get("match_id"))
                map_number = int(row.get("map_number") or 0)
                key = (match_id, map_number)
                try:
                    scoreboards[key] = statistics_scoreboard.get_map_scoreboard(match_id, map_number)
                except Exception as e:
                    logger.log_error(
                        f"[UI] Scoreboard precompute failed match={match_id} map={map_number}: {e}",
                        exc=e,
                    )

            dispatcher.loaded.emit(
                request_id,
                {
                    "overview": overview,
                    "recent_rows": recent_rows,
                    "scoreboards": scoreboards,
                },
            )
        except Exception as e:
            dispatcher.failed.emit(request_id, e)

    executor.submit(worker)


def on_statistics_data_updated(parent):
    logger.log("[UI] Statistics data update triggered", level="DEBUG")
    parent._statistics_cache_dirty = True
    _start_statistics_update(parent, render_after_update=False)


def refresh_statistics_tab(parent):
    logger.log("[UI] Refresh Statistics tab", level="DEBUG")

    layout = parent.layout()
    if layout is None:
        return

    if getattr(parent, "_statistics_update_loading", False):
        logger.log("[UI] Statistics refresh waiting for update", level="DEBUG")
        parent._statistics_render_on_update = True
        _show_loading_state(parent, "Loading statistics...")
        return

    if not getattr(parent, "_statistics_cache_dirty", True):
        overview = getattr(parent, "_statistics_overview", None)
        recent_rows = getattr(parent, "_statistics_recent_rows", None)
        if isinstance(overview, dict) and isinstance(recent_rows, list):
            _render_statistics_content(parent, overview, recent_rows)
            return

    _start_statistics_update(parent, render_after_update=True)
