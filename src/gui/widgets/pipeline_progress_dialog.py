from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox


class PipelineProgressDialog(QDialog):
    def __init__(self, title="Pipeline Progress", title_template="Running ({stage})", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(540, 190)

        self._title_template = title_template

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.title_label = QLabel("Running...")
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

        self._running = False
        self._allow_close = False
        self._cancel_handler = None

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
            self.title_label.setText(self._title_template.format(stage=stage))

        if message:
            self.message_label.setText(message)

        if isinstance(file_percent, (int, float)):
            value = max(0, min(100, int(file_percent)))
            self.file_progress.setValue(value)
            self.file_label.setText(f"Current file: {value}%")
        elif stage != "ftp":
            self.file_progress.setValue(0)
            self.file_label.setText("Current file: -")

    def set_running(self, running):
        self._running = bool(running)

    def set_cancel_handler(self, handler):
        self._cancel_handler = handler

    def allow_close_once(self):
        self._allow_close = True

    def closeEvent(self, event):
        if self._allow_close:
            super().closeEvent(event)
            return

        if self._running:
            confirm = QMessageBox.question(
                self,
                "Cancel Running Task",
                "You sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if confirm != QMessageBox.Yes:
                event.ignore()
                return

            if callable(self._cancel_handler):
                try:
                    self._cancel_handler()
                except Exception:
                    pass

        super().closeEvent(event)