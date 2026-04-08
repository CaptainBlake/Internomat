# core/settings.py

import db.settings_db as settings_db
from core.settings.service import SETTINGS_SCHEMA, _to_bool


# ---------------------------------------------------------------------------
# Single source of truth: schema key → (type_caster, default_value)
# Adding a new setting only requires a new entry here.
# ---------------------------------------------------------------------------
_SETTINGS_DEFAULTS = {
    "update_cooldown_minutes":          (int,      0),
    "max_demos_per_update":             (int,      0),
    "log_level":                        (str,      "INFO"),
    "log_export_enabled":               (_to_bool, True),
    "dist_weight":                      (float,    0.25),
    "default_rating":                   (int,      10000),
    "allow_uneven_teams":               (_to_bool, False),
    "use_elo_when_in_season":          (_to_bool, True),
    "maproulette_use_history":          (_to_bool, False),
    "maproulette_reset_weight_each_season": (_to_bool, False),
    "matchzy_host":                     (str,      ""),
    "matchzy_port":                     (int,      3306),
    "matchzy_user":                     (str,      ""),
    "matchzy_password":                 (str,      ""),
    "matchzy_database":                 (str,      ""),
    "auto_import_players_from_history": (_to_bool, False),
    "auto_import_maps_from_history":    (_to_bool, False),
    "demo_ftp_host":                    (str,      ""),
    "demo_ftp_port":                    (int,      21),
    "demo_ftp_user":                    (str,      ""),
    "demo_ftp_password":                (str,      ""),
    "demo_remote_path":                 (str,      "/cs2/game/csgo/MatchZy"),
    "elo_seasons_json":                  (str,      "[]"),
    "elo_k_factor":                     (float,    24.0),
    "elo_base_rating":                  (float,    1500.0),
    "elo_adr_alpha":                    (float,    0.20),
    "elo_adr_spread":                   (float,    22.0),
    "elo_adr_min_mult":                 (float,    0.85),
    "elo_adr_max_mult":                 (float,    1.15),
    "elo_adr_prior_matches":            (float,    5.0),
    "elo_initial_global_anchor":        (float,    80.0),
}


class Settings:
    def __init__(self):
        for key, (_caster, default) in _SETTINGS_DEFAULTS.items():
            setattr(self, key, default)

    def load(self):
        # Legacy key migration: old single toggle → two granular toggles.
        legacy_auto_import = settings_db.get("auto_import_match_players", "False") == "True"

        for key, (caster, default) in _SETTINGS_DEFAULTS.items():
            # Use legacy value as fallback default for the two granular keys.
            if key in ("auto_import_players_from_history", "auto_import_maps_from_history"):
                db_default = str(legacy_auto_import)
            elif caster is _to_bool:
                db_default = str(default)
            else:
                db_default = default

            raw = settings_db.get(key, db_default)
            setattr(self, key, caster(raw))

    def save(self):
        for key in _SETTINGS_DEFAULTS:
            value = getattr(self, key)
            settings_db.set(key, str(value))

        # Keep legacy key for backwards compatibility with older exports.
        settings_db.set(
            "auto_import_match_players",
            str(self.auto_import_players_from_history or self.auto_import_maps_from_history),
        )


settings = Settings()