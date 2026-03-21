from db.init import init_db
from gui.gui import start_gui
from services.executor import shutdown


def main():
    init_db()

    app = start_gui()

    app.aboutToQuit.connect(shutdown)

    app.exec()


if __name__ == "__main__":
    main()