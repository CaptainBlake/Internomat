from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSpinBox
from core.settings.settings import settings
from gui.tabs.settings.settings_helpers import (
    create_section,
    create_setting_row,
    text_input,
)


def build_matchzy_section(setting_bindings, mark_dirty, save_settings_button):
    """Build the MatchZy Database section. Returns the frame."""
    frame, layout = create_section("MatchZy Database")

    info_label = QLabel("Requires MatchZy to be configured with a MySQL database.")
    info_label.setWordWrap(True)
    info_label.setStyleSheet("""
        QLabel {
            font-size: 12px;
            color: #5A6B7C;
            padding-bottom: 6px;
        }
    """)
    layout.addWidget(info_label)

    input_host = text_input(settings.matchzy_host)
    layout.addLayout(create_setting_row(
        "Host:", input_host, "matchzy_host",
        setting_bindings, mark_dirty,
        tooltip="Hostname or IP address of the MySQL server."
    ))

    input_port = QSpinBox()
    input_port.setRange(1, 65535)
    input_port.setValue(settings.matchzy_port)
    layout.addLayout(create_setting_row(
        "Port:", input_port, "matchzy_port",
        setting_bindings, mark_dirty,
        tooltip="MySQL server port.\nDefault: 3306"
    ))

    input_user = text_input(settings.matchzy_user)
    layout.addLayout(create_setting_row(
        "User:", input_user, "matchzy_user",
        setting_bindings, mark_dirty,
        tooltip="MySQL username for the MatchZy database."
    ))

    input_password = text_input(settings.matchzy_password, password=True)
    layout.addLayout(create_setting_row(
        "Password:", input_password, "matchzy_password",
        setting_bindings, mark_dirty,
        tooltip="MySQL password for the MatchZy database."
    ))

    input_db = text_input(settings.matchzy_database)
    layout.addLayout(create_setting_row(
        "Database:", input_db, "matchzy_database",
        setting_bindings, mark_dirty,
        tooltip="Name of the MatchZy MySQL database."
    ))

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)
    btn_row.addWidget(save_settings_button)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    return frame
