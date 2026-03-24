from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QFrame,
    QStackedWidget,
    QPushButton,
    QLabel,
)
from PySide6.QtGui import QIcon
from gui.tabs.teambuilder_tab import build_team_tab
from gui.tabs.map_roulette_tab import build_map_tab
from gui.tabs.settings_tab import build_settings_tab
from gui.tabs.leaderboard_tab import build_stat_overview_tab, refresh_stat_overview
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

        self.menu_categories = ["Play", "Tools", "Statistics", "Settings"]
        self.tab_map = {category: [] for category in self.menu_categories}
        self.category_stacks = {}
        self.category_pages = {}
        self.submenu_buttons = {}
        self.category_collapsed = set()
        self.active_subtab_by_category = {}
        self.content_category = "Play"
        self.open_menu_category = None
        self._suppress_tab_change = False

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

        self._build_category_pages()

        self.team_page = QWidget()
        self.map_page = QWidget()
        self.stat_overview_page = QWidget()
        self.stat_tracker_page = QWidget()

        tracker_layout = QVBoxLayout(self.stat_tracker_page)
        tracker_layout.setContentsMargins(24, 24, 24, 24)
        tracker_label = QLabel("Stat Tracker coming soon")
        tracker_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #2E4C69;")
        tracker_layout.addWidget(tracker_label)
        tracker_layout.addStretch()

        self.add_to("Play", "team_builder", "Team Builder", self.team_page)
        self.add_to("Tools", "map_roulette", "Map Roulette", self.map_page)
        self.add_to(
            "Statistics",
            "leaderboard",
            "Leaderboard",
            self.stat_overview_page,
            on_select=lambda: refresh_stat_overview(self.stat_overview_page),
        )
        self.add_to("Statistics", "stat_tracker", "Stat-tracker", self.stat_tracker_page)

        self._populate_category_stacks()

        logger.log("[GUI] Tabs created", level="DEBUG")

        refresh_players = build_team_tab(self.team_page)
        logger.log("[GUI] Team Builder ready", level="INFO")

        build_map_tab(self.map_page)
        logger.log("[GUI] Map Roulette ready", level="INFO")

        build_stat_overview_tab(self.stat_overview_page)
        logger.log("[GUI] Stat Overview ready", level="INFO")

        build_settings_tab(self.settings_page, on_players_updated=refresh_players)
        logger.log("[GUI] Settings ready", level="INFO")

        self._build_category_submenu()
        self._select_subtab("Play", "team_builder")
        self.tabs.setCurrentIndex(0)
        self._set_category_submenu_visible(False)

        # --- user interaction ---
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().tabBarClicked.connect(self._on_tab_clicked)
        self.tabs.tabBar().installEventFilter(self)
        QApplication.instance().installEventFilter(self)

    def _build_category_pages(self):
        self.settings_page = QWidget()

        for category in self.menu_categories:
            if category == "Settings":
                self.tabs.addTab(self.settings_page, category)
                self.category_pages[category] = self.settings_page
                continue

            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)

            stack = QStackedWidget()
            stack.addWidget(QWidget())
            page_layout.addWidget(stack)

            self.tabs.addTab(page, category)
            self.category_pages[category] = page
            self.category_stacks[category] = stack

    def add_to(self, category, tab_id, label, widget, on_select=None):
        if category not in self.tab_map:
            raise ValueError(f"Unknown category: {category}")

        self.tab_map[category].append(
            {
                "id": tab_id,
                "label": label,
                "widget": widget,
                "on_select": on_select,
            }
        )

    def _populate_category_stacks(self):
        for category, entries in self.tab_map.items():
            stack = self.category_stacks.get(category)
            if stack is None:
                continue

            for index, entry in enumerate(entries):
                stack.addWidget(entry["widget"])
                entry["stack_index"] = index + 1

            stack.setCurrentIndex(0)

    def _build_category_submenu(self):
        self.category_submenu = QFrame(self.tabs)
        self.category_submenu.setObjectName("categorySubmenu")
        self.category_submenu.setStyleSheet(
            """
            QFrame#categorySubmenu {
                background: transparent;
                border: none;
            }
            QPushButton {
                background: #DCEAF7;
                color: #2E4C69;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 600;
                text-align: center;
            }
            QPushButton:hover {
                background: #E7F1FB;
                color: #3A79BA;
            }
            QPushButton:checked {
                background: #FFFFFF;
                color: #2F6FB3;
            }
            """
        )

        self.category_submenu_layout = QVBoxLayout(self.category_submenu)
        self.category_submenu_layout.setContentsMargins(0, 0, 0, 0)
        self.category_submenu_layout.setSpacing(6)

        self.category_submenu.hide()

    def _clear_category_submenu_buttons(self):
        while self.category_submenu_layout.count():
            item = self.category_submenu_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_submenu_for_category(self, category):
        self._clear_category_submenu_buttons()
        self.submenu_buttons = {}

        entries = self.tab_map.get(category, [])
        tab_rect = self.tabs.tabBar().tabRect(self.tabs.currentIndex())
        item_height = tab_rect.height() if tab_rect.isValid() else 40

        for entry in entries:
            button = QPushButton(f"{entry['label']}")
            button.setCheckable(True)
            button.setFixedHeight(item_height)
            button.clicked.connect(
                lambda _checked=False, c=category, tab_id=entry["id"]: self._select_subtab(c, tab_id)
            )
            self.submenu_buttons[entry["id"]] = button
            self.category_submenu_layout.addWidget(button)

    def _set_category_submenu_visible(self, visible):
        if visible:
            self._reposition_category_submenu()
            self.category_submenu.show()
            self.category_submenu.raise_()
        else:
            self.category_submenu.hide()

    def _reposition_category_submenu(self):
        if not hasattr(self, "category_submenu"):
            return

        tab_bar = self.tabs.tabBar()
        index = self.tabs.currentIndex()
        if index < 0:
            return

        tab_rect = tab_bar.tabRect(index)
        if not tab_rect.isValid():
            return

        pos = tab_bar.mapTo(self.tabs, tab_rect.bottomLeft())
        x = pos.x()
        y = pos.y()
        width = tab_rect.width()
        button_count = self.category_submenu_layout.count()
        button_height = tab_rect.height() if tab_rect.isValid() else 40
        spacing = self.category_submenu_layout.spacing() if button_count > 1 else 0
        height = button_count * button_height + max(0, button_count - 1) * spacing
        self.category_submenu.setGeometry(x, y, width, height)

    def _get_category_entries(self, category):
        return self.tab_map.get(category, [])

    def _set_current_tab_silently(self, index):
        self._suppress_tab_change = True
        try:
            self.tabs.setCurrentIndex(index)
        finally:
            self._suppress_tab_change = False

    def _restore_content_category_tab(self):
        page = self.category_pages.get(self.content_category)
        if page is None:
            return

        index = self.tabs.indexOf(page)
        if index >= 0 and self.tabs.currentIndex() != index:
            self._set_current_tab_silently(index)

    def _select_subtab(self, category, tab_id):
        entries = self._get_category_entries(category)
        stack = self.category_stacks.get(category)

        if stack is None:
            return

        selected_entry = None
        for entry in entries:
            if entry["id"] == tab_id:
                selected_entry = entry
                stack.setCurrentIndex(entry["stack_index"])
                self.active_subtab_by_category[category] = tab_id
                break

        if selected_entry is None:
            return

        for entry in entries:
            btn = self.submenu_buttons.get(entry["id"])
            if btn is not None:
                btn.setChecked(entry["id"] == tab_id)

        on_select = selected_entry.get("on_select")
        if on_select:
            on_select()

        self.content_category = category
        target_page = self.category_pages.get(category)
        if target_page is not None:
            target_index = self.tabs.indexOf(target_page)
            if target_index >= 0:
                self._set_current_tab_silently(target_index)

        self.open_menu_category = None
        self.category_collapsed.add(category)
        self._set_category_submenu_visible(False)

    def _on_tab_clicked(self, index):
        category = self.tabs.tabText(index)

        if category == "Settings":
            self.category_collapsed.discard(category)
            self.open_menu_category = None
            self._set_category_submenu_visible(False)
            self.content_category = "Settings"
            return

        if self.open_menu_category == category and self.category_submenu.isVisible():
            self.category_collapsed.add(category)
            self.open_menu_category = None
            self._set_category_submenu_visible(False)
        else:
            self.category_collapsed.discard(category)
            self.open_menu_category = category
            self._build_submenu_for_category(category)
            self._set_category_submenu_visible(True)

        self._restore_content_category_tab()

    def _on_tab_changed(self, index):
        if self._suppress_tab_change:
            return

        category = self.tabs.tabText(index)
        logger.log_user_action("Switched Tab", category)

        if category == "Settings":
            self.content_category = "Settings"
            self.open_menu_category = None
            self._set_category_submenu_visible(False)
            return

        self.open_menu_category = category
        self._build_submenu_for_category(category)
        self._set_category_submenu_visible(True)
        self._restore_content_category_tab()

    def eventFilter(self, obj, event):
        if obj == self.tabs.tabBar() and event.type() in (QEvent.Resize, QEvent.Show):
            if hasattr(self, "category_submenu") and self.category_submenu.isVisible():
                self._reposition_category_submenu()

        if event.type() == QEvent.MouseButtonPress:
            if hasattr(self, "category_submenu") and self.category_submenu.isVisible():
                global_pos = None
                if hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                elif hasattr(event, "globalPos"):
                    global_pos = event.globalPos()

                if global_pos is not None:
                    submenu_hit = self._global_pos_in_widget(self.category_submenu, global_pos)
                    tabbar_hit = self._global_pos_in_widget(self.tabs.tabBar(), global_pos)

                    if not submenu_hit and not tabbar_hit:
                        if self.open_menu_category:
                            self.category_collapsed.add(self.open_menu_category)
                        self.open_menu_category = None
                        self._set_category_submenu_visible(False)

        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "category_submenu") and self.category_submenu.isVisible():
            self._reposition_category_submenu()

    @staticmethod
    def _global_pos_in_widget(widget, global_pos):
        if widget is None or not widget.isVisible():
            return False

        top_left = widget.mapToGlobal(QPoint(0, 0))
        local = global_pos - top_left
        return widget.rect().contains(local)



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
    return app
    
def restart_window():
    global MAIN_WINDOW

    logger.log("[GUI] Reloading UI", level="INFO")

    if MAIN_WINDOW:
        MAIN_WINDOW.close()
        MAIN_WINDOW.deleteLater()

    MAIN_WINDOW = InternomatWindow()
    MAIN_WINDOW.show()
