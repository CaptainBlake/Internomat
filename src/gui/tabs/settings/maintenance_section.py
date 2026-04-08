from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from gui.tabs.settings.settings_helpers import create_section
from core.settings.settings import settings
from core import io_service
from core.pathing import data_path
from db.connection_db import DB_FILE, get_conn
from db.init_db import init_db
import db.settings_db as settings_db
from services import demo_cache
import services.logger as logger
from pathlib import Path
import shutil


def build_maintenance_section(open_logs_btn, clear_cache_btn, check_updates_btn,
                              import_settings_btn, export_settings_btn):
    """Build the Maintenance section frame. Returns the frame."""
    frame, layout = create_section("Maintenance")

    for btn in [open_logs_btn, clear_cache_btn, check_updates_btn,
                import_settings_btn, export_settings_btn]:
        btn.setMaximumWidth(300)
        layout.addWidget(btn)

    return frame


def run_clear_cache_dialog(parent, on_data_updated=None, on_players_data_updated=None):
    """Show the clear-cache / delete-data dialog."""
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
