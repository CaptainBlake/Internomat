import threading
import json

from PySide6.QtCore import Qt, QTimer
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
    QTextEdit,
    QFileDialog,
    QScrollArea,
    QFrame,
    QListWidget,
    QLineEdit,
    QGridLayout,
    QSpinBox,
    QDialog,
    QProgressBar,
    QMessageBox,
)
from PySide6.QtGui import QFont
from core.settings.settings import settings
from services import executor
from services.logger import get_log_history
import services.logger as logger
from db.IO_db import export_players as db_export_players
from db.IO_db import import_players as db_import_players
from services.matchzy import sync
from services.demo_scrapper import DemoScrapperIntegration
from services import demo_cache
from PySide6.QtCore import QObject, Signal

class SettingsDispatcher(QObject):
    sync_finished = Signal()
    sync_error = Signal(object)
    sync_all_error = Signal(object)
    demos_sync_finished = Signal(object)
    demos_sync_error = Signal(object)
    demos_sync_progress = Signal(object)


LOG_WINDOW_INSTANCE = None


class DemoSyncProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Demo Sync Progress")
        self.setModal(False)
        self.resize(540, 190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.title_label = QLabel("Syncing demos...")
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #22384D;")

        self.message_label = QLabel("Starting pipeline...")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("font-size: 12px; color: #5A6B7C;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")

        self.file_label = QLabel("Current file: -")
        self.file_label.setStyleSheet("font-size: 11px; color: #5A6B7C;")

        self.file_progress = QProgressBar()
        self.file_progress.setRange(0, 100)
        self.file_progress.setValue(0)
        self.file_progress.setFormat("%p%")

        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.file_label)
        layout.addWidget(self.file_progress)

    def update_status(self, payload):
        if not isinstance(payload, dict):
            return

        percent = payload.get("percent")
        file_percent = payload.get("file_percent")
        message = str(payload.get("message") or "")
        stage = str(payload.get("stage") or "pipeline")

        if isinstance(percent, (int, float)):
            self.progress.setValue(max(0, min(100, int(percent))))

        if stage:
            self.title_label.setText(f"Syncing demos ({stage})")

        if message:
            self.message_label.setText(message)

        if isinstance(file_percent, (int, float)):
            value = max(0, min(100, int(file_percent)))
            self.file_progress.setValue(value)
            self.file_label.setText(f"Current file: {value}%")
        elif stage != "ftp":
            self.file_progress.setValue(0)
            self.file_label.setText("Current file: -")

