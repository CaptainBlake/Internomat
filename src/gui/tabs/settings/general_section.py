from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSpinBox
from core.settings.settings import settings
from gui.tabs.settings.settings_helpers import create_section, create_setting_row


def build_general_section(setting_bindings, mark_dirty, save_settings_button):
    """Build the general Settings section. Returns the frame."""
    frame, layout = create_section("Settings")

    spin_cooldown = QSpinBox()
    spin_cooldown.setRange(0, 30)
    spin_cooldown.setValue(settings.update_cooldown_minutes)
    spin_cooldown.setButtonSymbols(QSpinBox.NoButtons)
    layout.addLayout(create_setting_row(
        "Update cooldown (minutes):", spin_cooldown, "update_cooldown_minutes",
        setting_bindings, mark_dirty,
        tooltip="Minimum wait between automatic sync runs.\nSet to 0 to disable the cooldown.\nRecommended: 10"
    ))

    spin_max_demos = QSpinBox()
    spin_max_demos.setRange(0, 10)
    spin_max_demos.setValue(int(getattr(settings, "max_demos_per_update", 0) or 0))
    spin_max_demos.setButtonSymbols(QSpinBox.NoButtons)
    layout.addLayout(create_setting_row(
        "Max demos per update:", spin_max_demos, "max_demos_per_update",
        setting_bindings, mark_dirty,
        tooltip="Limits how many demo files are parsed per sync run.\nSet to 0 to parse all available demos.\nUseful to keep sync times short."
    ))

    spin_rating = QSpinBox()
    spin_rating.setRange(0, 25000)
    spin_rating.setValue(settings.default_rating)
    spin_rating.setButtonSymbols(QSpinBox.NoButtons)
    layout.addLayout(create_setting_row(
        "Default Prime Rating:", spin_rating, "default_rating",
        setting_bindings, mark_dirty,
        tooltip="Initial CS rating assigned to new players.\nUsed by TeamBuilder when Elo is not active.\nRecommended: 10000"
    ))

    checkbox_uneven = QCheckBox()
    checkbox_uneven.setChecked(settings.allow_uneven_teams)
    layout.addLayout(create_setting_row(
        "Allow uneven teams:", checkbox_uneven, "allow_uneven_teams",
        setting_bindings, mark_dirty,
        tooltip="When enabled, TeamBuilder allows uneven team sizes (e.g. 3 vs 2).\nOtherwise an even player count is required."
    ))

    checkbox_maproulette_history = QCheckBox()
    checkbox_maproulette_history.setChecked(settings.maproulette_use_history)
    layout.addLayout(create_setting_row(
        "Map roulette uses history:", checkbox_maproulette_history, "maproulette_use_history",
        setting_bindings, mark_dirty,
        tooltip="When enabled, map roulette uses match history percentages as map weights."
    ))

    checkbox_maproulette_season_reset = QCheckBox()
    checkbox_maproulette_season_reset.setChecked(
        bool(getattr(settings, "maproulette_reset_weight_each_season", False))
    )
    layout.addLayout(create_setting_row(
        "Reset map weights each season:", checkbox_maproulette_season_reset,
        "maproulette_reset_weight_each_season",
        setting_bindings, mark_dirty,
        tooltip="When enabled, history-based map roulette only uses matches from the currently active Elo season."
    ))

    checkbox_log_export = QCheckBox()
    checkbox_log_export.setChecked(bool(getattr(settings, "log_export_enabled", True)))
    layout.addLayout(create_setting_row(
        "Export logs to file:", checkbox_log_export, "log_export_enabled",
        setting_bindings, mark_dirty,
        tooltip="When enabled, logs are written to timestamped files in the log folder."
    ))

    checkbox_use_elo_in_season = QCheckBox()
    checkbox_use_elo_in_season.setChecked(bool(getattr(settings, "use_elo_when_in_season", True)))
    layout.addLayout(create_setting_row(
        "Use Elo in active season:", checkbox_use_elo_in_season, "use_elo_when_in_season",
        setting_bindings, mark_dirty,
        tooltip="When enabled, TeamBuilder auto-switches to Elo while today is inside a configured season."
    ))

    checkbox_auto_import_players = QCheckBox()
    checkbox_auto_import_players.setChecked(settings.auto_import_players_from_history)
    layout.addLayout(create_setting_row(
        "Import players from history:", checkbox_auto_import_players, "auto_import_players_from_history",
        setting_bindings, mark_dirty,
        tooltip="When enabled, MatchZy + demo sync imports players from match history into the team pool."
    ))

    checkbox_auto_import_maps = QCheckBox()
    checkbox_auto_import_maps.setChecked(settings.auto_import_maps_from_history)
    layout.addLayout(create_setting_row(
        "Import maps from history:", checkbox_auto_import_maps, "auto_import_maps_from_history",
        setting_bindings, mark_dirty,
        tooltip="When enabled, MatchZy sync imports map names from match history into the map pool."
    ))

    settings_button_row = QHBoxLayout()
    settings_button_row.setSpacing(10)
    settings_button_row.addWidget(save_settings_button)
    settings_button_row.addStretch()
    layout.addLayout(settings_button_row)

    return frame
