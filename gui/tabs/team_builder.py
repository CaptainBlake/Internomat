from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
)

import db.players as player_db
import threading
import services.crawler as crawler
import services.logger as logger
import core


update_running = False


class UiDispatcher(QObject):
    add_player_success = Signal(object)
    add_player_error = Signal(object)
    update_progress = Signal(int, int)
    update_player_ready = Signal(object)
    update_finished = Signal()
    update_error = Signal(object)
    balance_finished = Signal(object, object, int)
    balance_error = Signal(object)


def _apply_table_style(table):
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    table.horizontalHeader().setStretchLastSection(False)

    table.setStyleSheet("""
        QTableWidget {
            background: transparent;
            border: none;
            outline: none;
            alternate-background-color: #F8FCFA;
            color: #20443D;
        }
        QTableWidget:focus {
            border: none;
            outline: none;
        }
        QTableWidget::item {
            padding: 6px;
            border: none;
            outline: none;
        }
        QTableWidget::item:selected {
            background: #DFF7EF;
            color: #4A7168;
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
    """)

    table.horizontalHeader().setStyleSheet("""
        QHeaderView {
            border: none;
            background: transparent;
        }
        QHeaderView::section {
            background: #EAF8F3;
            color: #4A7168;
            padding: 10px;
            border: none;
            font-size: 12pt;
            font-weight: 800;
            text-align: center;
        }
    """)

    header_font = QFont()
    header_font.setPointSize(12)
    header_font.setBold(True)

    for i in range(table.columnCount()):
        item = table.horizontalHeaderItem(i)
        if item is not None:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFont(header_font)


def _apply_result_table_style(table):
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().hide()
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

    table.setStyleSheet("""
        QTableWidget {
            background: #FFFFFF;
            border: none;
            outline: none;
            alternate-background-color: #F7FAFD;
            color: #1E2B38;
        }
        QTableWidget:focus {
            border: none;
            outline: none;
        }
        QTableWidget::item {
            padding: 10px 8px;
            border: none;
            outline: none;
            background: transparent;
            color: #1E2B38;
        }
        QTableWidget::item:selected {
            background: #DCEAF7;
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
    """)


def _build_card(title_text, table, title_color="#DCEAF7", title_text_color="#2E4C69"):
    card = QFrame()
    card.setStyleSheet("""
        QFrame {
            background: rgba(255, 255, 255, 0.94);
            border: none;
            border-radius: 16px;
        }
    """)

    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(0, 0, 0, 0)
    card_layout.setSpacing(0)

    title = QLabel(title_text)
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet(f"""
        QLabel {{
            background: {title_color};
            color: {title_text_color};
            padding: 8px 12px;
            font-size: 13px;
            font-weight: 800;
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
        }}
    """)

    card_layout.addWidget(title)
    card_layout.addWidget(table, 1)
    return card


