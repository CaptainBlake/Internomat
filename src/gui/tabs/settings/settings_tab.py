from PySide6.QtCore import Qt, QTimer, QUrl, QDate
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDoubleSpinBox,
    QSizePolicy,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QScrollArea,
    QFrame,
    QListWidget,
    QLineEdit,
    QGridLayout,
    QSpinBox,
    QMessageBox,
    QDialog,
    QDateEdit,
)
from core.settings.settings import settings
from core.settings import service as settings_service
from core.update import service as update_service
from core.version import APP_VERSION
from core import io_service
from services import executor
import services.logger as logger
from services.matchzy import sync
from services.demo_scrapper import DemoScrapperIntegration
from services import demo_cache
from PySide6.QtCore import QObject, Signal
from gui.tabs.settings.log_window import open_log_window
from gui.widgets.pipeline_progress_dialog import PipelineProgressDialog
import json
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from db.connection_db import DB_FILE, get_conn
from db.init_db import init_db
import db.settings_db as settings_db
from core.pathing import data_path

class SettingsDispatcher(QObject):
    sync_finished = Signal()
    sync_error = Signal(object)
    demos_sync_finished = Signal(object)
    demos_sync_error = Signal(object)
    demos_sync_progress = Signal(object)
    update_check_finished = Signal(object)
    update_check_error = Signal(object)
    update_download_finished = Signal(object)
    update_download_error = Signal(object)

