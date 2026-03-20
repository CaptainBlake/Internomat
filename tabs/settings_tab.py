import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QGridLayout,
    QSpinBox
)
from PySide6.QtGui import QFont
from services.settings import settings
from services.logger import get_log_history
import services.logger as logger
from db.IO import export_players as db_export_players
from db.IO import import_players as db_import_players
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
    layout.setAlignment(Qt.AlignTop)

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

        section_layout = QVBoxLayout(frame)
        section_layout.setContentsMargins(12, 8, 12, 8)
        section_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #20443D;
        """)

        section_layout.addWidget(title_label)
        return frame, section_layout

    def small_button(text):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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

        label = QLabel(label_text + ":")
        label.setFixedWidth(220) 
        label.setStyleSheet("font-weight: 500;")

        if tooltip:
            label.setToolTip(tooltip)
            widget.setToolTip(tooltip)

        if isinstance(widget, QCheckBox):
            def update():
                value = widget.isChecked()
                setattr(settings, attr_name, value)

                logger.log(
                    f"[SETTINGS] {attr_name} set to {value}",
                    level="INFO"
                )

            widget.stateChanged.connect(update)

        else:
            def update():
                value = widget.value()
                setattr(settings, attr_name, value)

                logger.log(
                    f"[SETTINGS] {attr_name} set to {value}",
                    level="INFO"
                )

            widget.editingFinished.connect(update)

        if not isinstance(widget, QCheckBox):
            widget.setFixedWidth(100)

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
        [import_players_button, import_db_button, sync_matchzy_button],
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
        from gui import restart_window
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
    reload_ui_button.clicked.connect(reload_ui)
    import_players_button.clicked.connect(import_players)
    export_players_button.clicked.connect(export_players)
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