def build_team_tab(parent):
    dispatcher = UiDispatcher(parent)

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(10)

    top_frame = QFrame()
    top_layout = QHBoxLayout(top_frame)
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(8)

    entry = QLineEdit()
    entry.setPlaceholderText("Steam profile URL")

    add_button = QPushButton("Add Player")
    remove_button = QPushButton("Remove Player")
    update_button = QPushButton("Update")

    top_layout.addWidget(entry, 1)
    top_layout.addWidget(add_button)
    top_layout.addWidget(remove_button)
    top_layout.addWidget(update_button)
    layout.addWidget(top_frame)

    lists_frame = QFrame()
    lists_layout = QHBoxLayout(lists_frame)
    lists_layout.setContentsMargins(0, 0, 0, 0)
    lists_layout.setSpacing(10)

    db_tree = QTableWidget(0, 2)
    db_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    db_tree.setHorizontalHeaderLabels(["Player", "Rating"])
    _apply_table_style(db_tree)
    db_tree.horizontalHeader().hide()
    db_tree.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    db_tree.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    db_tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    db_tree.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    pool_tree = QTableWidget(0, 3)
    pool_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    pool_tree.setHorizontalHeaderLabels(["#", "Player", "Rating"])
    _apply_table_style(pool_tree)
    pool_tree.horizontalHeader().hide()
    pool_tree.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    pool_tree.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    pool_tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    pool_tree.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    pool_tree.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    db_card = _build_card("Player Pool", db_tree)
    pool_card = _build_card("Selected Players", pool_tree)

    btn_frame = QFrame()
    btn_layout = QVBoxLayout(btn_frame)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(8)

    add_to_pool_button = QPushButton(">")
    remove_from_pool_button = QPushButton("<")
    add_to_pool_button.setFixedWidth(44)
    remove_from_pool_button.setFixedWidth(44)

    btn_layout.addStretch(1)
    btn_layout.addWidget(add_to_pool_button, alignment=Qt.AlignmentFlag.AlignHCenter)
    btn_layout.addWidget(remove_from_pool_button, alignment=Qt.AlignmentFlag.AlignHCenter)
    btn_layout.addStretch(1)

    lists_layout.addWidget(db_card, 2)
    lists_layout.addWidget(btn_frame, 0)
    lists_layout.addWidget(pool_card, 2)
    layout.addWidget(lists_frame, 1)

    control_frame = QFrame()
    control_frame.setStyleSheet("""
        QFrame {
            background: #EAF1F8;
            border-radius: 12px;
        }
    """)
    control_layout = QHBoxLayout(control_frame)
    control_layout.setContentsMargins(16, 12, 16, 12)
    control_layout.setSpacing(10)

    tolerance_value = QLabel("1000")
    tolerance_value.setFixedWidth(50)
    tolerance_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

    tolerance_slider = QSlider(Qt.Orientation.Horizontal)
    tolerance_slider.setRange(0, 5000)
    tolerance_slider.setValue(1000)
    tolerance_slider.setFixedWidth(240)

    def update_tolerance_value(value):
        tolerance_value.setText(str(value))

    tolerance_slider.valueChanged.connect(update_tolerance_value)
    update_tolerance_value(tolerance_slider.value())

    generate_button = QPushButton("Generate Teams")

    control_layout.addStretch(1)
    control_layout.addWidget(QLabel("Tolerance:"))
    control_layout.addWidget(tolerance_value)
    control_layout.addWidget(tolerance_slider)
    control_layout.addWidget(generate_button)
    control_layout.addStretch(1)
    layout.addWidget(control_frame)

    result_frame = QFrame()
    result_layout = QHBoxLayout(result_frame)
    result_layout.setContentsMargins(0, 0, 0, 0)
    result_layout.setSpacing(10)

    ct_frame = QFrame()
    t_frame = QFrame()
    ct_frame.setStyleSheet("""
        QFrame {
            background: #FFFFFF;
            border: none;
            border-radius: 12px;
        }
    """)
    t_frame.setStyleSheet("""
        QFrame {
            background: #FFFFFF;
            border: none;
            border-radius: 12px;
        }
    """)

    ct_layout = QVBoxLayout(ct_frame)
    t_layout = QVBoxLayout(t_frame)

    ct_layout.setContentsMargins(0, 0, 0, 0)
    ct_layout.setSpacing(0)
    t_layout.setContentsMargins(0, 0, 0, 0)
    t_layout.setSpacing(0)

    team_a_tree = QTableWidget(0, 1)
    team_b_tree = QTableWidget(0, 1)

    for tree in (team_a_tree, team_b_tree):
        tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tree.setHorizontalHeaderLabels(["Player"])
        _apply_result_table_style(tree)
        tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    ct_card = _build_card("Counter Terrorists", team_a_tree, "#3A7BD5", "#FFFFFF")
    t_card = _build_card("Terrorists", team_b_tree, "#D94A4A", "#FFFFFF")

    ct_layout.addWidget(ct_card)
    ct_layout.addWidget(QLabel("Total: 0"))
    t_layout.addWidget(t_card)
    t_layout.addWidget(QLabel("Total: 0"))

    ct_total = ct_layout.itemAt(1).widget()
    t_total = t_layout.itemAt(1).widget()

    ct_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
    t_total.setAlignment(Qt.AlignmentFlag.AlignCenter)

    ct_total.setStyleSheet("""
        QLabel {
            background: #DCEAF7;
            color: #2E4C69;
            padding: 10px 12px;
            font-size: 14px;
            font-weight: 800;
            border-radius: 0px;
        }
    """)

    t_total.setStyleSheet("""
        QLabel {
            background: #F7D8D8;
            color: #7A2E2E;
            padding: 10px 12px;
            font-size: 14px;
            font-weight: 800;
            border-radius: 0px;
        }
    """)

    result_layout.addWidget(ct_frame, 1)
    result_layout.addWidget(t_frame, 1)
    layout.addWidget(result_frame, 1)

    diff_label = QLabel("Rating Difference: 0")
    diff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    diff_label.setStyleSheet("""
        QLabel {
            background: #FFFFFF;
            color: #2E4C69;
            padding: 10px 14px;
            font-size: 15px;
            font-weight: 900;
            border-radius: 12px;
            border: 1px solid #B9CADC;
        }
    """)
    layout.addWidget(diff_label)

    def on_progress(i, total_count):
        update_button.setText(f"Updating {i}/{total_count}")

    def on_player(player):
        if player:
            player_db.update_player(player)
            refresh_players()

    def finish():
        global update_running
        update_running = False
        update_button.setEnabled(True)
        update_button.setText("Update")
        logger.log("[UPDATE] Finished", level="INFO")

    def on_error(e):
        logger.log_error(f"Update failed: {e}", exc=e)
        show_error_popup(parent, "Error", str(e))
        finish()

    def refresh_pool_display():
        for i in range(pool_tree.rowCount()):
            pool_tree.item(i, 0).setText(str(i + 1))

    def clear_table(table):
        table.setRowCount(0)

    def show_error_popup(parent, title, message):
        logger.log_error(f"{title}: {message}")
        QMessageBox.critical(parent, title, message)

    def show_info(title, text):
        logger.log(f"[UI] {title}: {text}", level="INFO")
        QMessageBox.information(parent, title, text)

    def get_pool_players():
        players = []
        for row in range(pool_tree.rowCount()):
            pid = str(pool_tree.item(row, 0).data(Qt.ItemDataRole.UserRole))
            name = pool_tree.item(row, 1).text()
            rating = int(pool_tree.item(row, 2).text())
            players.append((pid, name, rating))
        return players

    def refresh_players():
        db_tree.setRowCount(0)
        players = player_db.get_players()
        for p in players:
            row = db_tree.rowCount()
            db_tree.insertRow(row)

            name_item = QTableWidgetItem(str(p[1]))
            name_item.setData(Qt.ItemDataRole.UserRole, str(p[0]))

            rating_item = QTableWidgetItem(str(p[2]))
            rating_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            db_tree.setItem(row, 0, name_item)
            db_tree.setItem(row, 1, rating_item)

        logger.log(f"[UI] Refresh players count={len(players)}", level="DEBUG")

    def add_player():
        url = entry.text().strip()
        if not url:
            show_error_popup(parent, "Error", "Enter Steam profile URL")
            return

        logger.log_user_action("Add Player", url)

        add_button.setEnabled(False)

        def worker():
            try:
                player = crawler.fetch_player(url)
                dispatcher.add_player_success.emit(player)
            except Exception as e:
                dispatcher.add_player_error.emit(e)

        threading.Thread(target=worker, daemon=True).start()

    def on_add_player_success(player):
        player_db.upsert_player(player)
        refresh_players()
        entry.clear()
        add_button.setEnabled(True)

        logger.log(f"[UI] Player added {player.get('name')}", level="INFO")

    def on_add_player_error(e):
        logger.log_error(f"Add player failed: {e}", exc=e)
        show_error_popup(parent, "Error", str(e))
        add_button.setEnabled(True)

    dispatcher.add_player_success.connect(on_add_player_success)
    dispatcher.add_player_error.connect(on_add_player_error)

    def add_to_pool():
        selected_rows = db_tree.selectionModel().selectedRows()
        logger.log_user_action("Add to Pool", f"count={len(selected_rows)}")

        for row in selected_rows:
            pid_item = db_tree.item(row.row(), 0)
            rating_item = db_tree.item(row.row(), 1)

            pid = str(pid_item.data(Qt.ItemDataRole.UserRole))
            name = pid_item.text()
            rating = rating_item.text()

            if any(str(pool_tree.item(r, 0).data(Qt.ItemDataRole.UserRole)) == pid for r in range(pool_tree.rowCount())):
                continue

            new_row = pool_tree.rowCount()
            pool_tree.insertRow(new_row)

            index_item = QTableWidgetItem(str(new_row + 1))
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            index_item.setData(Qt.ItemDataRole.UserRole, pid)

            name_item = QTableWidgetItem(name)
            rating_out = QTableWidgetItem(str(rating))
            rating_out.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            pool_tree.setItem(new_row, 0, index_item)
            pool_tree.setItem(new_row, 1, name_item)
            pool_tree.setItem(new_row, 2, rating_out)

        refresh_pool_display()

    def remove_from_pool():
        rows = sorted({r.row() for r in pool_tree.selectionModel().selectedRows()}, reverse=True)
        logger.log_user_action("Remove from Pool", f"count={len(rows)}")

        for row in rows:
            pool_tree.removeRow(row)
        refresh_pool_display()

    def remove_player():
        rows = sorted({r.row() for r in db_tree.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            show_error_popup(parent, "Error", "Select a player to remove")
            return

        logger.log_user_action("Remove Player", f"count={len(rows)}")

        confirm = QMessageBox.question(
            parent,
            "Confirm",
            "Remove selected player(s) from database?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ids = []
        for row in rows:
            pid = db_tree.item(row, 0).data(Qt.ItemDataRole.UserRole)
            ids.append(str(pid))

        for pid in ids:
            player_db.delete_player(pid)
            for row in range(pool_tree.rowCount() - 1, -1, -1):
                if str(pool_tree.item(row, 0).data(Qt.ItemDataRole.UserRole)) == pid:
                    pool_tree.removeRow(row)

        refresh_players()
        refresh_pool_display()

    def update_players():

        global update_running

        if update_running:
            show_info("Update", "Update already running")
            return

        logger.log_user_action("Update Players")

        update_running = True
        update_button.setEnabled(False)

        steam_ids = player_db.get_players_to_update() or []

        total = len(steam_ids)
        update_button.setText(f"Updating 0/{total}")

        def worker():
            core.update_players_pipeline(
                steam_ids,
                on_progress=lambda i, t: dispatcher.update_progress.emit(i, t),
                on_player=lambda p: dispatcher.update_player_ready.emit(p),
                on_error=lambda e: dispatcher.update_error.emit(e),
                on_finish=lambda: dispatcher.update_finished.emit()
            )
        threading.Thread(target=worker, daemon=True).start()

    def run_balancer():
        players = get_pool_players()

        if len(players) < 2:
            show_error_popup(parent, "Error", "Add players to pool first")
            return


        tolerance = tolerance_slider.value()

        logger.log_user_action(
            "Generate Teams",
            f"players={len(players)} tolerance={tolerance}"
        )

        generate_button.setEnabled(False)
        generate_button.setText("Generating...")

        def worker():
            try:
                (team_a, team_b), diff = core.balance_teams(players, tolerance=tolerance)
                dispatcher.balance_finished.emit(team_a, team_b, diff)
            except Exception as e:
                dispatcher.balance_error.emit(e)

        threading.Thread(target=worker, daemon=True).start()

    def on_balance_finished(team_a, team_b, diff):
        clear_table(team_a_tree)
        clear_table(team_b_tree)

        team_a = sorted(team_a, key=lambda p: p[2], reverse=True)
        team_b = sorted(team_b, key=lambda p: p[2], reverse=True)

        sum_a = 0
        for p in team_a:
            row = team_a_tree.rowCount()
            team_a_tree.insertRow(row)

            name_item = QTableWidgetItem(p[1])
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = name_item.font()
            font.setPointSize(12)
            font.setBold(True)
            name_item.setFont(font)

            team_a_tree.setItem(row, 0, name_item)
            sum_a += p[2]

        sum_b = 0
        for p in team_b:
            row = team_b_tree.rowCount()
            team_b_tree.insertRow(row)

            name_item = QTableWidgetItem(p[1])
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = name_item.font()
            font.setPointSize(12)
            font.setBold(True)
            name_item.setFont(font)

            team_b_tree.setItem(row, 0, name_item)
            sum_b += p[2]

        ct_total.setText(f"Total: {sum_a}")
        t_total.setText(f"Total: {sum_b}")
        diff_label.setText(f"Rating Difference: {diff}")

        generate_button.setEnabled(True)
        generate_button.setText("Generate Teams")
        generate_button.setFocus()

    def on_balance_error(e):
        logger.log_error(f"Balance failed: {e}", exc=e)
        show_error_popup(parent, "Error", str(e))

        generate_button.setEnabled(True)
        generate_button.setText("Generate Teams")
        generate_button.setFocus()

    add_button.clicked.connect(add_player)
    update_button.clicked.connect(update_players)
    remove_button.clicked.connect(remove_player)
    add_to_pool_button.clicked.connect(add_to_pool)
    remove_from_pool_button.clicked.connect(remove_from_pool)
    generate_button.clicked.connect(run_balancer)
    db_tree.itemDoubleClicked.connect(lambda _: add_to_pool())
    pool_tree.itemDoubleClicked.connect(lambda _: remove_from_pool())
    dispatcher.balance_finished.connect(on_balance_finished)
    dispatcher.balance_error.connect(on_balance_error)
    dispatcher.update_progress.connect(on_progress)
    dispatcher.update_player_ready.connect(on_player)
    dispatcher.update_error.connect(on_error)
    dispatcher.update_finished.connect(finish)

    refresh_players()
    return refresh_players