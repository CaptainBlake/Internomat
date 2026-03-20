import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
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
    QSpinBox
)
from PySide6.QtGui import QFont
from services.settings import settings
from services.logger import get_log_history
import services.logger as logger
from db import export_players as db_export_players
from db import import_players as db_import_players
from services.matchzy_db import sync

LOG_WINDOW_INSTANCE = None

# SETTINGS TAB
def build_settings_tab(parent, on_players_updated=None):

    root_layout = QHBoxLayout(parent)
    root_layout.setContentsMargins(20, 20, 20, 20)
    root_layout.setSpacing(20)


    # SIDEBAR
    sidebar = QListWidget()
    sidebar.setFixedWidth(160)
    sidebar.addItems(["Debug", "Database", "Settings"])

    root_layout.addWidget(sidebar)


    # SCROLL AREA
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setSpacing(10)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(container)
    root_layout.addWidget(scroll, 1)


    # HELPERS
    def create_section(title):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #D5EEE6;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        title_label = QLabel(title)
        title_label.setContentsMargins(0, 2, 0, 2)
        title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #20443D;
        """)

        layout.addWidget(title_label)
        layout.addSpacing(4)
        return frame, layout

    def small_button(text):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setMinimumWidth(140)
        return btn


    # BUTTONS
    open_logs_button = small_button("Open Logs")
    export_players_button = small_button("Export Playerlist")
    import_players_button = small_button("Import Playerlist")
    reload_ui_button = small_button("Reload UI")
    sync_matchzy_button = small_button("Sync with Matchzy")


    # DEBUG SECTION
    debug_frame, debug_layout = create_section("Debug")

    debug_layout.addWidget(open_logs_button, alignment=Qt.AlignLeft)
    debug_layout.addWidget(reload_ui_button, alignment=Qt.AlignLeft)

    layout.addWidget(debug_frame)


    # DATABASE SECTION
    db_frame, db_layout = create_section("Database")

    db_layout.addWidget(export_players_button, alignment=Qt.AlignLeft)
    db_layout.addWidget(import_players_button, alignment=Qt.AlignLeft)
    db_layout.addWidget(sync_matchzy_button, alignment=Qt.AlignLeft)

    layout.addWidget(db_frame)


    # SETTINGS SECTION
    settings_frame, settings_layout = create_section("Settings")

    # container for this setting
    row = QHBoxLayout()
    row.setSpacing(10)

    label = QLabel("Update cooldown (minutes):")
    label.setMinimumWidth(220)
    label.setStyleSheet("""
        font-weight: 500;
        border: none;
        background: transparent;
    """)
    spin = QSpinBox()
    spin.setRange(0, 9999)
    spin.setValue(settings.update_cooldown_minutes)
    spin.setFixedWidth(100)
    spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    def on_cooldown_changed():
        value = spin.value()
        settings.update_cooldown_minutes = value

        logger.log(
            f"[SETTINGS] Cooldown set to {value}",
            level="INFO"
        )

    spin.editingFinished.connect(on_cooldown_changed)
    tooltip = "Minimum time between player updates. Set to 0 to disable cooldown.\nRecommended: 10"
    label.setToolTip(tooltip)
    spin.setToolTip(tooltip)
    row.addWidget(label)
    row.addWidget(spin)

    # DIST WEIGHT
    row2 = QHBoxLayout()
    row2.setSpacing(10)

    label2 = QLabel("Team balance weight:")
    label2.setMinimumWidth(220)
    label2.setStyleSheet("""
        font-weight: 500;
        border: none;
        background: transparent;
    """)

    spin2 = QDoubleSpinBox()
    spin2.setRange(0.0, 0.5)
    spin2.setSingleStep(0.01)
    spin2.setDecimals(2)
    spin2.setValue(settings.dist_weight)
    spin2.setFixedWidth(100)

    def on_dist_weight_changed():
        value = spin2.value()
        settings.dist_weight = value

        logger.log(
            f"[SETTINGS] dist_weight set to {value}",
            level="INFO"
        )

    spin2.editingFinished.connect(on_dist_weight_changed)
    tooltip = "Controls how strongly skill distribution affects team balancing.\nHigher = more random teams, lower = more even teams.\nRecommended: 0.25"

    label2.setToolTip(tooltip)
    spin2.setToolTip(tooltip)
    row2.addWidget(label2)
    row2.addWidget(spin2)
    row2.addStretch()

    settings_layout.addLayout(row2)

    # spacer?
    row.addStretch()

    settings_layout.addLayout(row)

    layout.addWidget(settings_frame)

    layout.addStretch()

    # WINDOW STATE
    log_window = {"instance": None}


    # ACTIONS
    def open_logs():
        global LOG_WINDOW_INSTANCE

        if LOG_WINDOW_INSTANCE is None or not LOG_WINDOW_INSTANCE.isVisible():
            LOG_WINDOW_INSTANCE = LogWindow()

        LOG_WINDOW_INSTANCE.show()
        LOG_WINDOW_INSTANCE.raise_()
        LOG_WINDOW_INSTANCE.activateWindow()

    def export_players():
        logger.log_user_action("Export Playerlist")

        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export Players",
            "players.json",
            "JSON Files (*.json)"
        )

        if not path:
            return

        db_export_players(path)

    def import_players():
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Import Players",
            "",
            "JSON Files (*.json)"
        )

        if not path:
            return

        db_import_players(path)

        if on_players_updated:
            on_players_updated()

    def reload_ui():
        logger.log_user_action("Reload UI")
        from gui import restart_window
        restart_window()

    def sync_matchzy_action():
        logger.log_user_action("Sync Matchzy")
        sync_matchzy_button.setEnabled(False)
        def run():
            try:
                sync()
                logger.log("[MATCHZY] Sync completed", level="INFO")
            except Exception as e:
                logger.log_error("[MATCHZY] Sync failed", exc=e)
            finally:
                sync_matchzy_button.setEnabled(True)

        threading.Thread(target=run, daemon=True).start()


    # SIGNALS
    open_logs_button.clicked.connect(open_logs)
    export_players_button.clicked.connect(export_players)
    import_players_button.clicked.connect(import_players)
    reload_ui_button.clicked.connect(reload_ui)
    sync_matchzy_button.clicked.connect(sync_matchzy_action)


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