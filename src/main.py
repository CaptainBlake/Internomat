from db.init_db import init_db
from gui.gui import start_gui
from services.executor import shutdown as shutdown_executor
from core.settings.settings import settings
from services.demo_cache import reconcile_db_demo_flags_default
from services.profile_scrapper import close_driver
import services.logger as logger


def shutdown():
    logger.log("[APP_SHUTDOWN] Stopping background services", level="INFO")

    try:
        close_driver()
    except Exception as e:
        logger.log_error(f"[APP_SHUTDOWN] Selenium close failed: {e}", exc=e)

    try:
        shutdown_executor(wait=True)
    except Exception as e:
        logger.log_error(f"[APP_SHUTDOWN] Executor shutdown failed: {e}", exc=e)

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