from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
from PySide6.QtGui import QIcon
from tabs.team_builder import build_team_tab
from tabs.map_roulette import build_map_tab
from tabs.settings_tab import build_settings_tab
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
    background-color: #F4FCF9;
}

QWidget {
    background-color: #F4FCF9;
    font-family: Segoe UI;
    font-size: 10pt;
}

QMainWindow, QWidget {
    color: #20443D;
}

QTextEdit {
    background-color: #FFFFFF;
    color: #20443D;
}

QTableWidget::item {
    color: #20443D;
}

QTabWidget::pane {
    border: 0;
    margin: 0;
    padding: 0;
}

QTabBar::tab {
    background: #E3F8F1;
    color: #4D756B;
    min-width: 180px;
    min-height: 40px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #6CCFB6;
}

QTabBar::tab:hover {
    background: #ECFBF7;
    color: #5DBEA7;
}

QLineEdit, QTableWidget, QListWidget {
    background-color: #FFFFFF;
    color: #20443D;
    border: 1px solid #D5EEE6;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #6CCFB6;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QTableWidget:focus, QListWidget:focus {
    border: 1px solid #6CCFB6;
}

QPushButton {
    background-color: #69CFAC;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #7FD9BF;
}

QPushButton:pressed {
    background-color: #56BF9B;
}

QPushButton:disabled {
    background-color: #C6EADF;
    color: #F4FCF9;
}

QHeaderView::section {
    background-color: #E3F8F1;
    color: #4A7168;
    padding: 6px;
    border: none;
    font-weight: 600;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #DFF7EF;
    color: #4A7168;
}

QSlider::groove:horizontal {
    height: 8px;
    background: #E6F7F2;
    border-radius: 4px;
}

QSlider::sub-page:horizontal {
    background: #8EE0CA;
    border-radius: 4px;
}

QSlider::add-page:horizontal {
    background: #E6F7F2;
    border-radius: 4px;
}

QSlider::handle:horizontal {
    background: #8EE0CA;
    border: 2px solid #A9E9D7;
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #A0E7D5;
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

        self.tabs.addTab(self.team_tab, "Team Builder")
        self.tabs.addTab(self.map_tab, "Map Roulette")
        self.tabs.addTab(self.settings_tab, "Settings")

        logger.log("[GUI] Tabs created", level="DEBUG")

        refresh_players = build_team_tab(self.team_tab)
        logger.log("[GUI] Team Builder ready", level="INFO")

        build_map_tab(self.map_tab)
        logger.log("[GUI] Map Roulette ready", level="INFO")
        build_settings_tab(self.settings_tab, on_players_updated=refresh_players)
        logger.log("[GUI] Settings ready", level="INFO")

        # --- user interaction ---
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        logger.log_user_action("Switched Tab", tab_name)
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
