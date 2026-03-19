from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from tabs.team_builder import build_team_tab
from tabs.map_roulette import build_map_tab


APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #ECEFF1;
    color: #263238;
    font-family: "Segoe UI";
    font-size: 11px;
}

QTabWidget::pane {
    border: 0;
    margin: 0;
    padding: 0;
}

QTabBar::tab {
    background: #CFD8DC;
    color: #455A64;
    min-width: 180px;
    min-height: 44px;
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-size: 13px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #1976D2;
}

QTabBar::tab:hover {
    background: #E3F2FD;
    color: #1565C0;
}

QLineEdit, QTableWidget, QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #CFD8DC;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #1976D2;
    selection-color: #FFFFFF;
}

QSlider {
    background: transparent;
}

QLineEdit:focus, QTableWidget:focus, QListWidget:focus {
    border: 1px solid #1976D2;
}

QPushButton {
    background-color: #1976D2;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1565C0;
}

QPushButton:pressed {
    background-color: #0D47A1;
}

QPushButton:disabled {
    background-color: #90A4AE;
    color: #ECEFF1;
}

QLabel {
    color: #263238;
}

QHeaderView::section {
    background-color: #CFD8DC;
    color: #37474F;
    padding: 6px;
    border: none;
    font-weight: 600;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #BBDEFB;
    color: #0D47A1;
}

QFrame {
    border: none;
}
"""


class InternomatWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Internomat")
        self.resize(1100, 780)
        self.setMinimumSize(900, 700)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.setTabBarAutoHide(False)

        self.tabs.setStyleSheet("""
            QTabBar::tab {
                flex: 1;
                min-width: 100%;
                min-height: 36px;
                padding: 10px 18px;
                margin-right: 4px;
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

        self.tabs.addTab(self.team_tab, "Team Builder")
        self.tabs.addTab(self.map_tab, "Map Roulette")

        build_team_tab(self.team_tab)
        build_map_tab(self.map_tab)


def start_gui():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(APP_STYLESHEET)

    window = InternomatWindow()
    window.show()
    app.exec()