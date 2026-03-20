from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
from PySide6.QtGui import QIcon
from tabs.team_builder import build_team_tab
from tabs.map_roulette import build_map_tab
from tabs.settings_tab import build_settings_tab
from tabs.stat_overview import build_stat_overview_tab, refresh_stat_overview
from services.settings import settings
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
APP_STYLESHEET = """

QMainWindow {
    background-color: #EEF3F9;
}

QWidget {
    background-color: #EEF3F9;
    font-family: Segoe UI;
    font-size: 10pt;
}

QMainWindow, QWidget {
    color: #1E2B38;
}

QTextEdit {
    background-color: #FFFFFF;
    color: #1E2B38;
}

QTableWidget::item {
    color: #1E2B38;
}

QTabWidget::pane {
    border: 0;
    margin: 0;
    padding: 0;
}

QTabBar::tab {
    background: #DCEAF7;
    color: #2E4C69;
    min-width: 180px;
    min-height: 40px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #2F6FB3;
}

QTabBar::tab:hover {
    background: #E7F1FB;
    color: #3A79BA;
}

QLineEdit, QTableWidget, QListWidget {
    background-color: #FFFFFF;
    color: #1E2B38;
    border: 1px solid #B9CADC;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #3F88D9;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QTableWidget:focus, QListWidget:focus {
    border: 1px solid #3F88D9;
}

/* Tables: no focus border / black outline */
QTableWidget {
    outline: none;
}

QTableWidget:focus {
    border: 1px solid #B9CADC;
    outline: none;
}

QTableWidget::item {
    color: #1E2B38;
    border: none;
    outline: none;
}

QTableWidget::item:selected {
    background-color: #DCEAF7;
    color: #1E2B38;
    border: none;
    outline: none;
}

QTableWidget::item:focus {
    border: none;
    outline: none;
}

QAbstractItemView {
    outline: none;
}

QAbstractItemView::item {
    border: none;
    outline: none;
}

QAbstractItemView::item:selected {
    border: none;
    outline: none;
}

QPushButton {
    background-color: #3F88D9;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #5A9BE3;
}

QPushButton:pressed {
    background-color: #2F6FB3;
}

QPushButton:disabled {
    background-color: #BFD0E0;
    color: #F7FAFD;
}

QHeaderView::section {
    background-color: #DCEAF7;
    color: #2E4C69;
    padding: 6px;
    border: none;
    font-weight: 600;
}

QHeaderView::section:first {
    border-top-left-radius: 8px;
}

QHeaderView::section:last {
    border-top-right-radius: 8px;
}

QHeaderView::section:only-one {
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #DCEAF7;
    color: #1E2B38;
}

QSlider::groove:horizontal {
    height: 8px;
    background: #D9E4EF;
    border-radius: 4px;
}

QSlider::sub-page:horizontal {
    background: #3F88D9;
    border-radius: 4px;
}

QSlider::add-page:horizontal {
    background: #D9E4EF;
    border-radius: 4px;
}

QSlider::handle:horizontal {
    background: #3F88D9;
    border: 2px solid #B7CCE3;
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #5A9BE3;
}

QFrame {
    border: none;
}

/* Hide scrollbars globally */
QScrollBar:vertical, QScrollBar:horizontal {
    width: 0px;
    height: 0px;
    background: transparent;
    border: none;
}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: transparent;
    border: none;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
}
"""


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
        from services.crawler import close_driver

        close_driver()

        super().closeEvent(event)


def start_gui():
    logger.log("[APP_START]", level="INFO")
    global MAIN_WINDOW
    from PySide6.QtGui import QIcon
    app = QApplication.instance() or QApplication([])

    icon = QIcon(resource_path("assets/duck_icon.ico"))
    app.setWindowIcon(icon)

    app.setStyleSheet(APP_STYLESHEET)

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
