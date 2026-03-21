from db.init_db import init_db
from gui.gui import start_gui
from services.executor import shutdown
from core.settings.settings import settings

def main():
    init_db()
    settings.load()
    app = start_gui()
    app.aboutToQuit.connect(shutdown)
    app.exec()


if __name__ == "__main__":
    main()