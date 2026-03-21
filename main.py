from db.init import init_db
from gui.gui import start_gui


def main():
    init_db()
    start_gui()


if __name__ == "__main__":
    main()