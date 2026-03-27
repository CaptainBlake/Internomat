from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

from services.logger import get_log_history
import services.logger as logger


_LOG_WINDOW_INSTANCE = None
_QUIT_HOOK_ATTACHED = False


def open_log_window(parent=None):
    global _LOG_WINDOW_INSTANCE
    global _QUIT_HOOK_ATTACHED

    app = QApplication.instance()
    if app is not None and not _QUIT_HOOK_ATTACHED:
        app.aboutToQuit.connect(close_log_window)
        _QUIT_HOOK_ATTACHED = True

    if _LOG_WINDOW_INSTANCE is None or not _LOG_WINDOW_INSTANCE.isVisible():
        # Keep popup behavior while tying lifetime to the main app window.
        _LOG_WINDOW_INSTANCE = LogWindow(parent=parent, on_closed=_on_window_closed)

    _LOG_WINDOW_INSTANCE.show()
    _LOG_WINDOW_INSTANCE.raise_()
    _LOG_WINDOW_INSTANCE.activateWindow()


def close_log_window():
    if _LOG_WINDOW_INSTANCE is None:
        return
    _LOG_WINDOW_INSTANCE.request_close()


def _on_window_closed():
    global _LOG_WINDOW_INSTANCE
    _LOG_WINDOW_INSTANCE = None


class LogWindow(QWidget):
    def __init__(self, parent=None, on_closed=None):
        super().__init__(parent)

        self._on_closed = on_closed
        self._closed = False

        # Show as standalone popup even when a parent is set for lifecycle ownership.
        self.setWindowFlag(Qt.Window, True)

        self.setWindowTitle("Internomat Logs")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

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

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.log_view)

        self.last_snapshot = ""

        self.log_mode.currentTextChanged.connect(self.reload_logs)

        logger.subscribe(self.append_log)

        self.reload_logs()

    def filter_logs(self, logs):
        mode = self.log_mode.currentText()

        if mode == "INFO":
            return [line for line in logs if "[DEBUG]" not in line]

        if mode == "ERROR":
            return [line for line in logs if "[ERROR]" in line]

        return logs

    def reload_logs(self):
        logs = get_log_history()
        filtered = self.filter_logs(logs)
        new_text = "\n".join(filtered)

        if new_text == self.last_snapshot:
            return

        self.last_snapshot = new_text
        self.log_view.setPlainText(new_text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def append_log(self, entry):
        mode = self.log_mode.currentText()

        if mode == "ERROR" and "[ERROR]" not in entry:
            return

        if mode == "INFO" and "[DEBUG]" in entry:
            return

        self.log_view.append(entry)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def request_close(self):
        if self._closed:
            return
        self.close()

    def closeEvent(self, event):
        if not self._closed:
            self._closed = True
            logger.unsubscribe(self.append_log)

            if callable(self._on_closed):
                self._on_closed()

        super().closeEvent(event)