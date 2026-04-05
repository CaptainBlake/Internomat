from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
)
from PySide6.QtGui import QIcon
from gui.tabs.menu_controller import MenuController
from gui.tabs.play.teambuilder_tab import build_team_tab
from gui.tabs.tools.map_roulette_tab import build_map_tab
from gui.tabs.settings.settings_tab import build_settings_tab
from gui.tabs.settings.log_window import close_log_window
from gui.tabs.statistics.leaderboard_tab import build_stat_overview_tab, refresh_stat_overview
from gui.tabs.statistics.statistics_tab import (
    build_statistics_tab,
    refresh_statistics_tab,
    on_statistics_data_updated,
)
from gui.tabs.statistics.stattracker_tab import (
    build_stattracker_tab,
    refresh_stattracker,
    on_stattracker_data_updated,
)
from gui.tabs.statistics.leaderboard_tab import on_stat_overview_data_updated
import services.logger as logger
import os
import sys


MENU_CATEGORIES = ["Play", "Tools", "Statistics", "Settings"]

MENU_TABS = [
    {"category": "Play", "id": "team_builder", "label": "Team Builder", "page_key": "team_builder"},
    {"category": "Tools", "id": "map_roulette", "label": "Map Roulette", "page_key": "map_roulette"},
    {
        "category": "Statistics",
        "id": "leaderboard",
        "label": "Leaderboard",
        "page_key": "stat_overview",
        "on_select": "refresh_stat_overview",
    },
    {
        "category": "Statistics",
        "id": "statistics",
        "label": "Statistics",
        "page_key": "statistics",
        "on_select": "refresh_statistics",
    },
    {
        "category": "Statistics",
        "id": "stat_tracker",
        "label": "Stat Tracker",
        "page_key": "stat_tracker",
        "on_select": "refresh_stattracker",
    },
]

def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


