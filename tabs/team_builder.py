import tkinter as tk
from tkinter import messagebox, ttk

import core
import db
import threading
import time


update_running = False


def sort_treeview(tree, col, reverse):

    data = [(tree.set(k, col), k) for k in tree.get_children('')]

    if col == "rating":
        data.sort(key=lambda x: int(x[0]), reverse=reverse)
    else:
        data.sort(key=lambda x: x[0].lower(), reverse=reverse)

    for index, (val, k) in enumerate(data):
        tree.move(k, '', index)

    tree.heading(col, command=lambda: sort_treeview(tree, col, not reverse))


def build_team_tab(root, parent):

    def update_players():

        global update_running

        if update_running:
            messagebox.showinfo("Update", "Update already running")
            return

        update_running = True

        update_button.config(state="disabled")
        update_button.config(text="Updating...")

        def finish():
            global update_running
            update_running = False
            update_button.config(state="normal")
            update_button.config(text="Update")
            refresh_players()

        def worker():

            try:
                steam_ids = db.get_players_to_update()

                if not steam_ids:
                    root.after(0, finish)
                    return

                total = len(steam_ids)

                for i, steam_id in enumerate(steam_ids, start=1):

                    root.after(
                        0,
                        lambda i=i, total=total:
                        update_button.config(text=f"Updating {i}/{total}")
                    )

                    try:
                        player = core.get_leetify_player(steam_id)
                        db.update_player(player)

                    except Exception as e:
                        print(f"Update failed for {steam_id}: {e}")

                    time.sleep(1)

            finally:
                root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_players():

        for row in db_tree.get_children():
            db_tree.delete(row)

        for p in db.get_players():

            db_tree.insert(
                "",
                "end",
                iid=str(p[0]),
                values=(p[1], p[2])
            )

    def add_player():

        url = entry.get().strip()
        url_copy = url

        if not url:
            messagebox.showerror("Error", "Enter Steam profile URL")
            return

        add_button.config(state="disabled")

        def worker():

            try:
                steam_id = core.get_player_identifier(url_copy)

                player = core.get_leetify_player(steam_id)

                if db.player_exists(steam_id):
                    db.update_player(player)
                else:
                    db.insert_player(player)

                def finish():
                    refresh_players()
                    entry.delete(0, tk.END)
                    add_button.config(state="normal")

                root.after(0, finish)

            except Exception as e:

                def fail():
                    messagebox.showerror("Error", str(e))
                    add_button.config(state="normal")

                root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    def remove_player():

        selected = db_tree.selection()

        if not selected:
            messagebox.showerror("Error", "Select a player to remove")
            return

        confirm = messagebox.askyesno(
            "Confirm",
            "Remove selected player(s) from database?"
        )

        if not confirm:
            return

        for item in selected:

            steam_id = item

            db.delete_player(steam_id)

            if pool_tree.exists(item):
                pool_tree.delete(item)

        refresh_players()

    def add_to_pool():

        for item in db_tree.selection():

            values = db_tree.item(item)["values"]

            if not pool_tree.exists(item):

                pool_tree.insert(
                    "",
                    "end",
                    iid=item,
                    values=values
                )

    def remove_from_pool():

        for item in pool_tree.selection():
            pool_tree.delete(item)

    def get_pool_players():

        players = []

        for item in pool_tree.get_children():

            values = pool_tree.item(item)["values"]

            players.append((item, values[0], int(values[1])))

        return players

    def run_balancer():

        players = get_pool_players()

        if len(players) < 2:
            messagebox.showerror("Error", "Add players to pool first")
            return

        if len(players) % 2 != 0:
            messagebox.showerror("Error", "Player count must be even")
            return

        (team_a, team_b), diff = core.balance_teams(players)

        for row in team_a_tree.get_children():
            team_a_tree.delete(row)

        for row in team_b_tree.get_children():
            team_b_tree.delete(row)

        team_a = sorted(team_a, key=lambda p: p[2], reverse=True)
        team_b = sorted(team_b, key=lambda p: p[2], reverse=True)

        sum_a = 0
        for p in team_a:
            team_a_tree.insert("", "end", values=(p[1], p[2]))
            sum_a += p[2]

        sum_b = 0
        for p in team_b:
            team_b_tree.insert("", "end", values=(p[1], p[2]))
            sum_b += p[2]

        team_a_total.config(text=f"Total: {sum_a}")
        team_b_total.config(text=f"Total: {sum_b}")

        if diff < 500:
            color = "green"
            text = f"Balanced ✔  (Difference: {diff})"
        elif diff < 1500:
            color = "orange"
            text = f"Acceptable ⚠  (Difference: {diff})"
        else:
            color = "red"
            text = f"Unbalanced ✖  (Difference: {diff})"

        diff_label.config(text=text, fg=color)

    # UI

    top_frame = tk.Frame(parent)
    top_frame.pack(fill="x", padx=10, pady=10)

    def limit_length(new_value):
        return len(new_value) <= 80

    vcmd = root.register(limit_length)

    entry = tk.Entry(
        top_frame,
        validate="key",
        validatecommand=(vcmd, "%P")
    )

    entry.pack(side="left", fill="x", expand=True, padx=(0,10))

    add_button = tk.Button(top_frame, text="Add Player", command=add_player)
    add_button.pack(side="left", padx=5)

    tk.Button(top_frame, text="Remove Player", command=remove_player).pack(side="left", padx=5)

    update_button = tk.Button(top_frame, text="Update", command=update_players)
    update_button.pack(side="left", padx=5)

    lists_frame = tk.Frame(parent)
    lists_frame.pack(fill="both", expand=True, padx=10, pady=5)

    db_frame = tk.Frame(lists_frame)
    db_frame.pack(side="left", fill="both", expand=True)

    tk.Label(db_frame, text="Player Database").pack()

    db_tree = ttk.Treeview(
        db_frame,
        columns=("name", "rating"),
        show="headings",
        selectmode="extended"
    )

    db_tree.heading("name", text="Player", command=lambda: sort_treeview(db_tree, "name", False))
    db_tree.heading("rating", text="Rating", command=lambda: sort_treeview(db_tree, "rating", True))
    db_tree.bind("<Double-1>", lambda e: add_to_pool() if db_tree.selection() else None)

    db_scroll = ttk.Scrollbar(db_frame, orient="vertical", command=db_tree.yview)
    db_tree.configure(yscrollcommand=db_scroll.set)

    db_scroll.pack(side="right", fill="y")
    db_tree.pack(fill="both", expand=True)

    mid_frame = tk.Frame(lists_frame)
    mid_frame.pack(side="left", padx=10)

    tk.Button(mid_frame, text=">", width=4, command=add_to_pool).pack(pady=5)
    tk.Button(mid_frame, text="<", width=4, command=remove_from_pool).pack(pady=5)

    pool_frame = tk.Frame(lists_frame)
    pool_frame.pack(side="left", fill="both", expand=True)

    tk.Label(pool_frame, text="Player Pool").pack()

    pool_tree = ttk.Treeview(
        pool_frame,
        columns=("name", "rating"),
        show="headings",
        selectmode="extended"
    )

    pool_tree.heading("name", text="Player")
    pool_tree.heading("rating", text="Rating")

    pool_scroll = ttk.Scrollbar(pool_frame, orient="vertical", command=pool_tree.yview)
    pool_tree.configure(yscrollcommand=pool_scroll.set)
    pool_tree.bind("<Double-1>", lambda e: remove_from_pool() if pool_tree.selection() else None)

    pool_scroll.pack(side="right", fill="y")
    pool_tree.pack(fill="both", expand=True)

    tk.Button(parent, text="Generate Teams", command=run_balancer).pack(pady=10)

    result_frame = tk.Frame(parent)
    result_frame.pack(fill="both", padx=10, pady=10)

    team_a_frame = tk.LabelFrame(result_frame, text="TEAM A", bg="#e8f1ff", padx=5, pady=5)
    team_a_frame.pack(side="left", fill="both", expand=True, padx=5)

    team_b_frame = tk.LabelFrame(result_frame, text="TEAM B", bg="#ffecec", padx=5, pady=5)
    team_b_frame.pack(side="left", fill="both", expand=True, padx=5)

    team_a_tree = ttk.Treeview(team_a_frame, columns=("name", "rating"), show="headings", height=6)
    team_a_tree.heading("name", text="Player")
    team_a_tree.heading("rating", text="Rating")
    team_a_tree.pack(fill="both", expand=True)

    team_b_tree = ttk.Treeview(team_b_frame, columns=("name", "rating"), show="headings", height=6)
    team_b_tree.heading("name", text="Player")
    team_b_tree.heading("rating", text="Rating")
    team_b_tree.pack(fill="both", expand=True)

    team_a_total = tk.Label(team_a_frame, text="Total: 0", bg="#e8f1ff", font=("Segoe UI", 9, "bold"))
    team_a_total.pack(pady=4)

    team_b_total = tk.Label(team_b_frame, text="Total: 0", bg="#ffecec", font=("Segoe UI", 9, "bold"))
    team_b_total.pack(pady=4)

    balance_frame = tk.Frame(parent)
    balance_frame.pack(pady=(0,10))

    separator = ttk.Separator(balance_frame, orient="horizontal")
    separator.pack(fill="x", pady=5)

    diff_label = tk.Label(balance_frame, text="Rating Difference: 0", font=("Segoe UI", 10, "bold"))
    diff_label.pack()

    refresh_players()