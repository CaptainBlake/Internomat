from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QFrame, QPushButton, QStackedWidget, QVBoxLayout, QWidget


SUBMENU_STYLESHEET = """
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


class MenuController:
    def __init__(self, tabs, menu_categories, settings_category, on_category_changed=None):
        self.tabs = tabs
        self.menu_categories = list(menu_categories)
        self.settings_category = settings_category
        self.on_category_changed = on_category_changed

        self.tab_map = {category: [] for category in self.menu_categories}
        self.category_stacks = {}
        self.category_pages = {}
        self.submenu_buttons = {}

        self.category_collapsed = set()
        self.active_subtab_by_category = {}
        self.content_category = self.menu_categories[0] if self.menu_categories else None
        self.open_menu_category = None
        self._suppress_tab_change = False

        self.category_submenu = None
        self.category_submenu_layout = None

    def build_category_pages(self):
        """Create one top-level tab per menu category and return page/stack maps."""
        settings_page = QWidget()

        for category in self.menu_categories:
            if category == self.settings_category:
                self.tabs.addTab(settings_page, category)
                self.category_pages[category] = settings_page
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

        return self.category_pages, self.category_stacks

    def add_to(self, category, tab_id, label, widget, on_select=None):
        """Register a subtab entry under a category."""
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

    def populate_category_stacks(self):
        """Attach registered subtabs to their category stacks."""
        for category, entries in self.tab_map.items():
            stack = self.category_stacks.get(category)
            if stack is None:
                continue

            for index, entry in enumerate(entries):
                stack.addWidget(entry["widget"])
                entry["stack_index"] = index + 1

            stack.setCurrentIndex(0)

    def build_submenu(self):
        """Create dropdown submenu UI used by non-settings categories."""
        self.category_submenu = QFrame(self.tabs)
        self.category_submenu.setObjectName("categorySubmenu")
        self.category_submenu.setStyleSheet(SUBMENU_STYLESHEET)

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
                lambda _checked=False, c=category, tab_id=entry["id"]: self.select_subtab(c, tab_id)
            )
            self.submenu_buttons[entry["id"]] = button
            self.category_submenu_layout.addWidget(button)

    def set_submenu_visible(self, visible):
        if visible:
            self.reposition_submenu()
            self.category_submenu.show()
            self.category_submenu.raise_()
        else:
            self.category_submenu.hide()

    def reposition_submenu(self):
        if self.category_submenu is None:
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

    def select_subtab(self, category, tab_id):
        """Activate one submenu item and close the dropdown."""
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
        self.set_submenu_visible(False)

    def on_tab_clicked(self, index):
        """Handle root menu click: open/close submenu or direct Settings navigation."""
        category = self.tabs.tabText(index)
        entries = self._get_category_entries(category)

        if category == self.settings_category:
            self.category_collapsed.discard(category)
            self.open_menu_category = None
            self.set_submenu_visible(False)
            self.content_category = self.settings_category
            return

        if len(entries) == 1:
            self.select_subtab(category, entries[0]["id"])
            return

        if self.open_menu_category == category and self.category_submenu.isVisible():
            self.category_collapsed.add(category)
            self.open_menu_category = None
            self.set_submenu_visible(False)
        else:
            self.category_collapsed.discard(category)
            self.open_menu_category = category
            self._build_submenu_for_category(category)
            self.set_submenu_visible(True)

        self._restore_content_category_tab()

    def on_tab_changed(self, index):
        """Keep content stable on category switch and show submenu when appropriate."""
        if self._suppress_tab_change:
            return

        category = self.tabs.tabText(index)
        entries = self._get_category_entries(category)

        if self.on_category_changed:
            self.on_category_changed(category)

        if category == self.settings_category:
            self.content_category = self.settings_category
            self.open_menu_category = None
            self.set_submenu_visible(False)
            return

        if len(entries) == 1:
            self.open_menu_category = None
            self.set_submenu_visible(False)
            self._restore_content_category_tab()
            return

        self.open_menu_category = category
        self._build_submenu_for_category(category)
        self.set_submenu_visible(True)
        self._restore_content_category_tab()

    def handle_event_filter(self, obj, event):
        """Handle submenu reflow and click-outside collapse events."""
        tab_bar = self.tabs.tabBar() if self.tabs is not None else None

        if tab_bar is not None and obj == tab_bar and event.type() in (QEvent.Resize, QEvent.Show):
            if self.category_submenu is not None and self.category_submenu.isVisible():
                self.reposition_submenu()

        if event.type() == QEvent.MouseButtonPress:
            if self.category_submenu is not None and self.category_submenu.isVisible():
                global_pos = None
                if hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                elif hasattr(event, "globalPos"):
                    global_pos = event.globalPos()

                if global_pos is not None:
                    submenu_hit = self._global_pos_in_widget(self.category_submenu, global_pos)
                    tabbar_hit = self._global_pos_in_widget(tab_bar, global_pos)
                    if not submenu_hit and not tabbar_hit:
                        if self.open_menu_category:
                            self.category_collapsed.add(self.open_menu_category)
                        self.open_menu_category = None
                        self.set_submenu_visible(False)

    def handle_resize(self):
        """Reposition submenu on host window resize."""
        if self.category_submenu is not None and self.category_submenu.isVisible():
            self.reposition_submenu()

    @staticmethod
    def _global_pos_in_widget(widget, global_pos):
        if widget is None or not widget.isVisible():
            return False

        top_left = widget.mapToGlobal(QPoint(0, 0))
        local = global_pos - top_left
        return widget.rect().contains(local)
