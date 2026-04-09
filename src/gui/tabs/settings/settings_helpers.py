from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)


def date_from_str(value):
    from datetime import datetime
    txt = str(value or "").strip()
    if not txt:
        return None
    try:
        return datetime.fromisoformat(txt[:10]).date()
    except Exception:
        return None


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


_SETTING_ROW_WIDGET_STYLE = """
    QSpinBox, QDoubleSpinBox {
        background: #FFFFFF;
        color: #1E2B38;
        border: 1px solid #B9CADC;
        border-radius: 8px;
        padding: 6px 36px 6px 10px;
        min-height: 36px;
        min-width: 70px;
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
"""


def create_setting_row(label_text, widget, attr_name, setting_bindings, mark_dirty, tooltip=None):
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
    widget.setStyleSheet(_SETTING_ROW_WIDGET_STYLE)

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
