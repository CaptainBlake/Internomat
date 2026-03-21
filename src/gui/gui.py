from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
from PySide6.QtGui import QIcon
from gui.tabs.team_builder import build_team_tab
from gui.tabs.map_roulette import build_map_tab
from gui.tabs.settings_tab import build_settings_tab
from gui.tabs.stat_overview import build_stat_overview_tab, refresh_stat_overview
from core.settings.settings import settings
import services.logger as logger
import os
import sys

def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


MAIN_WINDOW = None

class InternomatWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        logger.log("[GUI] Init main window", level="DEBUG")

        self.setWindowTitle("Internomat")
        self.resize(1400, 900)
        self.setMinimumSize(1400, 900)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.setTabBarAutoHide(False)

        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setUsesScrollButtons(False)

        # important feature!
        icon_path = resource_path("assets/duck_icon.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.tabs.setStyleSheet("""
            QTabBar::tab {
                min-height: 36px;
                padding: 10px 18px;
                font-size: 16px;
                font-weight: 600;
            }
            QTabWidget::pane {
                border: 0;
                margin: 0;
                padding: 0;
            }
        """)

        self.setCentralWidget(self.tabs)

        self.team_tab = QWidget()
        self.map_tab = QWidget()
        self.settings_tab = QWidget()
        self.stat_tab = QWidget()

        self.tabs.addTab(self.team_tab, "Team Builder")
        self.tabs.addTab(self.map_tab, "Map Roulette")
        self.tabs.addTab(self.stat_tab, "Stat Overview")
        self.tabs.addTab(self.settings_tab, "Settings")

        logger.log("[GUI] Tabs created", level="DEBUG")

        refresh_players = build_team_tab(self.team_tab)
        logger.log("[GUI] Team Builder ready", level="INFO")

        build_map_tab(self.map_tab)
        logger.log("[GUI] Map Roulette ready", level="INFO")

        build_stat_overview_tab(self.stat_tab)
        logger.log("[GUI] Stat Overview ready", level="INFO")

        build_settings_tab(self.settings_tab, on_players_updated=refresh_players)
        logger.log("[GUI] Settings ready", level="INFO")

        # --- user interaction ---
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        logger.log_user_action("Switched Tab", tab_name)
        if tab_name == "Stat Overview":
            refresh_stat_overview(self.stat_tab)
        #TODO: maybe add some kind of auto-refresh here

    def closeEvent(self, event):
        from services.profile_scrapper import close_driver

        close_driver()

        super().closeEvent(event)


def start_gui():
    logger.log("[APP_START]", level="INFO")
    global MAIN_WINDOW

    from PySide6.QtGui import QIcon
    app = QApplication.instance() or QApplication([])

    # very important feature! do not change:
    icon = QIcon(resource_path("assets/duck_icon.ico"))
    app.setWindowIcon(icon)

    def load_stylesheet():
        path = resource_path("styles/app.qss")

        logger.log(f"[GUI] Loading stylesheet from {path}", level="DEBUG")

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    app.setStyleSheet(load_stylesheet())


    MAIN_WINDOW = InternomatWindow()
    MAIN_WINDOW.setWindowIcon(icon)
    MAIN_WINDOW.show()

    logger.log("[APP_READY] GUI running", level="INFO")
    app.exec()
    
def restart_window():
    global MAIN_WINDOW

    logger.log("[GUI] Reloading UI", level="INFO")

    if MAIN_WINDOW:
        MAIN_WINDOW.close()
        MAIN_WINDOW.deleteLater()

    MAIN_WINDOW = InternomatWindow()
    MAIN_WINDOW.show()
