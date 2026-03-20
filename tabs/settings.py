from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTextEdit
)
from PySide6.QtGui import QFont

from services.logger import get_log_history
import services.logger as logger
from PySide6.QtWidgets import QFileDialog
from db import export_players as db_export_players
from db import import_players as db_import_players


# SETTINGS TAB

def build_settings_tab(parent, on_players_updated=None):

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(10)

    # TOP BAR

    top_layout = QHBoxLayout()

    open_logs_button = QPushButton("Open Logs")
    export_players_button = QPushButton("Export Playerlist")
    import_players_button = QPushButton("Import Playerlist")

    top_layout.addWidget(open_logs_button)
    top_layout.addWidget(export_players_button)
    top_layout.addWidget(import_players_button)

    top_layout.addStretch(1)

    layout.addLayout(top_layout)

    layout.addStretch(1)

    # WINDOW STATE

    log_window = {"instance": None}

    # ACTIONS

    def open_logs():
        if log_window["instance"] is None:
            log_window["instance"] = LogWindow()

        log_window["instance"].show()
        log_window["instance"].raise_()
        log_window["instance"].activateWindow()

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
        


    # SIGNALS

    open_logs_button.clicked.connect(open_logs)
    export_players_button.clicked.connect(export_players)
    import_players_button.clicked.connect(import_players)


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
        # self.log_view.setStyleSheet("font-family: Consolas; font-size: 10pt;")

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

        # DEBUG: allow everything

        self.log_view.append(entry)

        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        logger.unsubscribe(self.append_log)
        super().closeEvent(event)