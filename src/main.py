from db.init_db import init_db
from gui.gui import start_gui
from services.executor import shutdown
from core.settings.settings import settings
from services.demo_cache import reconcile_db_demo_flags_default
import services.logger as logger

def main():
    init_db()
    settings.load()
    logger.set_log_export_enabled(bool(getattr(settings, "log_export_enabled", True)))
    reconcile_db_demo_flags_default()
    app = start_gui()
    app.aboutToQuit.connect(shutdown)
    app.exec()


if __name__ == "__main__":
    main()