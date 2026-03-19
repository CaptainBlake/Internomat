import threading

from PySide6.QtCore import Qt, Signal, QObject
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
    QDialog,
    QTextEdit
)
import db
import threading
import services.crawler as crawler
import services.matchzy_db as matchzy
from services.logger import get_log_history
import core


update_running = False


class UiDispatcher(QObject):
    add_player_success = Signal(object)
    add_player_error = Signal(object)
    update_progress = Signal(int, int)
    update_player_ready = Signal(object)
    update_finished = Signal()
    update_error = Signal(object)


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
    db_tree.setHorizontalHeaderLabels(["Player", "Rating"])
    db_tree.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    db_tree.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    db_tree.verticalHeader().setVisible(False)
    db_tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    db_tree.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    pool_tree = QTableWidget(0, 3)
    pool_tree.setHorizontalHeaderLabels(["#", "Player", "Rating"])
    pool_tree.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    pool_tree.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    pool_tree.verticalHeader().setVisible(False)
    pool_tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    pool_tree.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    pool_tree.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

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

    lists_layout.addWidget(db_tree, 2)
    lists_layout.addWidget(btn_frame, 0)
    lists_layout.addWidget(pool_tree, 2)
    layout.addWidget(lists_frame, 1)

    control_frame = QFrame()
    control_frame.setStyleSheet("""
        QFrame {
            background: #ECEFF1;
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

    ct_layout = QVBoxLayout(ct_frame)
    t_layout = QVBoxLayout(t_frame)

    ct_title = QLabel("Counter Terrorists")
    t_title = QLabel("Terrorists")
    ct_total = QLabel("Total: 0")
    t_total = QLabel("Total: 0")

    team_a_tree = QTableWidget(0, 2)
    team_b_tree = QTableWidget(0, 2)

    for tree in (team_a_tree, team_b_tree):
        tree.setHorizontalHeaderLabels(["Player", "Rating"])
        tree.verticalHeader().setVisible(False)
        tree.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    ct_layout.addWidget(ct_title)
    ct_layout.addWidget(team_a_tree, 1)
    ct_layout.addWidget(ct_total)

    t_layout.addWidget(t_title)
    t_layout.addWidget(team_b_tree, 1)
    t_layout.addWidget(t_total)

    result_layout.addWidget(ct_frame, 1)
    result_layout.addWidget(t_frame, 1)
    layout.addWidget(result_frame, 1)

    diff_label = QLabel("Rating Difference: 0")
    diff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(diff_label)

    def refresh_players():
        db_tree.setRowCount(0)
        for p in db.get_players():
            row = db_tree.rowCount()
            db_tree.insertRow(row)

            name_item = QTableWidgetItem(str(p[1]))
            name_item.setData(Qt.ItemDataRole.UserRole, str(p[0]))

            rating_item = QTableWidgetItem(str(p[2]))
            rating_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            db_tree.setItem(row, 0, name_item)
            db_tree.setItem(row, 1, rating_item)

    def refresh_pool_display():
        for i in range(pool_tree.rowCount()):
            pool_tree.item(i, 0).setText(str(i + 1))

    def clear_table(table):
        table.setRowCount(0)

    def get_pool_players():
        players = []
        for row in range(pool_tree.rowCount()):
            pid = str(pool_tree.item(row, 0).data(Qt.ItemDataRole.UserRole))
            name = pool_tree.item(row, 1).text()
            rating = int(pool_tree.item(row, 2).text())
            players.append((pid, name, rating))
        return players

    def show_error(title, text):
        dialog = QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.resize(700, 500)

        layout = QVBoxLayout(dialog)

        text_box = QTextEdit()
        text_box.setReadOnly(True)

        # --- get last 100 logs ---
        logs = get_log_history()[-100:]
        log_text = "\n".join(logs)

        # --- combine error + logs ---
        full_text = (
            f"=== ERROR ===\n{text}\n\n"
            f"=== LAST 100 LOG ENTRIES ===\n{log_text}"
        )

        text_box.setText(full_text)
        layout.addWidget(text_box)

        # buttons
        copy_button = QPushButton("Copy All")
        copy_button.clicked.connect(lambda: text_box.selectAll() or text_box.copy())

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)

        layout.addWidget(copy_button)
        layout.addWidget(close_button)

        dialog.exec()

    def show_info(title, text):
        QMessageBox.information(parent, title, text)

    def add_player():
        url = entry.text().strip()
        if not url:
            show_error("Error", "Enter Steam profile URL")
            return

        add_button.setEnabled(False)

        def worker():
            try:
                player = crawler.fetch_player(url)
                dispatcher.add_player_success.emit(player)
            except Exception as e:
                dispatcher.add_player_error.emit(e)

        threading.Thread(target=worker, daemon=True).start()

    def on_add_player_success(player):
        db.upsert_player(player)
        refresh_players()
        entry.clear()
        add_button.setEnabled(True)

    def on_add_player_error(e):
        show_error("Error", str(e))
        add_button.setEnabled(True)

    dispatcher.add_player_success.connect(on_add_player_success)
    dispatcher.add_player_error.connect(on_add_player_error)

    def add_to_pool():
        selected_rows = db_tree.selectionModel().selectedRows()
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
        for row in rows:
            pool_tree.removeRow(row)
        refresh_pool_display()

    def remove_player():
        rows = sorted({r.row() for r in db_tree.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            show_error("Error", "Select a player to remove")
            return

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
            db.delete_player(pid)
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

        update_running = True
        update_button.setEnabled(False)
        update_button.setText("Updating...")

        steam_ids = db.get_players_to_update()
        if not steam_ids:
            show_info("Update", "All players were updated recently.\nTry again later.")
            update_running = False
            update_button.setEnabled(True)
            update_button.setText("Update")
            return

        total = len(steam_ids)
        update_button.setText(f"Updating 0/{total}")

        def on_progress(i, total_count):
            update_button.setText(f"Updating {i}/{total_count}")

        def on_player(player):
            if player:
                db.update_player(player)
                refresh_players()

        def finish():
            global update_running
            update_running = False
            update_button.setEnabled(True)
            update_button.setText("Update")

        def on_error(e):
            show_error("Error", str(e))
            finish()

        def worker():
            try:
                # --- PLAYER UPDATES ---
                for i, steam_id in enumerate(steam_ids, start=1):
                    try:
                        player = crawler.get_leetify_player(steam_id)
                        dispatcher.update_player_ready.emit(player)
                    except Exception as e:
                        dispatcher.update_error.emit(e)
                        return

                    dispatcher.update_progress.emit(i, total)

                # --- MATCHZY SYNC (NEW) ---
                try:
                    matchzy.sync()
                except Exception as e:
                    dispatcher.update_error.emit(e)
                    return

                dispatcher.update_finished.emit()

            except Exception as e:
                dispatcher.update_error.emit(e)

        dispatcher.update_progress.connect(on_progress)
        dispatcher.update_player_ready.connect(on_player)
        dispatcher.update_error.connect(on_error)
        dispatcher.update_finished.connect(finish)

        threading.Thread(target=worker, daemon=True).start()

    def run_balancer():
        players = get_pool_players()

        if len(players) < 2:
            show_error("Error", "Add players to pool first")
            return

        if len(players) % 2 != 0:
            show_error("Error", "Player count must be even")
            return

        tolerance = tolerance_slider.value()
        (team_a, team_b), diff = core.balance_teams(players, tolerance=tolerance)

        clear_table(team_a_tree)
        clear_table(team_b_tree)

        team_a = sorted(team_a, key=lambda p: p[2], reverse=True)
        team_b = sorted(team_b, key=lambda p: p[2], reverse=True)

        sum_a = 0
        for p in team_a:
            row = team_a_tree.rowCount()
            team_a_tree.insertRow(row)
            team_a_tree.setItem(row, 0, QTableWidgetItem(p[1]))
            rating_item = QTableWidgetItem(str(p[2]))
            rating_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            team_a_tree.setItem(row, 1, rating_item)
            sum_a += p[2]

        sum_b = 0
        for p in team_b:
            row = team_b_tree.rowCount()
            team_b_tree.insertRow(row)
            team_b_tree.setItem(row, 0, QTableWidgetItem(p[1]))
            rating_item = QTableWidgetItem(str(p[2]))
            rating_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            team_b_tree.setItem(row, 1, rating_item)
            sum_b += p[2]

        ct_total.setText(f"Total: {sum_a}")
        t_total.setText(f"Total: {sum_b}")
        diff_label.setText(f"Rating Difference: {diff}")

    add_button.clicked.connect(add_player)
    update_button.clicked.connect(update_players)
    remove_button.clicked.connect(remove_player)
    add_to_pool_button.clicked.connect(add_to_pool)
    remove_from_pool_button.clicked.connect(remove_from_pool)
    generate_button.clicked.connect(run_balancer)
    db_tree.itemDoubleClicked.connect(lambda _: add_to_pool())
    pool_tree.itemDoubleClicked.connect(lambda _: remove_from_pool())

    refresh_players()