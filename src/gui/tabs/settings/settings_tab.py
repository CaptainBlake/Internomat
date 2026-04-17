from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QScrollArea,
    QStackedWidget,
    QListWidget,
    QLineEdit,
    QSpinBox,
    QMessageBox,
)
from core.settings.settings import settings
from core.settings import service as settings_service
from core.update import service as update_service
from core.version import APP_VERSION
from services import executor
import services.logger as logger
from services.matchzy import sync
from services.demo_scrapper import DemoScrapperIntegration
from PySide6.QtCore import QObject, Signal
from gui.tabs.settings.log_window import open_log_window
from gui.tabs.settings.settings_helpers import small_button, danger_button
from gui.tabs.settings.general_section import build_general_section
from gui.tabs.settings.elo_section import build_elo_section
from gui.tabs.settings.matchzy_section import build_matchzy_section
from gui.tabs.settings.demos_section import build_demos_section
from gui.tabs.settings.maintenance_section import build_maintenance_section, run_clear_cache_dialog
from gui.widgets.pipeline_progress_dialog import PipelineProgressDialog
import json


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

    # RIGHT-SIDE CONTENT AREA (one section visible at a time, each in its own scroll)
    stack = QStackedWidget()
    dispatcher = SettingsDispatcher(parent)
    demo_sync_progress_dialog = {"dialog": None}
    setting_bindings = []
    settings_dirty = {"value": False}

    root_layout.addWidget(stack, 1)

    # BUTTONS

    save_buttons = []

    def _make_save_button():
        btn = small_button("Save Settings")
        btn.setEnabled(False)
        btn.setFocusPolicy(Qt.NoFocus)
        save_buttons.append(btn)
        return btn

    def _sync_save_buttons_enabled(enabled):
        for btn in save_buttons:
            btn.setEnabled(enabled)

    open_logs_button = small_button("Open Logs")
    import_settings_button = small_button("Import Settings")
    export_settings_button = small_button("Export Settings")
    sync_matchzy_button = small_button("Sync with Matchzy")
    sync_demos_button = small_button("Sync demos")
    clear_cache_button = danger_button("Cleaning")
    check_updates_button = small_button("Look for Updates")

    for btn in [
        import_settings_button,
        export_settings_button,
        sync_matchzy_button,
        sync_demos_button,
        check_updates_button,
        clear_cache_button,
    ]:
        btn.setFocusPolicy(Qt.NoFocus)

    def mark_dirty(*_args):
        settings_dirty["value"] = True
        _sync_save_buttons_enabled(True)

    # BUILD SECTIONS

    elo_callbacks = {
        "on_data_updated": on_data_updated,
        "on_players_updated": on_players_updated,
        "on_players_data_updated": on_players_data_updated,
    }

    settings_frame = build_general_section(setting_bindings, mark_dirty, _make_save_button())
    elo_api = build_elo_section(parent, setting_bindings, mark_dirty, sidebar, elo_callbacks)
    matchzy_frame = build_matchzy_section(setting_bindings, mark_dirty, _make_save_button())
    demos_frame = build_demos_section(setting_bindings, mark_dirty, _make_save_button())
    maintenance_frame = build_maintenance_section(
        open_logs_button, clear_cache_button, check_updates_button,
        import_settings_button, export_settings_button,
    )

    sections_by_key = {
        "Settings": settings_frame,
        "Elo": elo_api["frame"],
        "MatchZy": matchzy_frame,
        "Demos": demos_frame,
        "Maintenance": maintenance_frame,
    }

    for section_key in section_order:
        frame = sections_by_key.get(section_key)
        if frame is None:
            continue

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setSpacing(24)
        wrapper_layout.setAlignment(Qt.AlignTop)
        wrapper_layout.addWidget(frame)
        wrapper_layout.addStretch()
        scroll.setWidget(wrapper)

        stack.addWidget(scroll)
        section_frames.append(frame)

    def go_to_section(index):
        if index < 0 or index >= stack.count():
            return
        stack.setCurrentIndex(index)

    elo_callbacks["go_to_section"] = go_to_section

    # SHARED HELPERS

    tuning_setting_keys = {
        "elo_k_factor",
        "elo_base_rating",
        "elo_adr_alpha",
        "elo_adr_spread",
        "elo_adr_min_mult",
        "elo_adr_max_mult",
        "elo_adr_prior_matches",
        "elo_initial_global_anchor",
    }

    def read_widget_value(widget):
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return widget.value()

    def apply_form_to_settings(save=False, include_tuning=True):
        for attr_name, widget in setting_bindings:
            if not include_tuning and attr_name in tuning_setting_keys:
                continue
            setattr(settings, attr_name, read_widget_value(widget))

        seasons = elo_api["serialize_seasons_or_error"](show_popup=True)
        if seasons is None:
            return False
        settings.elo_seasons_json = json.dumps(seasons)

        if save:
            settings.save()
        return True

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
            elo_api["rebuild_seasons_from_json"](payload.get("elo_seasons_json"))

    # ACTIONS

    def save_settings_action():
        spins = elo_api["spins"]

        if float(spins["elo_adr_min_mult"].value()) > float(spins["elo_adr_max_mult"].value()):
            QMessageBox.warning(
                parent,
                "Invalid Elo tuning",
                "ADR min multiplier cannot be greater than ADR max multiplier.",
            )
            return

        if float(spins["elo_adr_spread"].value()) <= 0:
            QMessageBox.warning(
                parent,
                "Invalid Elo tuning",
                "ADR spread must be greater than 0.",
            )
            return

        tuning_changed = elo_api["tuning_changed"]()

        seasons_before_raw = str(getattr(settings, "elo_seasons_json", "[]") or "[]")
        try:
            seasons_before = json.loads(seasons_before_raw)
        except Exception:
            seasons_before = []

        seasons_now = elo_api["serialize_seasons_or_error"](show_popup=True)
        if seasons_now is None:
            return

        seasons_changed = seasons_now != seasons_before

        if not apply_form_to_settings(save=True, include_tuning=False):
            return

        if seasons_changed:
            elo_api["recalculate_elo_safe"]("settings save", show_popup=True)
            if callable(on_players_updated):
                logger.log("[UI] Refresh Team Builder player view after season change in settings save", level="DEBUG")
                on_players_updated()
            if callable(on_players_data_updated):
                on_players_data_updated()

        if callable(on_players_updated):
            on_players_updated()

        logger.set_log_export_enabled(bool(getattr(settings, "log_export_enabled", True)))
        if tuning_changed:
            QMessageBox.information(
                parent,
                "Tuning not saved",
                "General settings were saved. Use 'Save Elo Parameters' to persist tuning changes.",
            )
            settings_dirty["value"] = True
            _sync_save_buttons_enabled(True)
        else:
            settings_dirty["value"] = False
            _sync_save_buttons_enabled(False)
        elo_api["lock_seasons"]()
        elo_api["refresh_season_save_state"]()
        elo_api["refresh_tuning_state"]()
        logger.log("[SETTINGS] Saved", level="INFO")

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
        seasons = elo_api["serialize_seasons_or_error"](show_popup=True)
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
            _sync_save_buttons_enabled(False)
            logger.log_info(f"[SETTINGS] Imported from {path}")

            if callable(on_data_updated):
                on_data_updated()

        except Exception as e:
            logger.log_error(f"[SETTINGS] Import failed: {e}")

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
        run_clear_cache_dialog(parent, on_data_updated, on_players_data_updated)

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
        include_unstable = bool(getattr(settings, "update_include_unstable", False))
        logger.log(f"[UPDATE_CLIENT] Checking GitHub releases for updates (unstable={include_unstable})", level="INFO")

        def worker():
            try:
                result = update_service.check_latest_release(include_unstable=include_unstable)
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

    # SIGNAL HANDLERS

    def on_sync_finished():
        sync_matchzy_button.setEnabled(True)
        logger.log("[MATCHZY] Sync completed", level="INFO")

        executor.submit(lambda: elo_api["recalculate_elo_safe"]("MatchZy sync", show_popup=False))

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
            executor.submit(lambda: elo_api["recalculate_elo_safe"]("demo sync", show_popup=False))

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

    open_logs_button.clicked.connect(lambda: open_log_window(parent))
    import_settings_button.clicked.connect(import_settings_action)
    export_settings_button.clicked.connect(export_settings_action)
    for _btn in save_buttons:
        _btn.clicked.connect(save_settings_action)
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