# SETTINGS TAB
def build_settings_tab(parent, on_players_updated=None, on_data_updated=None):

    section_order = ["Debug", "Settings", "Database", "MatchZy", "Demos"]

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

    import_players_button = small_button("Import Playerlist")
    export_players_button = small_button("Export Playerlist")
    import_settings_button = small_button("Import Settings")
    export_settings_button = small_button("Export Settings")
    save_settings_button = small_button("Save Settings")

    sync_matchzy_button = small_button("Sync with Matchzy")
    sync_demos_button = small_button("Sync demos")
    sync_all_button = small_button("Sync")
    clear_cache_button = danger_button("Clear Cache")

    for btn in [
        import_players_button,
        export_players_button,
        import_settings_button,
        export_settings_button,
        save_settings_button,
        sync_matchzy_button,
        sync_demos_button,
        sync_all_button,
        clear_cache_button,
    ]:
        btn.setFocusPolicy(Qt.NoFocus)

    save_settings_button.setEnabled(False)


    # SECTIONS

    # DEBUG
    debug_frame = create_grid_section("Debug", [
        [open_logs_button, sync_matchzy_button, sync_demos_button]
    ], columns=3)

    # DATABASE
    database_frame = create_grid_section("Database", [
        [import_players_button, import_settings_button],
        [export_players_button, export_settings_button],
        [sync_all_button, clear_cache_button],
    ])

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

    settings_button_row = QHBoxLayout()
    settings_button_row.setSpacing(10)
    settings_button_row.addWidget(save_settings_button)
    settings_button_row.addStretch()
    settings_layout.addLayout(settings_button_row)

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
        "Debug": debug_frame,
        "Database": database_frame,
        "Settings": settings_frame,
        "MatchZy": matchzy_frame,
        "Demos": demos_frame,
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
        global LOG_WINDOW_INSTANCE
        if LOG_WINDOW_INSTANCE is None or not LOG_WINDOW_INSTANCE.isVisible():
            LOG_WINDOW_INSTANCE = LogWindow()
        LOG_WINDOW_INSTANCE.show()
        LOG_WINDOW_INSTANCE.raise_()
        LOG_WINDOW_INSTANCE.activateWindow()

    def import_players():
        path, _ = QFileDialog.getOpenFileName(parent, "Import Players", "", "JSON Files (*.json)")
        if path:
            db_import_players(path)
            if on_players_updated:
                on_players_updated()

    def export_players():
        path, _ = QFileDialog.getSaveFileName(parent, "Export Players", "players.json", "JSON Files (*.json)")
        if path:
            db_export_players(path)

    def export_settings_action():
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export Settings",
            "internomat_settings.json",
            "JSON Files (*.json)",
        )
        if not path:
            return

        payload = {attr_name: read_widget_value(widget) for attr_name, widget in setting_bindings}

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.log_info(f"[SETTINGS] Exported to {path}")
        except Exception as e:
            logger.log_error(f"[SETTINGS] Export failed: {e}")

    def import_settings_action():
        path, _ = QFileDialog.getOpenFileName(parent, "Import Settings", "", "JSON Files (*.json)")
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
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            if not isinstance(payload, dict):
                raise ValueError("Invalid settings file format")

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

            apply_form_to_settings(save=True)
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

        if save:
            settings.save()

    def save_settings_action():
        apply_form_to_settings(save=True)
        settings_dirty["value"] = False
        save_settings_button.setEnabled(False)
        logger.log("[SETTINGS] Saved", level="INFO")

    def sync_matchzy_action():
        if not sync_matchzy_button.isEnabled():
            return

        apply_form_to_settings(save=False)
        sync_matchzy_button.setEnabled(False)

        def worker():
            try:
                sync()
                dispatcher.sync_finished.emit()
            except Exception as e:
                dispatcher.sync_error.emit(e)

        executor.submit(worker)

    def sync_all_action():
        if not sync_all_button.isEnabled():
            return

        apply_form_to_settings(save=False)
        sync_all_button.setEnabled(False)
        sync_matchzy_button.setEnabled(False)
        sync_demos_button.setEnabled(False)

        dialog = DemoSyncProgressDialog(parent)
        dialog.update_status({"percent": 0, "stage": "matchzy", "message": "Starting MatchZy sync..."})
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        demo_sync_progress_dialog["dialog"] = dialog

        def worker():
            try:
                dispatcher.demos_sync_progress.emit(
                    {"percent": 5, "stage": "matchzy", "message": "Syncing MatchZy database..."}
                )
                sync()
                dispatcher.demos_sync_progress.emit(
                    {"percent": 15, "stage": "matchzy", "message": "MatchZy sync completed. Starting demos..."}
                )

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
                dispatcher.sync_all_error.emit(e)

        executor.submit(worker)

    def clear_cache_action():
        confirm = QMessageBox.question(
            parent,
            "Confirm Cache Clear",
            "This will delete all content inside the demos folder. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            logger.log_info("Cache clear cancelled by user.")
            return

        try:
            deleted = demo_cache.clear_cache_default()
            from db.matches_db import set_demo_flags_by_match_ids
            set_demo_flags_by_match_ids(set())  # Clear all demo flags
            logger.log_info(f"Cleared cache: {deleted} files deleted. Demo flags reset.")
            if on_data_updated:
                on_data_updated()
        except Exception as e:
            logger.log_error(f"Failed to clear cache: {e}")

    def sync_demos_action():
        if not sync_demos_button.isEnabled():
            return

        apply_form_to_settings(save=False)
        sync_demos_button.clearFocus()
        sync_demos_button.setEnabled(False)

        dialog = DemoSyncProgressDialog(parent)
        dialog.update_status({"percent": 0, "stage": "pipeline", "message": "Starting pipeline..."})
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

    def on_sync_finished():
        sync_matchzy_button.setEnabled(True)
        logger.log("[MATCHZY] Sync completed", level="INFO")
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

    def on_sync_all_error(e):
        sync_all_button.setEnabled(True)
        sync_matchzy_button.setEnabled(True)
        sync_demos_button.setEnabled(True)

        dialog = demo_sync_progress_dialog.get("dialog")
        if dialog is not None:
            dialog.update_status({"stage": "pipeline", "message": f"Failed: {e}"})
            dialog.close()
            demo_sync_progress_dialog["dialog"] = None

        logger.log_error(f"[SYNC] Unified sync failed: {e}", exc=e)

        logger.show_debug_popup(
            parent,
            "Unified Sync Failed",
            str(e),
            logger.get_log_history()
        )

    def on_demos_sync_finished(demo_data):
        sync_demos_button.setEnabled(True)
        sync_matchzy_button.setEnabled(True)
        sync_all_button.setEnabled(True)
        logger.log_info(f"[DEMOS] Sync completed ({len(demo_data)} parsed maps)")

        dialog = demo_sync_progress_dialog.get("dialog")
        if dialog is not None:
            dialog.update_status({"percent": 100, "stage": "pipeline", "message": "Pipeline completed."})

            def _close_dialog_later():
                current = demo_sync_progress_dialog.get("dialog")
                if current is not None:
                    current.close()
                    demo_sync_progress_dialog["dialog"] = None

            QTimer.singleShot(700, _close_dialog_later)

        if callable(on_data_updated):
            on_data_updated()

    def on_demos_sync_error(e):
        sync_demos_button.setEnabled(True)
        sync_matchzy_button.setEnabled(True)
        sync_all_button.setEnabled(True)
        logger.log_error(f"[DEMOS] Sync failed: {e}", exc=e)

        dialog = demo_sync_progress_dialog.get("dialog")
        if dialog is not None:
            dialog.update_status({"stage": "pipeline", "message": f"Failed: {e}"})
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

    # SIGNALS

    open_logs_button.clicked.connect(open_logs)
    import_players_button.clicked.connect(import_players)
    export_players_button.clicked.connect(export_players)
    import_settings_button.clicked.connect(import_settings_action)
    export_settings_button.clicked.connect(export_settings_action)
    save_settings_button.clicked.connect(save_settings_action)
    sync_all_button.clicked.connect(sync_all_action)
    sync_matchzy_button.clicked.connect(sync_matchzy_action)
    sync_demos_button.clicked.connect(sync_demos_action)
    clear_cache_button.clicked.connect(clear_cache_action)
    sidebar.currentRowChanged.connect(go_to_section)
    dispatcher.sync_finished.connect(on_sync_finished)
    dispatcher.sync_error.connect(on_sync_error)
    dispatcher.sync_all_error.connect(on_sync_all_error)
    dispatcher.demos_sync_finished.connect(on_demos_sync_finished)
    dispatcher.demos_sync_error.connect(on_demos_sync_error)
    dispatcher.demos_sync_progress.connect(on_demos_sync_progress)

    sidebar.setCurrentRow(0)


        

# LOG WINDOW 
class LogWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Internomat Logs")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        # TOP BAR

        top = QHBoxLayout()

        self.log_mode = QComboBox()
        self.log_mode.addItems(["INFO", "DEBUG", "ERROR"])
        font = self.log_mode.font()
        font.setPointSize(10)

        self.log_mode.setFont(font)
        self.log_mode.view().setFont(font)
        top.addStretch(1)
        top.addWidget(QLabel("Log Mode:"))
        top.addWidget(self.log_mode)

        layout.addLayout(top)

        # LOG VIEW

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)

        layout.addWidget(self.log_view)

        self.last_snapshot = ""

        # SIGNALS

        self.log_mode.currentTextChanged.connect(self.reload_logs)

        # LOGGER SUBSCRIBE

        logger.subscribe(self.append_log)

        # INITIAL LOAD

        self.reload_logs()

    # ACTIONS

    def filter_logs(self, logs):
        mode = self.log_mode.currentText()

        if mode == "INFO":
            return [l for l in logs if "[DEBUG]" not in l]

        if mode == "ERROR":
            return [l for l in logs if "[ERROR]" in l]

        return logs

    def reload_logs(self):
        logs = get_log_history()
        filtered = self.filter_logs(logs)

        new_text = "\n".join(filtered)

        if new_text == self.last_snapshot:
            return

        self.last_snapshot = new_text

        self.log_view.setPlainText(new_text)

        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def append_log(self, entry):
        mode = self.log_mode.currentText()

        if mode == "ERROR":
            if "[ERROR]" not in entry:
                return

        elif mode == "INFO":
            if "[DEBUG]" in entry:
                return

        self.log_view.append(entry)

        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        global LOG_WINDOW_INSTANCE
        LOG_WINDOW_INSTANCE = None

        logger.unsubscribe(self.append_log)
        super().closeEvent(event)