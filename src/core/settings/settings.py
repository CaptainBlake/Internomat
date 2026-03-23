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
        # Matchzy integration settings
        self.matchzy_host = ""
        self.matchzy_port = 3306
        self.matchzy_user = ""
        self.matchzy_password = ""
        self.matchzy_database = ""
        # Demo FTP sync settings
        self.demo_ftp_host = ""
        self.demo_ftp_port = 21
        self.demo_ftp_user = ""
        self.demo_ftp_password = ""
        self.demo_remote_path = "/cs2/game/csgo/MatchZy"

    def load(self):
        # load settings from DB, fallback to defaults if not set
        self.update_cooldown_minutes = int(settings_db.get("update_cooldown_minutes", 0))
        self.log_level = settings_db.get("log_level", "INFO")
        self.dist_weight = float(settings_db.get("dist_weight", 0.25))
        self.default_rating = int(settings_db.get("default_rating", 10000))
        self.allow_uneven_teams = settings_db.get("allow_uneven_teams", "False") == "True"
        # Matchzy settings
        self.matchzy_host = settings_db.get("matchzy_host", "")
        self.matchzy_port = int(settings_db.get("matchzy_port", 3306))
        self.matchzy_user = settings_db.get("matchzy_user", "")
        self.matchzy_password = settings_db.get("matchzy_password", "")
        self.matchzy_database = settings_db.get("matchzy_database", "")
        # Demo FTP sync settings
        self.demo_ftp_host = settings_db.get("demo_ftp_host", "")
        self.demo_ftp_port = int(settings_db.get("demo_ftp_port", 21))
        self.demo_ftp_user = settings_db.get("demo_ftp_user", "")
        self.demo_ftp_password = settings_db.get("demo_ftp_password", "")
        self.demo_remote_path = settings_db.get("demo_remote_path", "/cs2/game/csgo/MatchZy")

    def save(self):
        # save current settings to DB
        settings_db.set("update_cooldown_minutes", self.update_cooldown_minutes)
        settings_db.set("log_level", self.log_level)
        settings_db.set("dist_weight", self.dist_weight)
        settings_db.set("default_rating", self.default_rating)
        settings_db.set("allow_uneven_teams", str(self.allow_uneven_teams))
        # Matchzy settings
        settings_db.set("matchzy_host", self.matchzy_host)
        settings_db.set("matchzy_port", self.matchzy_port)
        settings_db.set("matchzy_user", self.matchzy_user)
        settings_db.set("matchzy_password", self.matchzy_password)
        settings_db.set("matchzy_database", self.matchzy_database)
        # Demo FTP sync settings
        settings_db.set("demo_ftp_host", self.demo_ftp_host)
        settings_db.set("demo_ftp_port", self.demo_ftp_port)
        settings_db.set("demo_ftp_user", self.demo_ftp_user)
        settings_db.set("demo_ftp_password", self.demo_ftp_password)
        settings_db.set("demo_remote_path", self.demo_remote_path)


settings = Settings()