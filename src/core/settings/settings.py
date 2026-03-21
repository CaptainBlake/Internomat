# core/settings.py

import db.settings_db as settings_db


class Settings:
    def __init__(self):
        # defaults
        self.update_cooldown_minutes = 0
        self.log_level = "INFO"
        self.dist_weight = 0.25
        self.default_rating = 10000
        self.allow_uneven_teams = False

    def load(self):
        self.update_cooldown_minutes = int(settings_db.get("update_cooldown_minutes", 0))
        self.log_level = settings_db.get("log_level", "INFO")
        self.dist_weight = float(settings_db.get("dist_weight", 0.25))
        self.default_rating = int(settings_db.get("default_rating", 10000))
        self.allow_uneven_teams = settings_db.get("allow_uneven_teams", "False") == "True"

    def save(self):
        settings_db.set("update_cooldown_minutes", self.update_cooldown_minutes)
        settings_db.set("log_level", self.log_level)
        settings_db.set("dist_weight", self.dist_weight)
        settings_db.set("default_rating", self.default_rating)
        settings_db.set("allow_uneven_teams", str(self.allow_uneven_teams))


settings = Settings()