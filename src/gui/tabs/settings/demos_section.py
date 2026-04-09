from PySide6.QtWidgets import QHBoxLayout, QSpinBox
from core.settings.settings import settings
from gui.tabs.settings.settings_helpers import (
    create_section,
    create_setting_row,
    text_input,
)


def build_demos_section(setting_bindings, mark_dirty, save_settings_button):
    """Build the MatchZy Demos section. Returns the frame."""
    frame, layout = create_section("MatchZy Demos")

    input_ftp_host = text_input(settings.demo_ftp_host)
    input_ftp_host.setPlaceholderText("IP/domain")
    layout.addLayout(create_setting_row(
        "FTP Server IP:", input_ftp_host, "demo_ftp_host",
        setting_bindings, mark_dirty,
        tooltip="Hostname or IP address of the FTP server hosting demo files.",
    ))

    input_ftp_port = QSpinBox()
    input_ftp_port.setRange(1, 65535)
    input_ftp_port.setValue(settings.demo_ftp_port)
    layout.addLayout(create_setting_row(
        "FTP Port:", input_ftp_port, "demo_ftp_port",
        setting_bindings, mark_dirty,
        tooltip="FTP server port.\nDefault: 21",
    ))

    input_ftp_user = text_input(settings.demo_ftp_user)
    input_ftp_user.setPlaceholderText("FTP user")
    layout.addLayout(create_setting_row(
        "FTP User:", input_ftp_user, "demo_ftp_user",
        setting_bindings, mark_dirty,
        tooltip="FTP username for authentication.",
    ))

    input_ftp_password = text_input(settings.demo_ftp_password, password=True)
    input_ftp_password.setPlaceholderText("FTP password")
    layout.addLayout(create_setting_row(
        "FTP Password:", input_ftp_password, "demo_ftp_password",
        setting_bindings, mark_dirty,
        tooltip="FTP password for authentication.",
    ))

    input_remote_path = text_input(settings.demo_remote_path)
    input_remote_path.setPlaceholderText("/cs2/game/csgo/MatchZy")
    layout.addLayout(create_setting_row(
        "Remote demo path:", input_remote_path, "demo_remote_path",
        setting_bindings, mark_dirty,
        tooltip="Absolute path on the FTP server where .dem files are stored.\nExample: /cs2/game/csgo/MatchZy",
    ))

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)
    btn_row.addWidget(save_settings_button)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    return frame
