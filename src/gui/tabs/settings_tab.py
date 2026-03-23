import threading

from PySide6.QtCore import Qt
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
    QSpinBox
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
from PySide6.QtCore import QObject, Signal

class SettingsDispatcher(QObject):
    sync_finished = Signal()
    sync_error = Signal(object)
    demos_sync_finished = Signal(object)
    demos_sync_error = Signal(object)


LOG_WINDOW_INSTANCE = None

# SETTINGS TAB
def build_settings_tab(parent, on_players_updated=None):

    root_layout = QHBoxLayout(parent)
    root_layout.setContentsMargins(20, 20, 20, 20)
    root_layout.setSpacing(20)

    # SIDEBAR
    sidebar = QListWidget()
    sidebar.setFixedWidth(170)
    sidebar.addItems(["Debug", "Database", "Settings", "MatchZy", "Demos"])
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
        layout.addWidget(frame)

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

        def update():
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                value = widget.text()
            else:
                value = widget.value()

            setattr(settings, attr_name, value)
            settings.save() 
            redacted_value =logger.redact(value)
            logger.log(f"[SETTINGS] {attr_name} set to {redacted_value}", level="INFO")


        if isinstance(widget, QCheckBox):
            widget.stateChanged.connect(update)
        elif isinstance(widget, QLineEdit):
            widget.editingFinished.connect(update)
        else:
            widget.editingFinished.connect(update)

        row.addWidget(label)
        row.addWidget(widget)
        row.addStretch()

        return row

    # BUTTONS

    open_logs_button = small_button("Open Logs")
    reload_ui_button = small_button("Reload UI")

    import_players_button = small_button("Import Playerlist")
    export_players_button = small_button("Export Playerlist")

    import_db_button = small_button("Import Database")
    export_db_button = small_button("Export Database")

    sync_matchzy_button = small_button("Sync with Matchzy")
    sync_demos_button = small_button("Sync demos")

    # disable DB buttons for now
    import_db_button.setEnabled(False)
    export_db_button.setEnabled(False)


    # SECTIONS

    # DEBUG
    create_grid_section("Debug", [
        [open_logs_button, reload_ui_button]
    ], columns=2)

    # DATABASE
    create_grid_section("Database", [
        [import_players_button, import_db_button, None],
        [export_players_button, export_db_button, None]
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

    layout.addWidget(settings_frame)
    layout.addStretch()

    # allow uneven teams
    checkbox_uneven = QCheckBox()
    checkbox_uneven.setChecked(settings.allow_uneven_teams)

    settings_layout.addLayout(create_setting_row(
        "Allow uneven teams:",
        checkbox_uneven,
        "allow_uneven_teams",
        "Allow uneven teams (e.g. 3 vs 2)"
    ))

    # MATCHZY SETTINGS
    matchzy_frame, matchzy_layout = create_section("MatchZy Database")

    info_label = QLabel(
        "Requires MatchZy to be configured with a MySQL database.\n"
        "See MatchZy documentation for setup:\nhttps://shobhit-pathak.github.io/MatchZy/database_stats/#using-mysql-database-with-matchzy"
    )
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

    matchzy_layout.addSpacing(10)
    matchzy_layout.addWidget(sync_matchzy_button)
    
    layout.addWidget(matchzy_frame)

    # DEMOS SETTINGS
    demos_frame, demos_layout = create_section("Demos")

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

    demos_layout.addSpacing(10)
    demos_layout.addWidget(sync_demos_button)

    layout.addWidget(demos_frame)
    
    # ACTIONS

    def open_logs():
        global LOG_WINDOW_INSTANCE
        if LOG_WINDOW_INSTANCE is None or not LOG_WINDOW_INSTANCE.isVisible():
            LOG_WINDOW_INSTANCE = LogWindow()
        LOG_WINDOW_INSTANCE.show()
        LOG_WINDOW_INSTANCE.raise_()
        LOG_WINDOW_INSTANCE.activateWindow()

    def reload_ui():
        logger.log_user_action("Reload UI")
        from gui.gui import restart_window
        restart_window()

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

    def sync_matchzy_action():
        if not sync_matchzy_button.isEnabled():
            return

        sync_matchzy_button.setEnabled(False)

        def worker():
            try:
                sync()
                dispatcher.sync_finished.emit()
            except Exception as e:
                dispatcher.sync_error.emit(e)

        executor.submit(worker)

    def sync_demos_action():
        if not sync_demos_button.isEnabled():
            return

        sync_demos_button.setEnabled(False)

        def worker():
            try:
                integration = DemoScrapperIntegration(
                    ftp_host=settings.demo_ftp_host,
                    ftp_port=settings.demo_ftp_port,
                    ftp_user=settings.demo_ftp_user,
                    ftp_password=settings.demo_ftp_password,
                    remote_dir=settings.demo_remote_path,
                )
                demo_data = integration.run_sync()
                dispatcher.demos_sync_finished.emit(demo_data)
            except Exception as e:
                dispatcher.demos_sync_error.emit(e)

        executor.submit(worker)

    def on_sync_finished():
        sync_matchzy_button.setEnabled(True)
        logger.log("[MATCHZY] Sync completed", level="INFO")

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
        logger.log_info(f"[DEMOS] Sync completed ({len(demo_data)} parsed maps)")

    def on_demos_sync_error(e):
        sync_demos_button.setEnabled(True)
        logger.log_error(f"[DEMOS] Sync failed: {e}", exc=e)
        logger.show_debug_popup(
            parent,
            "Demo Sync Failed",
            str(e),
            logger.get_log_history()
        )

    # SIGNALS

    open_logs_button.clicked.connect(open_logs)
    reload_ui_button.clicked.connect(reload_ui)
    import_players_button.clicked.connect(import_players)
    export_players_button.clicked.connect(export_players)
    sync_matchzy_button.clicked.connect(sync_matchzy_action)
    sync_demos_button.clicked.connect(sync_demos_action)
    dispatcher.sync_finished.connect(on_sync_finished)
    dispatcher.sync_error.connect(on_sync_error)
    dispatcher.demos_sync_finished.connect(on_demos_sync_finished)
    dispatcher.demos_sync_error.connect(on_demos_sync_error)


        

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