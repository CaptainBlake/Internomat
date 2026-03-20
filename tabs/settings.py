from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QTextEdit,
    QComboBox
)

from services.logger import get_log_history
import services.logger as logger


def build_settings_tab(parent):

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(10)

    # TOP BAR

    top_frame = QFrame()
    top_layout = QHBoxLayout(top_frame)
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(8)

    refresh_logs_button = QPushButton("Refresh Logs")
    clear_logs_button = QPushButton("Clear Logs")
    export_players_button = QPushButton("Export Playerlist")

    # --- log mode selector ---
    log_mode = QComboBox()
    log_mode.addItems(["ALL", "INFO", "DEBUG", "ERROR"])

    top_layout.addWidget(refresh_logs_button)
    top_layout.addWidget(clear_logs_button)
    top_layout.addWidget(export_players_button)
    top_layout.addStretch(1)
    top_layout.addWidget(QLabel("Log Mode:"))
    top_layout.addWidget(log_mode)

    layout.addWidget(top_frame)

    # LOG VIEWER

    log_frame = QFrame()
    log_frame.setStyleSheet("""
        QFrame {
            background: #ECEFF1;
            border-radius: 12px;
        }
    """)

    log_layout = QVBoxLayout(log_frame)
    log_layout.setContentsMargins(12, 12, 12, 12)

    log_title = QLabel("Debug Log")
    log_title.setAlignment(Qt.AlignmentFlag.AlignLeft)

    log_view = QTextEdit()
    from PySide6.QtGui import QFont

    font = QFont("Consolas")
    font.setPointSize(10)
    log_view.setFont(font)
    log_view.setReadOnly(True)
    log_view.setMaximumHeight(500)  
    log_view.setLineWrapMode(QTextEdit.NoWrap)
    log_layout.addWidget(log_title)
    log_layout.addWidget(log_view)

    layout.addWidget(log_frame)

    layout.addStretch(1)

    # ACTIONS

    def filter_logs(logs, mode):
        if mode == "ALL":
            return logs
        return [l for l in logs if f"[{mode}]" in l]

    last_log_snapshot = {"text": ""}

    def load_logs():
        logs = get_log_history()
        mode = log_mode.currentText()

        filtered = filter_logs(logs, mode)
        new_text = "\n".join(filtered)

        if new_text == last_log_snapshot["text"]:
            return

        last_log_snapshot["text"] = new_text

        log_view.setPlainText(new_text)

        log_view.verticalScrollBar().setValue(
            log_view.verticalScrollBar().maximum()
        )


    def clear_logs():
        log_view.clear()
        logger.log("[UI] Logs cleared (view only)", level="DEBUG")

    def export_players():
        logger.log_user_action("Export Playerlist")

        # placeholder
        logger.log("[UI] Export playerlist triggered", level="INFO")

    def append_log(entry):
        mode = log_mode.currentText()

        if mode != "ALL" and f"[{mode}]" not in entry:
            return

        log_view.append(entry)

        log_view.verticalScrollBar().setValue(
            log_view.verticalScrollBar().maximum()
        )

    def cleanup():
        logger.unsubscribe(append_log)


    # SIGNALS
    logger.subscribe(append_log)
    refresh_logs_button.clicked.connect(load_logs)
    clear_logs_button.clicked.connect(clear_logs)
    export_players_button.clicked.connect(export_players)
    log_mode.currentTextChanged.connect(load_logs)

    # initial load
    load_logs()