MAIN_WINDOW = None
_RELOADING_UI = False

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
                font-size: 14px;
                font-weight: 600;
            }
            QTabWidget::pane {
                border: 0;
                margin: 0;
                padding: 0;
            }
        """)

        self.setCentralWidget(self.tabs)

        self.menu = MenuController(
            tabs=self.tabs,
            menu_categories=MENU_CATEGORIES,
            settings_category="Settings",
            on_category_changed=lambda category: logger.log_user_action("Switched Tab", category),
        )
        category_pages, _ = self.menu.build_category_pages()
        self.settings_page = category_pages["Settings"]

        self.team_page = QWidget()
        self.map_page = QWidget()
        self.stat_overview_page = QWidget()
        self.statistics_page = QWidget()
        self.stat_tracker_page = QWidget()

        pages_by_key = {
            "team_builder": self.team_page,
            "map_roulette": self.map_page,
            "stat_overview": self.stat_overview_page,
            "statistics": self.statistics_page,
            "stat_tracker": self.stat_tracker_page,
        }

        for tab_def in MENU_TABS:
            callback = None
            if tab_def.get("on_select") == "refresh_stat_overview":
                callback = lambda: refresh_stat_overview(self.stat_overview_page)
            elif tab_def.get("on_select") == "refresh_statistics":
                callback = lambda: refresh_statistics_tab(self.statistics_page)
            elif tab_def.get("on_select") == "refresh_stattracker":
                callback = lambda: refresh_stattracker(self.stat_tracker_page)

            self.menu.add_to(
                category=tab_def["category"],
                tab_id=tab_def["id"],
                label=tab_def["label"],
                widget=pages_by_key[tab_def["page_key"]],
                on_select=callback,
            )

        self.menu.populate_category_stacks()

        logger.log("[GUI] Tabs created", level="DEBUG")

        def on_players_data_updated():
            logger.log("[UI] Player data update event received", level="DEBUG")
            on_stat_overview_data_updated(self.stat_overview_page)

        def on_data_updated():
            logger.log("[UI] Data update event received", level="DEBUG")
            on_statistics_data_updated(self.statistics_page)
            on_stat_overview_data_updated(self.stat_overview_page)
            on_stattracker_data_updated(self.stat_tracker_page)
            if callable(refresh_maps):
                refresh_maps()

        team_update_trigger = {}

        refresh_players = build_team_tab(
            self.team_page,
            on_data_updated=on_data_updated,
            on_players_data_updated=on_players_data_updated,
            update_trigger=team_update_trigger,
        )
        logger.log("[GUI] Team Builder ready", level="INFO")

        refresh_maps = build_map_tab(self.map_page)
        logger.log("[GUI] Map Roulette ready", level="INFO")

        build_stat_overview_tab(self.stat_overview_page)
        logger.log("[GUI] Stat Overview ready", level="INFO")

        build_statistics_tab(self.statistics_page)
        logger.log("[GUI] Statistics ready", level="INFO")

        build_stattracker_tab(self.stat_tracker_page)
        logger.log("[GUI] Stat Tracker ready", level="INFO")

        build_settings_tab(
            self.settings_page,
            on_players_updated=refresh_players,
            on_update_players=team_update_trigger.get("run"),
            on_update_players_only=team_update_trigger.get("run_players_only"),
            on_data_updated=on_data_updated,
            on_players_data_updated=on_players_data_updated,
        )
        logger.log("[GUI] Settings ready", level="INFO")

        self.menu.build_submenu()
        self.menu.select_subtab("Play", "team_builder")
        self.tabs.setCurrentIndex(0)
        self.menu.set_submenu_visible(False)

        # --- user interaction ---
        self.tabs.currentChanged.connect(self.menu.on_tab_changed)
        self.tabs.tabBar().tabBarClicked.connect(self.menu.on_tab_clicked)
        self.tabs.tabBar().installEventFilter(self)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Delegate menu-related filter events to the menu controller."""
        # Guard against re-entrant global event-filter callbacks.
        if getattr(self, "_menu_eventfilter_busy", False):
            return super().eventFilter(obj, event)

        self._menu_eventfilter_busy = True
        try:
            self.menu.handle_event_filter(obj, event)
        finally:
            self._menu_eventfilter_busy = False

        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        """Keep submenu anchored while the main window changes size."""
        super().resizeEvent(event)
        self.menu.handle_resize()

    def closeEvent(self, event):
        """Ensure auxiliary windows and workers stop when main window closes."""
        close_log_window()
        super().closeEvent(event)

        app = QApplication.instance()
        if app is not None and not _RELOADING_UI:
            app.quit()



def start_gui():
    logger.log("[APP_START]", level="INFO")
    global MAIN_WINDOW

    app = QApplication.instance() or QApplication([])

    # very important feature! do not change:
    icon = QIcon(resource_path("assets/duck_icon.ico"))
    app.setWindowIcon(icon)

    def load_stylesheet():
        path = resource_path("../styles/app.qss")

        logger.log(f"[GUI] Loading stylesheet from {path}", level="DEBUG")

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    app.setStyleSheet(load_stylesheet())

    MAIN_WINDOW = InternomatWindow()
    MAIN_WINDOW.setWindowIcon(icon)
    MAIN_WINDOW.show()

    logger.log("[APP_READY] GUI running", level="INFO")
    return app
    
def restart_window():
    global MAIN_WINDOW, _RELOADING_UI

    logger.log("[GUI] Reloading UI", level="INFO")

    app = QApplication.instance()
    previous_quit_on_last = app.quitOnLastWindowClosed() if app is not None else True
    if app is not None:
        app.setQuitOnLastWindowClosed(False)

    _RELOADING_UI = True

    try:
        if MAIN_WINDOW:
            MAIN_WINDOW.close()
            MAIN_WINDOW.deleteLater()

        MAIN_WINDOW = InternomatWindow()
        MAIN_WINDOW.show()
    finally:
        _RELOADING_UI = False
        if app is not None:
            app.setQuitOnLastWindowClosed(previous_quit_on_last)