# SETTINGS TAB
def build_settings_tab(parent, on_players_updated=None, on_update_players=None, on_update_players_only=None, on_data_updated=None, on_players_data_updated=None):

    section_order = ["Settings", "Elo", "MatchZy", "Demos", "Maintenance"]

    root_layout = QHBoxLayout(parent)
    root_layout.setContentsMargins(20, 20, 20, 20)
    root_layout.setSpacing(20)

    # SIDEBAR
    sidebar = QListWidget()
    sidebar.setFixedWidth(170)
    sidebar.addItems(section_order)
    sidebar.setStyleSheet("""
        QListWidget {
            background: #FFFFFF;
            border: 1px solid #B9CADC;
            border-radius: 12px;
            padding: 6px;
            color: #1E2B38;
        }
        QListWidget::item {
            padding: 10px 12px;
            margin: 2px 0px;
            border: none;
        }
        QListWidget::item:selected {
            background: #DCEAF7;
            color: #1E2B38;
        }
        QListWidget::item:hover {
            background: #E7F1FB;
            color: #2E4C69;
        }
    """)
    root_layout.addWidget(sidebar)

    section_frames = []

    # SCROLL AREA
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("""
        QScrollArea {
            border: none;
            background: transparent;
        }
    """)

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setSpacing(12)
    layout.setAlignment(Qt.AlignTop)
    dispatcher = SettingsDispatcher(parent)
    demo_sync_progress_dialog = {"dialog": None}
    setting_bindings = []
    settings_dirty = {"value": False}

    scroll.setWidget(container)
    root_layout.addWidget(scroll, 1)


    # HELPERS

    def create_section(title):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.94);
                border: none;
                border-radius: 16px;
            }
        """)

        section_layout = QVBoxLayout(frame)
        section_layout.setContentsMargins(14, 12, 14, 12)
        section_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 15px;
            font-weight: 800;
            color: #22384D;
        """)

        section_layout.addWidget(title_label)
        return frame, section_layout

    def small_button(text):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3F88D9;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #5A9BE3;
            }
            QPushButton:pressed {
                background-color: #2F6FB3;
            }
            QPushButton:disabled {
                background-color: #BFD0E0;
                color: #F7FAFD;
            }
        """)
        return btn

    def danger_button(text):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #C73A3A;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #D64B4B;
            }
            QPushButton:pressed {
                background-color: #A82F2F;
            }
            QPushButton:disabled {
                background-color: #E6B8B8;
                color: #F8F3F3;
            }
        """)
        return btn

    def create_grid_section(title, rows, columns=3):
        frame, section_layout = create_section(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        for col in range(columns):
            grid.setColumnStretch(col, 1)

        for r, row in enumerate(rows):
            for c, widget in enumerate(row):
                if widget:
                    grid.addWidget(widget, r, c)

        section_layout.addLayout(grid)
        return frame

    def create_setting_row(label_text, widget, attr_name, tooltip=None):
        row = QHBoxLayout()
        row.setSpacing(10)

        label = QLabel(label_text)
        label.setMinimumWidth(220)
        label.setStyleSheet("""
            QLabel {
                font-weight: 600;
                color: #2E4C69;
                border: none;
                background: transparent;
            }
        """)

        if tooltip:
            label.setToolTip(tooltip)
            widget.setToolTip(tooltip)

        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        widget.setStyleSheet("""
            QSpinBox, QDoubleSpinBox {
                background: #FFFFFF;
                color: #1E2B38;
                border: 1px solid #B9CADC;
                border-radius: 8px;
                padding: 6px 36px 6px 10px;
                min-height: 36px;
                min-width: 130px;
            }

            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #3F88D9;
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                border: none;
                background: #DCEAF7;
                width: 24px;
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-position: top right;
                border-top-right-radius: 8px;
            }

            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-position: bottom right;
                border-bottom-right-radius: 8px;
            }

            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background: #E7F1FB;
            }

            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                width: 0px;
                height: 0px;
            }

            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 0px;
                height: 0px;
            }
        """)

        def mark_dirty(*_args):
            settings_dirty["value"] = True
            save_settings_button.setEnabled(True)

        if isinstance(widget, QCheckBox):
            widget.stateChanged.connect(mark_dirty)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(mark_dirty)
        elif isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(mark_dirty)
        else:
            widget.valueChanged.connect(mark_dirty)

        setting_bindings.append((attr_name, widget))

        row.addWidget(label)
        row.addWidget(widget)
        row.addStretch()

        return row

    # BUTTONS

    open_logs_button = small_button("Open Logs")

    import_settings_button = small_button("Import Settings")
    export_settings_button = small_button("Export Settings")
    save_settings_button = small_button("Save Settings")

    sync_matchzy_button = small_button("Sync with Matchzy")
    sync_demos_button = small_button("Sync demos")
    clear_cache_button = danger_button("Clear Cache")
    check_updates_button = small_button("Look for Updates")

    for btn in [
        import_settings_button,
        export_settings_button,
        save_settings_button,
        sync_matchzy_button,
        sync_demos_button,
        check_updates_button,
        clear_cache_button,
    ]:
        btn.setFocusPolicy(Qt.NoFocus)

    save_settings_button.setEnabled(False)


    # SECTIONS

    # MAINTENANCE
    maintenance_frame = create_grid_section("Maintenance", [
        [open_logs_button, clear_cache_button, check_updates_button],
        [import_settings_button, export_settings_button, None],
    ], columns=3)

    # SETTINGS
    settings_frame, settings_layout = create_section("Settings")

    
    # cooldown
    spin_cooldown = QSpinBox()
    spin_cooldown.setRange(0, 9999)
    spin_cooldown.setValue(settings.update_cooldown_minutes)
    spin_cooldown.setFixedWidth(100)
    spin_cooldown.setButtonSymbols(QSpinBox.NoButtons)

    settings_layout.addLayout(create_setting_row(
        "Update cooldown (minutes):",
        spin_cooldown,
        "update_cooldown_minutes",
        "Minimum time between updates\nRecommended: 10"
    ))

    spin_max_demos = QSpinBox()
    spin_max_demos.setRange(0, 10000)
    spin_max_demos.setValue(int(getattr(settings, "max_demos_per_update", 0) or 0))
    spin_max_demos.setFixedWidth(140)
    spin_max_demos.setButtonSymbols(QSpinBox.NoButtons)

    settings_layout.addLayout(create_setting_row(
        "Max demos per update:",
        spin_max_demos,
        "max_demos_per_update",
        "Hard cap per sync run. 0 disables the cap."
    ))

    # dist weight
    spin_weight = QDoubleSpinBox()
    spin_weight.setRange(0.0, 0.5)
    spin_weight.setSingleStep(0.01)
    spin_weight.setDecimals(2)
    spin_weight.setValue(settings.dist_weight)
    spin_weight.setFixedWidth(100)

    settings_layout.addLayout(create_setting_row(
        "Team balance weight:",
        spin_weight,
        "dist_weight",
        "Higher = more random teams\nRecommended: 0.25"
    ))

    # default rating
    spin_rating = QSpinBox()
    spin_rating.setRange(0, 50000)
    spin_rating.setValue(settings.default_rating)
    spin_rating.setFixedWidth(100)
    spin_rating.setButtonSymbols(QSpinBox.NoButtons)

    settings_layout.addLayout(create_setting_row(
        "Default rating:",
        spin_rating,
        "default_rating",
        "Fallback rating\nRecommended: 10000"
    ))

    # allow uneven teams
    checkbox_uneven = QCheckBox()
    checkbox_uneven.setChecked(settings.allow_uneven_teams)

    settings_layout.addLayout(create_setting_row(
        "Allow uneven teams:",
        checkbox_uneven,
        "allow_uneven_teams",
        "Allow uneven teams (e.g. 3 vs 2)"
    ))

    checkbox_maproulette_history = QCheckBox()
    checkbox_maproulette_history.setChecked(settings.maproulette_use_history)

    settings_layout.addLayout(create_setting_row(
        "Map roulette uses history:",
        checkbox_maproulette_history,
        "maproulette_use_history",
        "When enabled, map roulette uses match history percentages as map weights."
    ))

    checkbox_log_export_enabled = QCheckBox()
    checkbox_log_export_enabled.setChecked(bool(getattr(settings, "log_export_enabled", True)))

    settings_layout.addLayout(create_setting_row(
        "Export logs to file:",
        checkbox_log_export_enabled,
        "log_export_enabled",
        "When enabled, logs are written to timestamped files in the log folder."
    ))

    settings_button_row = QHBoxLayout()
    settings_button_row.setSpacing(10)
    settings_button_row.addWidget(save_settings_button)
    settings_button_row.addStretch()
    settings_layout.addLayout(settings_button_row)

    # ELO SETTINGS
    elo_frame, elo_layout = create_section("Elo")

    elo_info = QLabel(
        "Season ranges are edited as dates (masked input). "
        "A new season cannot be started until the previous one has an explicit end date."
    )
    elo_info.setWordWrap(True)
    elo_info.setStyleSheet("""
        QLabel {
            font-size: 12px;
            color: #5A6B7C;
            padding-bottom: 6px;
        }
    """)
    elo_layout.addWidget(elo_info)

    season_rows_layout = QVBoxLayout()
    season_rows_layout.setSpacing(8)
    elo_layout.addLayout(season_rows_layout)
    season_rows = []
    season_edit_unlocked = {"value": False}

    def mark_dirty(*_args):
        settings_dirty["value"] = True
        save_settings_button.setEnabled(True)

    def _date_from_str(value):
        txt = str(value or "").strip()
        if not txt:
            return None
        try:
            return datetime.fromisoformat(txt[:10]).date()
        except Exception:
            return None

    def _to_qdate(value):
        if value is None:
            return QDate.currentDate()
        return QDate(value.year, value.month, value.day)

    def _clear_layout(layout_obj):
        while layout_obj.count():
            item = layout_obj.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _build_season_rows(seasons_data):
        season_rows.clear()
        _clear_layout(season_rows_layout)

        if not seasons_data:
            seasons_data = [{"season": 0, "start": None, "end": None}]

        for idx, item in enumerate(seasons_data):
            row_wrap = QWidget()
            row = QHBoxLayout(row_wrap)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            lbl = QLabel(f"Season {idx}")
            lbl.setMinimumWidth(80)

            start_edit = QDateEdit()
            start_edit.setDisplayFormat("yyyy-MM-dd")
            start_edit.setCalendarPopup(True)
            start_edit.setDate(_to_qdate(item.get("start")))

            end_edit = QDateEdit()
            end_edit.setDisplayFormat("yyyy-MM-dd")
            end_edit.setCalendarPopup(True)
            end_edit.setDate(_to_qdate(item.get("end")))

            open_end = QCheckBox("Open end")
            open_end.setChecked(item.get("end") is None)

            if idx == 0:
                # Season 0 is the baseline; start date is intentionally omitted.
                start_edit.setEnabled(False)

            def _toggle_end(checked, edit=end_edit):
                edit.setEnabled(not checked)
                mark_dirty()

            open_end.toggled.connect(_toggle_end)
            _toggle_end(open_end.isChecked())

            start_edit.dateChanged.connect(mark_dirty)
            end_edit.dateChanged.connect(mark_dirty)

            row.addWidget(lbl)
            row.addWidget(QLabel("Start"))
            row.addWidget(start_edit)
            row.addWidget(QLabel("End"))
            row.addWidget(end_edit)
            row.addWidget(open_end)
            row.addStretch()

            season_rows_layout.addWidget(row_wrap)
            season_rows.append({
                "start": start_edit,
                "end": end_edit,
                "open": open_end,
            })

        _apply_season_lock_state(season_edit_unlocked["value"])

    def _serialize_seasons_or_error(show_popup=True):
        out = []
        prev_end = None
        for idx, row in enumerate(season_rows):
            start_date = row["start"].date().toPython() if row["start"].isEnabled() else None
            end_date = None if row["open"].isChecked() else row["end"].date().toPython()

            if idx > 0 and start_date is None:
                if show_popup:
                    QMessageBox.warning(parent, "Invalid season setup", f"Season {idx} requires a start date.")
                return None

            if start_date and end_date and end_date < start_date:
                if show_popup:
                    QMessageBox.warning(parent, "Invalid season setup", f"Season {idx}: end date cannot be before start date.")
                return None

            if idx > 0:
                if prev_end is None:
                    if show_popup:
                        QMessageBox.warning(parent, "Invalid season setup", "You cannot start a new season while the previous one is open-ended.")
                    return None
                if start_date <= prev_end:
                    if show_popup:
                        QMessageBox.warning(
                            parent,
                            "Invalid season setup",
                            f"Season {idx} starts inside or before Season {idx - 1}. "
                            f"It must be after {prev_end.isoformat()}.",
                        )
                    return None

            item = {"season": idx}
            if start_date is not None:
                item["start"] = start_date.isoformat()
            if end_date is not None:
                item["end"] = end_date.isoformat()
            out.append(item)
            prev_end = end_date

        if not out:
            out = [{"season": 0}]

        return out

    def _season_for_date(date_obj, seasons_payload):
        if date_obj is None:
            return None
        for item in seasons_payload:
            sid = int(item.get("season", 0))
            s = _date_from_str(item.get("start"))
            e = _date_from_str(item.get("end"))
            start_ok = s is None or date_obj >= s
            end_ok = e is None or date_obj <= e
            if start_ok and end_ok:
                return sid
        return None

    def _count_matches_for_season(season_idx, seasons_payload):
        count = 0
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT TRIM(COALESCE(NULLIF(end_time, ''), NULLIF(start_time, ''), NULLIF(created_at, ''), '')) AS played_at
                FROM matches
                """
            ).fetchall()

        for r in rows:
            raw = str(r["played_at"] or "").strip()
            if not raw:
                continue
            try:
                d = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
            except Exception:
                try:
                    d = datetime.fromisoformat(raw[:10]).date()
                except Exception:
                    continue
            resolved = _season_for_date(d, seasons_payload)
            if resolved == season_idx:
                count += 1
        return count

    def _add_season_row_action():
        if not season_edit_unlocked["value"]:
            return
        seasons = _serialize_seasons_or_error(show_popup=True)
        if seasons is None:
            return
        last = seasons[-1]
        if "end" not in last:
            QMessageBox.warning(parent, "Cannot add season", "Close the current last season with an end date before adding a new one.")
            return
        next_start = _date_from_str(last.get("end")) + timedelta(days=1)
        seasons.append({
            "season": len(seasons),
            "start": next_start.isoformat(),
            "end": None,
        })
        parsed = []
        for s in seasons:
            parsed.append({
                "season": int(s["season"]),
                "start": _date_from_str(s.get("start")),
                "end": _date_from_str(s.get("end")),
            })
        _build_season_rows(parsed)
        mark_dirty()

    def _remove_last_season_row_action():
        if not season_edit_unlocked["value"]:
            return
        seasons = _serialize_seasons_or_error(show_popup=False)
        if seasons is None or len(seasons) <= 1:
            return

        last_idx = len(seasons) - 1
        existing = _count_matches_for_season(last_idx, seasons)
        if existing > 0:
            QMessageBox.warning(
                parent,
                "Cannot remove season",
                f"Season {last_idx} has {existing} stored match(es). "
                "Removing it would invalidate historical assignments.",
            )
            return

        seasons = seasons[:-1]
        parsed = []
        for s in seasons:
            parsed.append({
                "season": int(s["season"]),
                "start": _date_from_str(s.get("start")),
                "end": _date_from_str(s.get("end")),
            })
        _build_season_rows(parsed)
        mark_dirty()

    season_btn_row = QHBoxLayout()
    btn_add_season = small_button("Add Season")
    btn_remove_season = danger_button("Remove Last")
    season_btn_row.addWidget(btn_add_season)
    season_btn_row.addWidget(btn_remove_season)
    season_btn_row.addStretch()
    elo_layout.addLayout(season_btn_row)

    season_warning = QLabel(
        "Season editing is locked. Unlock only for boundary planning.\n"
        "All previous seasons stay read-only."
    )
    season_warning.setWordWrap(True)
    season_warning.setStyleSheet("font-size: 12px; color: #A33A3A; font-weight: 700;")
    elo_layout.addWidget(season_warning)

    unlock_seasons_checkbox = QCheckBox("Unlock season editing")
    unlock_seasons_checkbox.setChecked(False)
    elo_layout.addWidget(unlock_seasons_checkbox)

    def _apply_season_lock_state(checked):
        season_edit_unlocked["value"] = bool(checked)
        last_idx = len(season_rows) - 1

        for idx, row in enumerate(season_rows):
            editable = bool(checked) and idx == last_idx
            row["start"].setEnabled(editable and idx > 0)
            row["open"].setEnabled(editable)
            if row["open"].isChecked():
                row["end"].setEnabled(False)
            else:
                row["end"].setEnabled(editable)

        btn_add_season.setEnabled(bool(checked))
        btn_remove_season.setEnabled(bool(checked))

    unlock_seasons_checkbox.toggled.connect(_apply_season_lock_state)

    btn_add_season.clicked.connect(_add_season_row_action)
    btn_remove_season.clicked.connect(_remove_last_season_row_action)

    try:
        raw_seasons = str(getattr(settings, "elo_seasons_json", "[]") or "[]")
        loaded = json.loads(raw_seasons)
        parsed_rows = []
        if isinstance(loaded, list):
            loaded = sorted(
                [x for x in loaded if isinstance(x, dict)],
                key=lambda x: int(x.get("season", 0)),
            )
            for i, item in enumerate(loaded):
                parsed_rows.append({
                    "season": i,
                    "start": _date_from_str(item.get("start")),
                    "end": _date_from_str(item.get("end")),
                })
        _build_season_rows(parsed_rows)
    except Exception:
        _build_season_rows([])

    _apply_season_lock_state(False)

    # Elo tuning controls (production values)
    spin_elo_k = QDoubleSpinBox()
    spin_elo_k.setRange(0.0, 200.0)
    spin_elo_k.setDecimals(2)
    spin_elo_k.setSingleStep(1.0)
    spin_elo_k.setValue(float(getattr(settings, "elo_k_factor", 24.0)))
    elo_layout.addLayout(create_setting_row("K factor:", spin_elo_k, "elo_k_factor", "Rating swing per match."))

    spin_elo_base = QDoubleSpinBox()
    spin_elo_base.setRange(0.0, 5000.0)
    spin_elo_base.setDecimals(1)
    spin_elo_base.setSingleStep(10.0)
    spin_elo_base.setValue(float(getattr(settings, "elo_base_rating", 1500.0)))
    elo_layout.addLayout(create_setting_row("Base rating:", spin_elo_base, "elo_base_rating", "Starting Elo for new players."))

    spin_elo_alpha = QDoubleSpinBox()
    spin_elo_alpha.setRange(0.0, 2.0)
    spin_elo_alpha.setDecimals(3)
    spin_elo_alpha.setSingleStep(0.01)
    spin_elo_alpha.setValue(float(getattr(settings, "elo_adr_alpha", 0.20)))
    elo_layout.addLayout(create_setting_row("ADR alpha:", spin_elo_alpha, "elo_adr_alpha", "ADR influence strength."))

    spin_elo_spread = QDoubleSpinBox()
    spin_elo_spread.setRange(0.1, 200.0)
    spin_elo_spread.setDecimals(2)
    spin_elo_spread.setSingleStep(1.0)
    spin_elo_spread.setValue(float(getattr(settings, "elo_adr_spread", 22.0)))
    elo_layout.addLayout(create_setting_row("ADR spread:", spin_elo_spread, "elo_adr_spread", "Z-score denominator for ADR delta."))

    spin_elo_min_mult = QDoubleSpinBox()
    spin_elo_min_mult.setRange(0.01, 5.0)
    spin_elo_min_mult.setDecimals(3)
    spin_elo_min_mult.setSingleStep(0.01)
    spin_elo_min_mult.setValue(float(getattr(settings, "elo_adr_min_mult", 0.85)))
    elo_layout.addLayout(create_setting_row("ADR min multiplier:", spin_elo_min_mult, "elo_adr_min_mult", "Lower clamp for ADR multiplier."))

    spin_elo_max_mult = QDoubleSpinBox()
    spin_elo_max_mult.setRange(0.01, 5.0)
    spin_elo_max_mult.setDecimals(3)
    spin_elo_max_mult.setSingleStep(0.01)
    spin_elo_max_mult.setValue(float(getattr(settings, "elo_adr_max_mult", 1.15)))
    elo_layout.addLayout(create_setting_row("ADR max multiplier:", spin_elo_max_mult, "elo_adr_max_mult", "Upper clamp for ADR multiplier."))

    spin_elo_prior = QDoubleSpinBox()
    spin_elo_prior.setRange(0.0, 100.0)
    spin_elo_prior.setDecimals(2)
    spin_elo_prior.setSingleStep(0.5)
    spin_elo_prior.setValue(float(getattr(settings, "elo_adr_prior_matches", 5.0)))
    elo_layout.addLayout(create_setting_row("ADR prior matches:", spin_elo_prior, "elo_adr_prior_matches", "Bayesian smoothing prior weight."))

    spin_elo_anchor = QDoubleSpinBox()
    spin_elo_anchor.setRange(0.0, 500.0)
    spin_elo_anchor.setDecimals(2)
    spin_elo_anchor.setSingleStep(1.0)
    spin_elo_anchor.setValue(float(getattr(settings, "elo_initial_global_anchor", 80.0)))
    elo_layout.addLayout(create_setting_row("Initial global anchor:", spin_elo_anchor, "elo_initial_global_anchor", "Fallback ADR expectation before data exists."))

    tuning_warning = QLabel(
        "Warning: changing tuning during an active season will invalidate comparability.\n"
        "Use only between seasons."
    )
    tuning_warning.setWordWrap(True)
    tuning_warning.setStyleSheet("font-size: 12px; color: #A33A3A; font-weight: 700;")
    elo_layout.addWidget(tuning_warning)

    unlock_tuning_checkbox = QCheckBox("Unlock advanced Elo tuning")
    unlock_tuning_checkbox.setChecked(False)
    elo_layout.addWidget(unlock_tuning_checkbox)

    tuning_widgets = [
        spin_elo_k,
        spin_elo_base,
        spin_elo_alpha,
        spin_elo_spread,
        spin_elo_min_mult,
        spin_elo_max_mult,
        spin_elo_prior,
        spin_elo_anchor,
    ]

    def _apply_tuning_lock_state(checked):
        for w in tuning_widgets:
            w.setEnabled(bool(checked))

    unlock_tuning_checkbox.toggled.connect(_apply_tuning_lock_state)
    _apply_tuning_lock_state(False)

    # MATCHZY SETTINGS
    matchzy_frame, matchzy_layout = create_section("MatchZy Database")

    info_label = QLabel("Requires MatchZy to be configured with a MySQL database.")
    info_label.setWordWrap(True)
    info_label.setStyleSheet("""
        QLabel {
            font-size: 12px;
            color: #5A6B7C;
            padding-bottom: 6px;
        }
    """)

    matchzy_layout.addWidget(info_label)

    def text_input(value="", password=False):
        inp = QLineEdit()
        inp.setText(value)
        inp.setFixedWidth(200)

        if password:
            inp.setEchoMode(QLineEdit.Password)

        inp.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                color: #1E2B38;
                border: 1px solid #B9CADC;
                border-radius: 8px;
                padding: 6px 10px;
                min-height: 36px;
            }
            QLineEdit:focus {
                border: 1px solid #3F88D9;
            }
        """)
        return inp


    # host
    input_host = text_input(settings.matchzy_host)
    matchzy_layout.addLayout(create_setting_row(
        "Host:",
        input_host,
        "matchzy_host"
    ))

    input_port = QSpinBox()
    input_port.setFixedWidth(100)
    input_port.setRange(1, 65535)
    input_port.setValue(settings.matchzy_port)

    matchzy_layout.addLayout(create_setting_row(
        "Port:",
        input_port,
        "matchzy_port"
    ))

    # user
    input_user = text_input(settings.matchzy_user)
    matchzy_layout.addLayout(create_setting_row(
        "User:",
        input_user,
        "matchzy_user"
    ))

    # password
    input_password = text_input(settings.matchzy_password, password=True)
    matchzy_layout.addLayout(create_setting_row(
        "Password:",
        input_password,
        "matchzy_password"
    ))

    # database
    input_db = text_input(settings.matchzy_database)
    matchzy_layout.addLayout(create_setting_row(
        "Database:",
        input_db,
        "matchzy_database"
    ))

    checkbox_auto_import_players_from_history = QCheckBox()
    checkbox_auto_import_players_from_history.setChecked(settings.auto_import_players_from_history)
    matchzy_layout.addLayout(create_setting_row(
        "Import players from history:",
        checkbox_auto_import_players_from_history,
        "auto_import_players_from_history",
        "When enabled, MatchZy + demo sync imports players from match history into the team pool."
    ))

    checkbox_auto_import_maps_from_history = QCheckBox()
    checkbox_auto_import_maps_from_history.setChecked(settings.auto_import_maps_from_history)
    matchzy_layout.addLayout(create_setting_row(
        "Import maps from history:",
        checkbox_auto_import_maps_from_history,
        "auto_import_maps_from_history",
        "When enabled, MatchZy sync imports map names from match history into the map pool."
    ))

    # DEMOS SETTINGS
    demos_frame, demos_layout = create_section("MatchZy Demos")

    input_demo_ftp_host = text_input(settings.demo_ftp_host)
    input_demo_ftp_host.setPlaceholderText("IP/domain")
    demos_layout.addLayout(create_setting_row(
        "FTP Server IP:",
        input_demo_ftp_host,
        "demo_ftp_host",
        "IP or domain"
    ))

    input_demo_ftp_port = QSpinBox()
    input_demo_ftp_port.setFixedWidth(100)
    input_demo_ftp_port.setRange(1, 65535)
    input_demo_ftp_port.setValue(settings.demo_ftp_port)
    demos_layout.addLayout(create_setting_row(
        "FTP Port:",
        input_demo_ftp_port,
        "demo_ftp_port"
    ))

    input_demo_ftp_user = text_input(settings.demo_ftp_user)
    input_demo_ftp_user.setPlaceholderText("FTP user")
    demos_layout.addLayout(create_setting_row(
        "FTP User:",
        input_demo_ftp_user,
        "demo_ftp_user"
    ))

    input_demo_ftp_password = text_input(settings.demo_ftp_password, password=True)
    input_demo_ftp_password.setPlaceholderText("FTP password")
    demos_layout.addLayout(create_setting_row(
        "FTP Passwort:",
        input_demo_ftp_password,
        "demo_ftp_password"
    ))

    input_demo_remote_path = text_input(settings.demo_remote_path)
    input_demo_remote_path.setPlaceholderText("/cs2/game/csgo/MatchZy")
    demos_layout.addLayout(create_setting_row(
        "Remote demo path:",
        input_demo_remote_path,
        "demo_remote_path"
    ))

    sections_by_key = {
        "Settings": settings_frame,
        "Elo": elo_frame,
        "MatchZy": matchzy_frame,
        "Demos": demos_frame,
        "Maintenance": maintenance_frame,
    }

    for section_key in section_order:
        frame = sections_by_key.get(section_key)
        if frame is None:
            continue

        layout.addWidget(frame)
        section_frames.append(frame)

    layout.addStretch()

    def go_to_section(index):
        if index < 0 or index >= len(section_frames):
            return

        target = section_frames[index]
        scroll.ensureWidgetVisible(target, 0, 16)
    
    # ACTIONS

    def open_logs():
        open_log_window(parent)

    def apply_settings_payload_to_form(payload):
        for attr_name, widget in setting_bindings:
            if attr_name not in payload:
                continue

            value = payload[attr_name]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, QComboBox):
                text_value = "" if value is None else str(value)
                idx = widget.findText(text_value)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))

        if "elo_seasons_json" in payload:
            try:
                loaded = json.loads(str(payload.get("elo_seasons_json") or "[]"))
            except Exception:
                loaded = []

            parsed_rows = []
            if isinstance(loaded, list):
                loaded = sorted(
                    [x for x in loaded if isinstance(x, dict)],
                    key=lambda x: int(x.get("season", 0)),
                )
                for i, item in enumerate(loaded):
                    parsed_rows.append({
                        "season": i,
                        "start": _date_from_str(item.get("start")),
                        "end": _date_from_str(item.get("end")),
                    })
            _build_season_rows(parsed_rows)

    def export_settings_action():
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export Settings",
            "internomat_settings.cfg",
            "CFG Files (*.cfg);;JSON Files (*.json)",
        )
        if not path:
            return

        payload = {attr_name: read_widget_value(widget) for attr_name, widget in setting_bindings}
        seasons = _serialize_seasons_or_error(show_popup=True)
        if seasons is None:
            return
        payload["elo_seasons_json"] = json.dumps(seasons)

        try:
            settings_service.export_settings_payload(path, payload)
            logger.log_info(f"[SETTINGS] Exported to {path}")
        except Exception as e:
            logger.log_error(f"[SETTINGS] Export failed: {e}")

    def import_settings_action():
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Import Settings",
            "",
            "CFG Files (*.cfg);;JSON Files (*.json)",
        )
        if not path:
            return

        confirm = QMessageBox.question(
            parent,
            "Confirm Settings Import",
            "Importing settings will overwrite current values in this form. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            payload = settings_service.import_settings_payload(path)

            if not isinstance(payload, dict):
                raise ValueError("Invalid settings file format")

            apply_settings_payload_to_form(payload)

            if not apply_form_to_settings(save=True):
                return
            logger.set_log_export_enabled(bool(getattr(settings, "log_export_enabled", True)))
            settings_dirty["value"] = False
            save_settings_button.setEnabled(False)
            logger.log_info(f"[SETTINGS] Imported from {path}")

            if callable(on_data_updated):
                on_data_updated()

        except Exception as e:
            logger.log_error(f"[SETTINGS] Import failed: {e}")

    def read_widget_value(widget):
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return widget.value()

    def apply_form_to_settings(save=False):
        for attr_name, widget in setting_bindings:
            setattr(settings, attr_name, read_widget_value(widget))

        seasons = _serialize_seasons_or_error(show_popup=True)
        if seasons is None:
            return False
        settings.elo_seasons_json = json.dumps(seasons)

        if save:
            settings.save()
        return True

    def save_settings_action():
        if float(spin_elo_min_mult.value()) > float(spin_elo_max_mult.value()):
            QMessageBox.warning(
                parent,
                "Invalid Elo tuning",
                "ADR min multiplier cannot be greater than ADR max multiplier.",
            )
            return

        if float(spin_elo_spread.value()) <= 0:
            QMessageBox.warning(
                parent,
                "Invalid Elo tuning",
                "ADR spread must be greater than 0.",
            )
            return

        tuning_changed = (
            float(spin_elo_k.value()) != float(getattr(settings, "elo_k_factor", 24.0))
            or float(spin_elo_base.value()) != float(getattr(settings, "elo_base_rating", 1500.0))
            or float(spin_elo_alpha.value()) != float(getattr(settings, "elo_adr_alpha", 0.20))
            or float(spin_elo_spread.value()) != float(getattr(settings, "elo_adr_spread", 22.0))
            or float(spin_elo_min_mult.value()) != float(getattr(settings, "elo_adr_min_mult", 0.85))
            or float(spin_elo_max_mult.value()) != float(getattr(settings, "elo_adr_max_mult", 1.15))
            or float(spin_elo_prior.value()) != float(getattr(settings, "elo_adr_prior_matches", 5.0))
            or float(spin_elo_anchor.value()) != float(getattr(settings, "elo_initial_global_anchor", 80.0))
        )

        if tuning_changed and not unlock_tuning_checkbox.isChecked():
            QMessageBox.warning(
                parent,
                "Tuning locked",
                "Unlock advanced Elo tuning first before changing parameters.",
            )
            return

        if tuning_changed:
            seasons_now = _serialize_seasons_or_error(show_popup=True)
            if seasons_now is None:
                return
            today = datetime.now().date()
            active = _season_for_date(today, seasons_now)
            if active is not None:
                matches_in_active = _count_matches_for_season(active, seasons_now)
                if matches_in_active > 0:
                    QMessageBox.warning(
                        parent,
                        "Blocked: active season has matches",
                        f"Season {active} already has {matches_in_active} match(es). "
                        "Do not change Elo tuning inside an active season.",
                    )
                    return

        if not apply_form_to_settings(save=True):
            return
        logger.set_log_export_enabled(bool(getattr(settings, "log_export_enabled", True)))
        settings_dirty["value"] = False
        save_settings_button.setEnabled(False)
        logger.log("[SETTINGS] Saved", level="INFO")

    def sync_matchzy_action():
        if not sync_matchzy_button.isEnabled():
            return

        if not apply_form_to_settings(save=False):
            return
        sync_matchzy_button.setEnabled(False)

        def worker():
            try:
                sync()
                dispatcher.sync_finished.emit()
            except Exception as e:
                dispatcher.sync_error.emit(e)

        executor.submit(worker)

    def clear_cache_action():
        base_dir = data_path()
        demos_dir = base_dir / "demos"
        parsed_dir = demos_dir / "parsed"
        logs_dir = base_dir / "log"
        db_files = [
            Path(DB_FILE),
            Path(str(DB_FILE) + "-wal"),
            Path(str(DB_FILE) + "-shm"),
        ]

        dialog = QDialog(parent)
        dialog.setWindowTitle("Delete Data")
        dialog.setModal(True)
        dialog.resize(430, 250)

        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(14, 12, 14, 12)
        dlg_layout.setSpacing(10)

        info = QLabel("Select what to delete:")
        info.setStyleSheet("font-size: 13px; font-weight: 700; color: #22384D;")
        dlg_layout.addWidget(info)

        cb_demos = QCheckBox("Demos")
        cb_parsed = QCheckBox("Parsed payloads")
        cb_logs = QCheckBox("Logs")
        cb_database = QCheckBox("Database")
        cb_include_settings = QCheckBox("Including settings")
        cb_include_players = QCheckBox("Including player-list")
        cb_include_settings.setChecked(False)
        cb_include_settings.setEnabled(False)
        cb_include_players.setChecked(False)
        cb_include_players.setEnabled(False)

        for cb in (cb_demos, cb_parsed, cb_logs, cb_database):
            cb.setStyleSheet("QCheckBox { color: #2E4C69; font-weight: 600; padding: 2px 0px; }")
            dlg_layout.addWidget(cb)

        cb_include_settings.setStyleSheet("QCheckBox { color: #5A6B7C; font-weight: 600; padding: 0px 0px 2px 18px; }")
        dlg_layout.addWidget(cb_include_settings)
        cb_include_players.setStyleSheet("QCheckBox { color: #5A6B7C; font-weight: 600; padding: 0px 0px 2px 18px; }")
        dlg_layout.addWidget(cb_include_players)

        hint = QLabel(
            "Notes: 'Demos' removes raw demo files, 'Parsed payloads' removes cached parsed files,\n"
            "'Database' resets internomat.db and recreates a clean schema. Settings and player-list are kept unless explicitly included."
        )
        hint.setStyleSheet("font-size: 11px; color: #5A6B7C;")
        dlg_layout.addWidget(hint)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setEnabled(False)
        delete_btn.setStyleSheet(
            "QPushButton { background-color: #C73A3A; color: #FFFFFF; border: none; "
            "border-radius: 8px; padding: 6px 12px; font-weight: 700; } "
            "QPushButton:disabled { background-color: #E6B8B8; color: #F8F3F3; }"
        )
        button_row.addWidget(cancel_btn)
        button_row.addWidget(delete_btn)
        dlg_layout.addLayout(button_row)

        def _update_delete_enabled(*_args):
            delete_btn.setEnabled(any((cb_demos.isChecked(), cb_parsed.isChecked(), cb_logs.isChecked(), cb_database.isChecked())))
            allow_settings_toggle = cb_database.isChecked()
            cb_include_settings.setEnabled(allow_settings_toggle)
            cb_include_players.setEnabled(allow_settings_toggle)
            if not allow_settings_toggle:
                cb_include_settings.setChecked(False)
                cb_include_players.setChecked(False)

        for cb in (cb_demos, cb_parsed, cb_logs, cb_database):
            cb.stateChanged.connect(_update_delete_enabled)

        cancel_btn.clicked.connect(dialog.reject)

        def _delete_dir_contents(path_obj, exclude_names=None):
            exclude = set(exclude_names or [])
            deleted = 0
            if not path_obj.exists():
                return deleted

            for item in path_obj.iterdir():
                if item.name in exclude:
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    deleted += 1
                except Exception as exc:
                    logger.log_error(f"[CLEANUP] Failed to delete {item}: {exc}")
            return deleted

        def _perform_delete():
            confirm = QMessageBox.question(
                dialog,
                "Confirm Delete",
                "Delete selected data now? This action cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            total_deleted = 0

            selected_demos = cb_demos.isChecked()
            selected_parsed = cb_parsed.isChecked()
            selected_logs = cb_logs.isChecked()
            selected_database = cb_database.isChecked()
            selected_include_settings = cb_include_settings.isChecked()
            selected_include_players = cb_include_players.isChecked()
            requires_restart = bool(selected_database)

            if selected_demos and selected_parsed:
                total_deleted += demo_cache.clear_cache(demos_dir)
                io_service.clear_demo_flags()
            elif selected_demos:
                total_deleted += _delete_dir_contents(demos_dir, exclude_names={"parsed"})
                io_service.clear_demo_flags()
            elif selected_parsed:
                total_deleted += demo_cache.clear_cache(parsed_dir)
                io_service.clear_demo_flags()

            if selected_logs:
                prev_export_state = bool(getattr(settings, "log_export_enabled", True))
                logger.set_log_export_enabled(False)
                total_deleted += demo_cache.clear_cache(logs_dir)
                logger.set_log_export_enabled(prev_export_state)

            if selected_database:
                settings_snapshot = []
                players_snapshot = []
                if not selected_include_settings:
                    try:
                        with get_conn() as conn:
                            rows = conn.execute("SELECT key, value FROM settings").fetchall()
                            settings_snapshot = [(str(r["key"]), str(r["value"])) for r in rows]
                    except Exception as exc:
                        logger.log_error(f"[CLEANUP] Failed to snapshot settings before DB deletion: {exc}")

                if not selected_include_players:
                    try:
                        players_snapshot = io_service.get_players_payload()
                    except Exception as exc:
                        logger.log_error(f"[CLEANUP] Failed to snapshot players before DB deletion: {exc}")

                db_deleted = 0
                for db_path in db_files:
                    try:
                        if db_path.exists():
                            db_path.unlink()
                            db_deleted += 1
                    except Exception as exc:
                        logger.log_error(f"[CLEANUP] Failed to delete database file {db_path}: {exc}")
                total_deleted += db_deleted
                try:
                    init_db()
                    if not selected_include_settings and settings_snapshot:
                        for key, value in settings_snapshot:
                            settings_db.set(key, value)
                        logger.log_info(f"[CLEANUP] Restored settings entries={len(settings_snapshot)}")

                    if not selected_include_players and players_snapshot:
                        restored_players = io_service.import_players_payload(players_snapshot)
                        logger.log_info(f"[CLEANUP] Restored player-list entries={restored_players}")

                    logger.log_info("[CLEANUP] Reinitialized database after deletion")
                except Exception as exc:
                    logger.log_error(f"[CLEANUP] Database reinitialize failed: {exc}")

            logger.log_info(f"[CLEANUP] Deleted selected data entries={total_deleted}")

            if not requires_restart:
                if callable(on_data_updated):
                    on_data_updated()
                if callable(on_players_data_updated):
                    on_players_data_updated()

            dialog.accept()

            if requires_restart:
                logger.log_info("[CLEANUP] Database changed; forcing UI restart to refresh all in-memory state")

                def _restart_ui():
                    from gui.gui import restart_window
                    restart_window()

                QTimer.singleShot(0, _restart_ui)

        delete_btn.clicked.connect(_perform_delete)
        dialog.exec()

    def sync_demos_action():
        if not sync_demos_button.isEnabled():
            return

        if not apply_form_to_settings(save=False):
            return
        sync_demos_button.clearFocus()
        sync_demos_button.setEnabled(False)

        dialog = PipelineProgressDialog("Demo Sync Progress", "Syncing demos ({stage})", parent)
        dialog.update_status({"percent": 0, "stage": "pipeline", "message": "Starting..."})

        dialog.set_running(True)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        demo_sync_progress_dialog["dialog"] = dialog

        def worker():
            try:
                integration = DemoScrapperIntegration(
                    ftp_host=settings.demo_ftp_host,
                    ftp_port=settings.demo_ftp_port,
                    ftp_user=settings.demo_ftp_user,
                    ftp_password=settings.demo_ftp_password,
                    remote_dir=settings.demo_remote_path,
                    progress_callback=lambda payload: dispatcher.demos_sync_progress.emit(payload),
                )
                demo_data = integration.run_sync()
                dispatcher.demos_sync_finished.emit(demo_data)
            except Exception as e:
                dispatcher.demos_sync_error.emit(e)

        executor.submit(worker)

    def check_updates_action():
        if not check_updates_button.isEnabled():
            return

        check_updates_button.setEnabled(False)
        logger.log("[UPDATE_CLIENT] Checking GitHub releases for updates", level="INFO")

        def worker():
            try:
                result = update_service.check_latest_release()
                dispatcher.update_check_finished.emit(result)
            except Exception as exc:
                dispatcher.update_check_error.emit(exc)

        executor.submit(worker)

    def _download_update_action(result):
        check_updates_button.setEnabled(False)

        def worker():
            try:
                downloaded = update_service.download_and_verify_installer(result)
                dispatcher.update_download_finished.emit(downloaded)
            except Exception as exc:
                dispatcher.update_download_error.emit(exc)

        executor.submit(worker)

    def on_sync_finished():
        sync_matchzy_button.setEnabled(True)
        logger.log("[MATCHZY] Sync completed", level="INFO")

        if callable(on_update_players):
            logger.log("[UI] Trigger Team Builder update after MatchZy sync", level="DEBUG")
            on_update_players()

        if callable(on_data_updated):
            on_data_updated()

    def on_sync_error(e):
        sync_matchzy_button.setEnabled(True)

        logger.log_error(f"[MATCHZY] Sync failed: {e}", exc=e)

        logger.show_debug_popup(
            parent,
            "MatchZy Sync Failed",
            str(e),
            logger.get_log_history()
        )

    def on_demos_sync_finished(demo_data):
        sync_demos_button.setEnabled(True)
        sync_matchzy_button.setEnabled(True)
        logger.log_info(f"[DEMOS] Sync completed ({len(demo_data)} parsed maps)")

        dialog = demo_sync_progress_dialog.get("dialog")
        if dialog is not None:
            dialog.set_running(False)
            dialog.update_status({"percent": 100, "stage": "pipeline", "message": "Done"})

            def _close_dialog_later():
                current = demo_sync_progress_dialog.get("dialog")
                if current is not None:
                    current.allow_close_once()
                    current.close()
                    demo_sync_progress_dialog["dialog"] = None

            QTimer.singleShot(700, _close_dialog_later)

        def _run_post_sync_updates():
            if callable(on_data_updated):
                on_data_updated()

            if callable(on_update_players_only):
                logger.log("[UI] Trigger Team Builder player update after unified sync", level="DEBUG")
                on_update_players_only()
            elif callable(on_update_players):
                logger.log("[UI] Trigger Team Builder full update after unified sync", level="DEBUG")
                on_update_players()
            elif settings.auto_import_players_from_history and callable(on_players_updated):
                logger.log("[UI] Refresh Team Builder player pool after sync import", level="DEBUG")
                on_players_updated()
                if callable(on_players_data_updated):
                    on_players_data_updated()

        # Defer heavy refresh callbacks to keep the signal handler short and
        # allow the event loop to repaint/close progress UI first.
        QTimer.singleShot(0, _run_post_sync_updates)

    def on_demos_sync_error(e):
        sync_demos_button.setEnabled(True)
        sync_matchzy_button.setEnabled(True)
        logger.log_error(f"[DEMOS] Sync failed: {e}", exc=e)

        dialog = demo_sync_progress_dialog.get("dialog")
        if dialog is not None:
            dialog.set_running(False)
            dialog.update_status({"stage": "pipeline", "message": f"Failed: {e}"})
            dialog.allow_close_once()
            dialog.close()
            demo_sync_progress_dialog["dialog"] = None

        logger.show_debug_popup(
            parent,
            "Demo Sync Failed",
            str(e),
            logger.get_log_history()
        )

    def on_demos_sync_progress(payload):
        dialog = demo_sync_progress_dialog.get("dialog")
        if dialog is None:
            return
        dialog.update_status(payload)

    def on_update_check_finished(result):
        check_updates_button.setEnabled(True)

        title = "Update Available" if result.update_available else "No Updates"
        if result.update_available:
            msg = (
                f"Current version: {result.current_version}\n"
                f"Latest version: {result.latest_version}\n\n"
                "Download installer now?"
            )
            button = QMessageBox.question(
                parent,
                title,
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if button == QMessageBox.Yes:
                _download_update_action(result)
            logger.log(
                f"[UPDATE_CLIENT] Update available current={result.current_version} latest={result.latest_version}",
                level="INFO",
            )
            return

        QMessageBox.information(
            parent,
            title,
            f"Current version {APP_VERSION} is up to date.",
        )
        logger.log(f"[UPDATE_CLIENT] Up to date version={result.current_version}", level="INFO")

    def on_update_check_error(exc):
        check_updates_button.setEnabled(True)
        logger.log_error(f"[UPDATE_CLIENT] Update check failed: {exc}", exc=exc)
        QMessageBox.warning(parent, "Update Check Failed", str(exc))

    def on_update_download_finished(downloaded):
        check_updates_button.setEnabled(True)
        verification_status = (
            "verified with release checksums"
            if downloaded.verified_with_release_checksums
            else "downloaded (no release checksums asset found)"
        )

        msg = (
            f"Installer downloaded to:\n{downloaded.file_path}\n\n"
            f"SHA256: {downloaded.sha256}\n"
            f"Status: {verification_status}\n\n"
            "Open installer now?"
        )
        button = QMessageBox.question(
            parent,
            "Update Downloaded",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if button == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(downloaded.file_path))

        logger.log(
            f"[UPDATE_CLIENT] Installer downloaded path={downloaded.file_path} "
            f"checksum_verified={downloaded.verified_with_release_checksums}",
            level="INFO",
        )

    def on_update_download_error(exc):
        check_updates_button.setEnabled(True)
        logger.log_error(f"[UPDATE_CLIENT] Update download failed: {exc}", exc=exc)
        QMessageBox.warning(parent, "Update Download Failed", str(exc))

    # SIGNALS

    open_logs_button.clicked.connect(open_logs)
    import_settings_button.clicked.connect(import_settings_action)
    export_settings_button.clicked.connect(export_settings_action)
    save_settings_button.clicked.connect(save_settings_action)
    sync_matchzy_button.clicked.connect(sync_matchzy_action)
    sync_demos_button.clicked.connect(sync_demos_action)
    clear_cache_button.clicked.connect(clear_cache_action)
    check_updates_button.clicked.connect(check_updates_action)
    sidebar.currentRowChanged.connect(go_to_section)
    dispatcher.sync_finished.connect(on_sync_finished)
    dispatcher.sync_error.connect(on_sync_error)
    dispatcher.demos_sync_finished.connect(on_demos_sync_finished)
    dispatcher.demos_sync_error.connect(on_demos_sync_error)
    dispatcher.demos_sync_progress.connect(on_demos_sync_progress)
    dispatcher.update_check_finished.connect(on_update_check_finished)
    dispatcher.update_check_error.connect(on_update_check_error)
    dispatcher.update_download_finished.connect(on_update_download_finished)
    dispatcher.update_download_error.connect(on_update_download_error)

    sidebar.setCurrentRow(0)


