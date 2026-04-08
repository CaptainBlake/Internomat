from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from core.settings.settings import settings
from gui.tabs.settings.settings_helpers import (
    create_section,
    create_setting_row,
    small_button,
    danger_button,
    date_from_str,
)
import services.logger as logger
import db.settings_db as settings_db
from db.connection_db import get_conn
from core.stats.elo import recalculate_elo, bind_current_settings_tuning_to_season
from datetime import datetime, timedelta
import json


def build_elo_section(parent, setting_bindings, mark_dirty, sidebar, callbacks):
    """
    Build the Elo section with seasons and tuning parameters.

    callbacks: mutable dict, may later receive ``go_to_section`` entry.
        Keys used: on_data_updated, on_players_updated, on_players_data_updated

    Returns a dict with the frame and API functions/widgets.
    """
    frame, layout = create_section("Elo")

    # ---- helper: styled sub-card ------------------------------------------
    _SUBCARD_STYLE = """
        QFrame#eloSubcard {
            background: rgba(220, 234, 247, 0.35);
            border: 1px solid #C8D9EA;
            border-radius: 10px;
        }
    """

    def _make_subcard(title_text, description=None):
        card = QFrame()
        card.setObjectName("eloSubcard")
        card.setStyleSheet(_SUBCARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(10)

        title = QLabel(title_text)
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #22384D; border: none; background: transparent;")
        card_layout.addWidget(title)

        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setStyleSheet("font-size: 11px; color: #5A6B7C; border: none; background: transparent;")
            card_layout.addWidget(desc)

        return card, card_layout

    # ======================================================================
    #  SEASONS sub-card
    # ======================================================================
    seasons_card, seasons_layout = _make_subcard(
        "Seasons",
        "Season ranges are edited as dates. "
        "A new season cannot be started until the previous one has an explicit end date.",
    )
    layout.addWidget(seasons_card)

    season_warning = QLabel(
        "Season editing is locked. Unlock only for boundary planning."
    )
    season_warning.setWordWrap(True)
    season_warning.setStyleSheet("font-size: 11px; color: #A33A3A; font-weight: 700; border: none; background: transparent;")
    seasons_layout.addWidget(season_warning)

    unlock_seasons_checkbox = QCheckBox("Unlock season editing")
    unlock_seasons_checkbox.setChecked(False)
    unlock_seasons_checkbox.setStyleSheet("background: transparent; border: none;")
    seasons_layout.addWidget(unlock_seasons_checkbox)

    season_rows_layout = QVBoxLayout()
    season_rows_layout.setSpacing(8)
    seasons_layout.addLayout(season_rows_layout)
    season_rows = []
    season_edit_unlocked = {"value": False}
    tuning_widgets = []
    btn_save_tuning_ref = {"widget": None}
    tuning_warning_ref = {"widget": None}

    # ------------------------------------------------------------------ helpers

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

    def _set_date_if_changed(edit, new_date):
        if edit.date() == new_date:
            return
        was_blocked = edit.blockSignals(True)
        edit.setDate(new_date)
        edit.blockSignals(was_blocked)

    def _seasons_payload_compact(show_popup=False):
        seasons = _serialize_seasons_or_error(show_popup=show_popup)
        if seasons is None:
            return None
        return json.dumps(seasons)

    def _tuning_changed_from_settings():
        try:
            return (
                float(spin_elo_k.value()) != float(getattr(settings, "elo_k_factor", 24.0))
                or float(spin_elo_base.value()) != float(getattr(settings, "elo_base_rating", 1500.0))
                or float(spin_elo_alpha.value()) != float(getattr(settings, "elo_adr_alpha", 0.20))
                or float(spin_elo_spread.value()) != float(getattr(settings, "elo_adr_spread", 22.0))
                or float(spin_elo_min_mult.value()) != float(getattr(settings, "elo_adr_min_mult", 0.85))
                or float(spin_elo_max_mult.value()) != float(getattr(settings, "elo_adr_max_mult", 1.15))
                or float(spin_elo_prior.value()) != float(getattr(settings, "elo_adr_prior_matches", 5.0))
                or float(spin_elo_anchor.value()) != float(getattr(settings, "elo_initial_global_anchor", 80.0))
            )
        except NameError:
            return False

    def _is_today_in_any_season(seasons_payload):
        today = datetime.now().date()
        return _season_for_date(today, seasons_payload or []) is not None

    def _refresh_season_save_state():
        payload = _seasons_payload_compact(show_popup=False)
        unchanged = payload is not None and payload == str(getattr(settings, "elo_seasons_json", "[]") or "[]")
        btn_save_seasons.setEnabled(bool(season_edit_unlocked["value"]) and payload is not None and not unchanged)

    def _refresh_tuning_state():
        payload = _serialize_seasons_or_error(show_popup=False)
        in_season = _is_today_in_any_season(payload or [])
        unlocked = bool(season_edit_unlocked["value"])
        can_edit = unlocked and not in_season
        tuning_changed = _tuning_changed_from_settings()

        for widget in tuning_widgets:
            widget.setEnabled(can_edit)

        btn_save_tuning_widget = btn_save_tuning_ref.get("widget")
        if btn_save_tuning_widget is not None:
            btn_save_tuning_widget.setEnabled(can_edit and tuning_changed)

        tuning_warning = tuning_warning_ref.get("widget")
        if tuning_warning is None:
            return

        if not unlocked:
            tuning_warning.setText("Balancing is locked. Unlock season editing to edit Elo parameters.")
            tuning_warning.setStyleSheet("font-size: 12px; color: #A33A3A; font-weight: 700;")
        elif in_season:
            tuning_warning.setText("Balancing is locked during active season. Edit only in off-season.")
            tuning_warning.setStyleSheet("font-size: 12px; color: #A33A3A; font-weight: 700;")
        elif not tuning_changed:
            tuning_warning.setText("Balancing is editable (off-season). No unsaved parameter changes.")
            tuning_warning.setStyleSheet("font-size: 12px; color: #5A6B7C; font-weight: 700;")
        else:
            tuning_warning.setText("Balancing is editable (off-season). Unsaved parameter changes detected.")
            tuning_warning.setStyleSheet("font-size: 12px; color: #2E4C69; font-weight: 700;")

    def _apply_live_season_constraints():
        if not season_rows:
            return

        min_date = QDate(1900, 1, 1)
        max_date = QDate(7999, 12, 31)

        for idx, row in enumerate(season_rows):
            start_edit = row["start"]
            end_edit = row["end"]
            open_box = row["open"]

            prev_end = None
            if idx > 0:
                prev = season_rows[idx - 1]
                if not prev["open"].isChecked():
                    prev_end = prev["end"].date()

            next_start = None
            if idx + 1 < len(season_rows):
                next_start = season_rows[idx + 1]["start"].date()

            if idx > 0:
                start_min = prev_end.addDays(1) if prev_end is not None else min_date
                start_max = next_start.addDays(-1) if next_start is not None else max_date
                if start_max < start_min:
                    start_max = start_min
                start_edit.setDateRange(start_min, start_max)
                if start_edit.date() < start_min:
                    _set_date_if_changed(start_edit, start_min)
                if start_edit.date() > start_max:
                    _set_date_if_changed(start_edit, start_max)
            else:
                fixed_start = row.get("fixed_start")
                if fixed_start is not None:
                    start_qdate = _to_qdate(fixed_start)
                    _set_date_if_changed(start_edit, start_qdate)

            if idx == 0 and row.get("fixed_start") is not None:
                end_min = _to_qdate(row["fixed_start"])
            else:
                end_min = start_edit.date() if idx > 0 else min_date

            end_max = next_start.addDays(-1) if next_start is not None else max_date
            if end_max < end_min:
                end_max = end_min

            end_edit.setDateRange(end_min, end_max)

            if open_box.isChecked():
                _set_date_if_changed(end_edit, end_edit.minimumDate())
            else:
                if end_edit.date() < end_min:
                    _set_date_if_changed(end_edit, end_min)
                if end_edit.date() > end_max:
                    _set_date_if_changed(end_edit, end_max)

    def _first_match_date_or_none():
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT TRIM(COALESCE(NULLIF(end_time, ''), NULLIF(start_time, ''), NULLIF(created_at, ''), '')) AS played_at
                FROM matches
                WHERE TRIM(COALESCE(NULLIF(end_time, ''), NULLIF(start_time, ''), NULLIF(created_at, ''), '')) <> ''
                ORDER BY played_at ASC
                LIMIT 1
                """
            ).fetchone()

        raw = str((row["played_at"] if row else "") or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return datetime.fromisoformat(raw[:10]).date()
            except Exception:
                return None

    def _build_season_rows(seasons_data):
        season_rows.clear()
        _clear_layout(season_rows_layout)

        if not seasons_data:
            seasons_data = [{"season": 0, "start": _first_match_date_or_none(), "end": None}]

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
            start_edit.setMinimumDate(QDate(1900, 1, 1))
            start_edit.setDate(_to_qdate(item.get("start")))
            if idx == 0:
                start_edit.setSpecialValueText("-")
                if item.get("start") is None:
                    start_edit.setDate(start_edit.minimumDate())
            else:
                start_edit.setSpecialValueText("")

            end_edit = QDateEdit()
            end_edit.setDisplayFormat("yyyy-MM-dd")
            end_edit.setCalendarPopup(True)
            end_edit.setMinimumDate(QDate(1900, 1, 1))
            end_edit.setSpecialValueText("-")
            end_edit.setDate(_to_qdate(item.get("end")))

            open_end = QCheckBox("Open end")
            open_end.setChecked(item.get("end") is None)

            if idx == 0:
                # Season 0 is the baseline; start date is intentionally omitted.
                start_edit.setEnabled(False)

            def _toggle_end(checked, edit=end_edit, open_widget=open_end, row_idx=idx):
                if checked and row_idx < len(season_rows) - 1:
                    QMessageBox.warning(
                        parent,
                        "Invalid season setup",
                        "Only the last season can be open-ended. Close this season before creating a following one.",
                    )
                    was_blocked = open_widget.blockSignals(True)
                    open_widget.setChecked(False)
                    open_widget.blockSignals(was_blocked)
                    checked = False

                if checked:
                    edit.setDate(edit.minimumDate())
                    edit.setEnabled(False)
                else:
                    if edit.date() == edit.minimumDate():
                        edit.setDate(QDate.currentDate())
                    edit.setEnabled(True)
                _apply_live_season_constraints()
                mark_dirty()

            open_end.toggled.connect(_toggle_end)
            _toggle_end(open_end.isChecked())

            start_edit.dateChanged.connect(lambda *_args: (_apply_live_season_constraints(), mark_dirty(), _refresh_season_save_state(), _refresh_tuning_state()))
            end_edit.dateChanged.connect(lambda *_args: (_apply_live_season_constraints(), mark_dirty(), _refresh_season_save_state(), _refresh_tuning_state()))

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
                "fixed_start": item.get("start") if idx == 0 else None,
            })

        _apply_season_lock_state(season_edit_unlocked["value"])
        _apply_live_season_constraints()
        _refresh_season_save_state()
        _refresh_tuning_state()

    def _serialize_seasons_or_error(show_popup=True):
        out = []
        prev_end = None
        for idx, row in enumerate(season_rows):
            if idx == 0 and row.get("fixed_start") is not None:
                start_date = row.get("fixed_start")
            elif idx == 0:
                start_date = None
            else:
                start_date = row["start"].date().toPython()
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
            s = date_from_str(item.get("start"))
            e = date_from_str(item.get("end"))
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

    def _resolve_tuning_target_season(today_date, seasons_payload):
        active = _season_for_date(today_date, seasons_payload)
        if active is not None:
            return int(active)

        for item in seasons_payload:
            sid = int(item.get("season", 0))
            start = date_from_str(item.get("start"))
            if start is not None and start > today_date:
                return sid

        return int(seasons_payload[-1].get("season", 0)) if seasons_payload else 0

    def _recalculate_elo_safe(context_label, show_popup=False):
        try:
            result = recalculate_elo()
            logger.log_info(
                f"[ELO] Recalculated after {context_label}: "
                f"players={result.get('players_rated', 0)} matches={result.get('matches_processed', 0)} season={result.get('season', 0)}"
            )
            return True
        except Exception as exc:
            logger.log_error(f"[ELO] Recalculation failed after {context_label}: {exc}", exc=exc)
            if show_popup:
                QMessageBox.warning(
                    parent,
                    "Elo recalculation failed",
                    f"Settings were saved, but Elo recalculation failed:\n{exc}",
                )
            return False

    # ----------------------------------------------------------- season actions

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
        next_start = date_from_str(last.get("end")) + timedelta(days=1)
        seasons.append({
            "season": len(seasons),
            "start": next_start.isoformat(),
            "end": None,
        })
        parsed = []
        for s in seasons:
            parsed.append({
                "season": int(s["season"]),
                "start": date_from_str(s.get("start")),
                "end": date_from_str(s.get("end")),
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
                "start": date_from_str(s.get("start")),
                "end": date_from_str(s.get("end")),
            })
        _build_season_rows(parsed)
        mark_dirty()

    season_btn_row = QHBoxLayout()
    btn_add_season = small_button("Add Season")
    btn_remove_season = danger_button("Remove Last")
    btn_save_seasons = small_button("Save Seasons")
    season_btn_row.addWidget(btn_add_season)
    season_btn_row.addWidget(btn_remove_season)
    season_btn_row.addWidget(btn_save_seasons)
    season_btn_row.addStretch()
    seasons_layout.addLayout(season_btn_row)

    def _lock_seasons_without_sidebar_jump():
        go_to_section = callbacks.get("go_to_section")
        selected_row = sidebar.currentRow()
        if unlock_seasons_checkbox.isChecked():
            unlock_seasons_checkbox.setChecked(False)
        if selected_row >= 0 and sidebar.currentRow() != selected_row:
            blocked = sidebar.blockSignals(True)
            sidebar.setCurrentRow(selected_row)
            sidebar.blockSignals(blocked)
            if go_to_section:
                go_to_section(selected_row)

        def _focus_lock_toggle():
            if unlock_seasons_checkbox.isVisible() and unlock_seasons_checkbox.isEnabled():
                unlock_seasons_checkbox.setFocus(Qt.FocusReason.OtherFocusReason)

        QTimer.singleShot(0, _focus_lock_toggle)

    def _save_seasons_action():
        if not season_edit_unlocked["value"]:
            return

        seasons = _serialize_seasons_or_error(show_popup=True)
        if seasons is None:
            return

        payload = json.dumps(seasons)
        existing_payload = str(getattr(settings, "elo_seasons_json", "[]") or "[]")
        seasons_changed = payload != existing_payload

        settings_db.set("elo_seasons_json", payload)
        settings.elo_seasons_json = payload

        if seasons_changed:
            _recalculate_elo_safe("season save", show_popup=True)
            on_players_updated = callbacks.get("on_players_updated")
            if callable(on_players_updated):
                logger.log("[UI] Refresh Team Builder player view after season save", level="DEBUG")
                on_players_updated()
            on_players_data_updated = callbacks.get("on_players_data_updated")
            if callable(on_players_data_updated):
                on_players_data_updated()

        on_data_updated = callbacks.get("on_data_updated")
        if callable(on_data_updated):
            on_data_updated()

        if seasons_changed:
            QMessageBox.information(parent, "Seasons saved", "Season ranges were saved and applied.")

        _lock_seasons_without_sidebar_jump()
        _refresh_season_save_state()
        _refresh_tuning_state()

    def _apply_season_lock_state(checked):
        season_edit_unlocked["value"] = bool(checked)

        for idx, row in enumerate(season_rows):
            editable = bool(checked)
            row["start"].setEnabled(editable and idx > 0)
            row["open"].setEnabled(editable)
            if row["open"].isChecked():
                row["end"].setEnabled(False)
                row["end"].setDate(row["end"].minimumDate())
            else:
                row["end"].setEnabled(editable)

        btn_add_season.setEnabled(bool(checked))
        btn_remove_season.setEnabled(bool(checked))
        btn_save_seasons.setVisible(bool(checked))
        btn_save_seasons.setEnabled(bool(checked))

        btn_save_tuning_widget = btn_save_tuning_ref.get("widget")
        if btn_save_tuning_widget is not None:
            btn_save_tuning_widget.setVisible(True)

        season_warning.setVisible(not bool(checked))
        _apply_live_season_constraints()
        _refresh_season_save_state()
        _refresh_tuning_state()

    unlock_seasons_checkbox.toggled.connect(_apply_season_lock_state)

    btn_add_season.clicked.connect(_add_season_row_action)
    btn_remove_season.clicked.connect(_remove_last_season_row_action)
    btn_save_seasons.clicked.connect(_save_seasons_action)

    # -------------------------------------------------------- load initial data

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
                    "start": date_from_str(item.get("start")),
                    "end": date_from_str(item.get("end")),
                })
        _build_season_rows(parsed_rows)
    except Exception:
        _build_season_rows([])

    _apply_season_lock_state(False)

    # ======================================================================
    #  PARAMETERS sub-card
    # ======================================================================
    params_card, params_layout = _make_subcard(
        "Elo Parameters",
        "Tuning values that control how Elo ratings are calculated. "
        "Editable only during off-season with season editing unlocked.",
    )
    layout.addWidget(params_card)

    tuning_warning = QLabel(
        "Balancing lock status is evaluated live."
    )
    tuning_warning.setWordWrap(True)
    tuning_warning.setStyleSheet("font-size: 11px; color: #A33A3A; font-weight: 700; border: none; background: transparent;")
    params_layout.addWidget(tuning_warning)
    tuning_warning_ref["widget"] = tuning_warning

    spin_elo_k = QDoubleSpinBox()
    spin_elo_k.setRange(0.0, 200.0)
    spin_elo_k.setDecimals(2)
    spin_elo_k.setSingleStep(1.0)
    spin_elo_k.setValue(float(getattr(settings, "elo_k_factor", 24.0)))
    params_layout.addLayout(create_setting_row("K factor:", spin_elo_k, "elo_k_factor", setting_bindings, mark_dirty, tooltip="How many rating points are at stake per match.\nHigher values make ratings change faster."))

    spin_elo_base = QDoubleSpinBox()
    spin_elo_base.setRange(0.0, 5000.0)
    spin_elo_base.setDecimals(1)
    spin_elo_base.setSingleStep(10.0)
    spin_elo_base.setValue(float(getattr(settings, "elo_base_rating", 1500.0)))
    params_layout.addLayout(create_setting_row("Base rating:", spin_elo_base, "elo_base_rating", setting_bindings, mark_dirty, tooltip="Starting Elo rating assigned to new players\nin the Elo system."))

    spin_elo_alpha = QDoubleSpinBox()
    spin_elo_alpha.setRange(0.0, 2.0)
    spin_elo_alpha.setDecimals(3)
    spin_elo_alpha.setSingleStep(0.01)
    spin_elo_alpha.setValue(float(getattr(settings, "elo_adr_alpha", 0.20)))
    params_layout.addLayout(create_setting_row("ADR alpha:", spin_elo_alpha, "elo_adr_alpha", setting_bindings, mark_dirty, tooltip="How strongly ADR performance influences\nthe Elo adjustment. 0 = pure win/loss."))

    spin_elo_spread = QDoubleSpinBox()
    spin_elo_spread.setRange(0.1, 200.0)
    spin_elo_spread.setDecimals(2)
    spin_elo_spread.setSingleStep(1.0)
    spin_elo_spread.setValue(float(getattr(settings, "elo_adr_spread", 22.0)))
    params_layout.addLayout(create_setting_row("ADR spread:", spin_elo_spread, "elo_adr_spread", setting_bindings, mark_dirty, tooltip="Z-score denominator for ADR deviation.\nSmaller values amplify ADR impact."))

    spin_elo_min_mult = QDoubleSpinBox()
    spin_elo_min_mult.setRange(0.01, 5.0)
    spin_elo_min_mult.setDecimals(3)
    spin_elo_min_mult.setSingleStep(0.01)
    spin_elo_min_mult.setValue(float(getattr(settings, "elo_adr_min_mult", 0.85)))
    params_layout.addLayout(create_setting_row("ADR min multiplier:", spin_elo_min_mult, "elo_adr_min_mult", setting_bindings, mark_dirty, tooltip="Lower clamp for the ADR multiplier.\nPrevents excessive Elo loss from bad games."))

    spin_elo_max_mult = QDoubleSpinBox()
    spin_elo_max_mult.setRange(0.01, 5.0)
    spin_elo_max_mult.setDecimals(3)
    spin_elo_max_mult.setSingleStep(0.01)
    spin_elo_max_mult.setValue(float(getattr(settings, "elo_adr_max_mult", 1.15)))
    params_layout.addLayout(create_setting_row("ADR max multiplier:", spin_elo_max_mult, "elo_adr_max_mult", setting_bindings, mark_dirty, tooltip="Upper clamp for the ADR multiplier.\nPrevents excessive Elo gain from strong games."))

    spin_elo_prior = QDoubleSpinBox()
    spin_elo_prior.setRange(0.0, 100.0)
    spin_elo_prior.setDecimals(2)
    spin_elo_prior.setSingleStep(0.5)
    spin_elo_prior.setValue(float(getattr(settings, "elo_adr_prior_matches", 5.0)))
    params_layout.addLayout(create_setting_row("ADR prior matches:", spin_elo_prior, "elo_adr_prior_matches", setting_bindings, mark_dirty, tooltip="Bayesian smoothing weight.\nBlends a player's ADR toward the global\naverage for the first N matches."))

    spin_elo_anchor = QDoubleSpinBox()
    spin_elo_anchor.setRange(0.0, 500.0)
    spin_elo_anchor.setDecimals(2)
    spin_elo_anchor.setSingleStep(1.0)
    spin_elo_anchor.setValue(float(getattr(settings, "elo_initial_global_anchor", 80.0)))
    params_layout.addLayout(create_setting_row("Initial global anchor:", spin_elo_anchor, "elo_initial_global_anchor", setting_bindings, mark_dirty, tooltip="Fallback global ADR expectation used\nbefore enough match data exists."))

    btn_save_tuning = small_button("Save Elo Parameters")
    btn_save_tuning.setMaximumWidth(220)
    params_layout.addWidget(btn_save_tuning, alignment=Qt.AlignmentFlag.AlignLeft)
    btn_save_tuning_ref["widget"] = btn_save_tuning

    tuning_widgets.extend([
        spin_elo_k,
        spin_elo_base,
        spin_elo_alpha,
        spin_elo_spread,
        spin_elo_min_mult,
        spin_elo_max_mult,
        spin_elo_prior,
        spin_elo_anchor,
    ])

    for w in tuning_widgets:
        w.valueChanged.connect(lambda *_args: _refresh_tuning_state())

    _apply_season_lock_state(season_edit_unlocked["value"])
    _refresh_season_save_state()
    _refresh_tuning_state()

    # ---------------------------------------------------------- tuning action

    def _save_tuning_action():
        if not season_edit_unlocked["value"]:
            return

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

        seasons_now = _serialize_seasons_or_error(show_popup=True)
        if seasons_now is None:
            return

        today = datetime.now().date()
        active = _season_for_date(today, seasons_now)
        if active is not None:
            QMessageBox.warning(
                parent,
                "Blocked: active season",
                f"Today is inside Season {active}. Edit Elo balancing only during off-season.",
            )
            _refresh_tuning_state()
            return

        tuning_payload = {
            "elo_k_factor": float(spin_elo_k.value()),
            "elo_base_rating": float(spin_elo_base.value()),
            "elo_adr_alpha": float(spin_elo_alpha.value()),
            "elo_adr_spread": float(spin_elo_spread.value()),
            "elo_adr_min_mult": float(spin_elo_min_mult.value()),
            "elo_adr_max_mult": float(spin_elo_max_mult.value()),
            "elo_adr_prior_matches": float(spin_elo_prior.value()),
            "elo_initial_global_anchor": float(spin_elo_anchor.value()),
        }

        try:
            for key, value in tuning_payload.items():
                settings_db.set(key, value)
                setattr(settings, key, value)

            target_season = _resolve_tuning_target_season(today, seasons_now)
            bind_current_settings_tuning_to_season(target_season, source="settings_ui")
            _recalculate_elo_safe("tuning save", show_popup=True)

            QMessageBox.information(
                parent,
                "Elo balancing saved",
                f"Balancing parameters were saved for season {target_season} and applied.",
            )
            _refresh_tuning_state()
        except Exception as exc:
            logger.log_error(f"[ELO] Failed to save tuning: {exc}", exc=exc)
            QMessageBox.warning(parent, "Elo tuning save failed", str(exc))

    btn_save_tuning.clicked.connect(_save_tuning_action)

    # ------------------------------------------------------ public helpers

    def rebuild_seasons_from_json(json_str):
        """Rebuild season rows from a JSON string (used by settings import)."""
        try:
            loaded = json.loads(str(json_str or "[]"))
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
                    "start": date_from_str(item.get("start")),
                    "end": date_from_str(item.get("end")),
                })
        _build_season_rows(parsed_rows)

    return {
        "frame": frame,
        "serialize_seasons_or_error": _serialize_seasons_or_error,
        "tuning_changed": _tuning_changed_from_settings,
        "refresh_tuning_state": _refresh_tuning_state,
        "refresh_season_save_state": _refresh_season_save_state,
        "lock_seasons": _lock_seasons_without_sidebar_jump,
        "recalculate_elo_safe": _recalculate_elo_safe,
        "season_edit_unlocked": season_edit_unlocked,
        "spins": {
            "elo_adr_min_mult": spin_elo_min_mult,
            "elo_adr_max_mult": spin_elo_max_mult,
            "elo_adr_spread": spin_elo_spread,
        },
        "rebuild_seasons_from_json": rebuild_seasons_from_json,
    }
