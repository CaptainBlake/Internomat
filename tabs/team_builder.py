import tkinter as tk
from tkinter import messagebox, ttk


import db
import threading
import crawler
import core

BALANCED_THRESHOLD = 2500
ACCEPTABLE_THRESHOLD = 5000

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

    tolerance_var = tk.IntVar(value=1000)

    def update_players():

        def success(_):
            finish()

        def error(e):
            messagebox.showerror("Error", str(e))
            finish()

        def finish():
            global update_running
            update_running = False
            update_button.config(state="normal")
            update_button.config(text="Update")
     
        global update_running

        if update_running:
            messagebox.showinfo("Update", "Update already running")
            return

        update_running = True

        update_button.config(state="disabled")
        update_button.config(text="Updating...")

        steam_ids = db.get_players_to_update()

        if not steam_ids:
            messagebox.showinfo(
                "Update",
                "All players were updated recently.\nTry again later."
            )
            update_running = False
            finish()
            return

        total = len(steam_ids)
        update_button.config(text=f"Updating 0/{total}")

        def task():

            def progress(i, total):
                root.after(
                    0,
                    lambda: update_button.config(text=f"Updating {i}/{total}")
                )

            def handle_player(player):
                if player:
                    # update DB + UI immediately
                    root.after(0, lambda: db.update_player(player))
                    root.after(0, refresh_players)

            return crawler.fetch_players_bulk(
                steam_ids,
                on_progress=progress,
                on_player=handle_player
            )

        run_async(task, success, error)

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

        if not url:
            messagebox.showerror("Error", "Enter Steam profile URL")
            return

        add_button.config(state="disabled")

        def task():
            return crawler.fetch_player(url)

        def success(player):
            db.upsert_player(player)
            refresh_players()
            entry.delete(0, tk.END)
            add_button.config(state="normal")

        def error(e):
            messagebox.showerror("Error", str(e))
            add_button.config(state="normal")

        run_async(task, success, error)

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
                    values=("", values[0], values[1])  # FIXED
                )

        refresh_pool_display()

    def remove_from_pool():
        for item in pool_tree.selection():
            pool_tree.delete(item)

        refresh_pool_display()

    def get_pool_players():
        players = []

        for item in pool_tree.get_children():
            values = pool_tree.item(item)["values"]

            name = values[1]
            rating = int(values[2])

            players.append((item, name, rating))

        return players

    def run_async(task, on_success=None, on_error=None):
        def wrapper():
            try:
                result = task()
                if on_success:
                    root.after(0, lambda: on_success(result))
            except Exception as e:
                if on_error:
                    root.after(0, lambda: on_error(e))

        threading.Thread(target=wrapper, daemon=True).start()
    
    # --- TOP CONTROLS ---
    def create_top_controls():
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
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        add_button = tk.Button(top_frame, text="Add Player", command=add_player)
        add_button.pack(side="left", padx=5)

        tk.Button(top_frame, text="Remove Player", command=remove_player).pack(side="left", padx=5)

        update_button = tk.Button(top_frame, text="Update", command=update_players)
        update_button.pack(side="left", padx=5)

        return entry, add_button, update_button

    def run_balancer():

        players = get_pool_players()

        if len(players) < 2:
            messagebox.showerror("Error", "Add players to pool first")
            return

        if len(players) % 2 != 0:
            messagebox.showerror("Error", "Player count must be even")
            return

        # calling core function for balancing alg.
        tolerance = tolerance_var.get()


        (team_a, team_b), diff = core.balance_teams(
            players,
            tolerance=tolerance
        )

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

        if diff < BALANCED_THRESHOLD:
            color = "green"
            text = f"Balanced ✔  (Difference: {diff})"
        elif diff < ACCEPTABLE_THRESHOLD:
            color = "orange"
            text = f"Acceptable ⚠  (Difference: {diff})"
        else:
            color = "red"
            text = f"Unbalanced ✖  (Difference: {diff})"

        diff_label.config(text=text, fg=color)


    # --- DATABASE VIEW ---
    def create_database_view(lists_frame):
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

        return db_tree


    # --- PLAYER POOL ---
    def create_pool_view(lists_frame):
        pool_frame = tk.Frame(lists_frame)
        pool_frame.pack(side="left", fill="both", expand=True)

        tk.Label(pool_frame, text="Player Pool").pack()

        pool_tree = ttk.Treeview(
            pool_frame,
            columns=("index", "name", "rating"),
            show="headings",
            selectmode="extended"
        )

        pool_tree.heading("index", text="#")
        pool_tree.heading("name", text="Player", command=lambda: sort_treeview(pool_tree, "name", False))
        pool_tree.heading("rating", text="Rating", command=lambda: sort_treeview(pool_tree, "rating", True))

        pool_tree.column("index", width=40, anchor="center")
        pool_tree.column("name", width=140)
        pool_tree.column("rating", width=80, anchor="center")

        # zebra stripes
        pool_tree.tag_configure("even", background="#f2f2f2")
        pool_tree.tag_configure("odd", background="#ffffff")

        pool_scroll = ttk.Scrollbar(pool_frame, orient="vertical", command=pool_tree.yview)
        pool_tree.configure(yscrollcommand=pool_scroll.set)

        pool_tree.bind("<Double-1>", lambda e: remove_from_pool() if pool_tree.selection() else None)

        # --- DRAG & DROP ---
        def on_drag_start(event):
            pool_tree._drag_item = pool_tree.identify_row(event.y)

        def on_drag_motion(event):
            row = pool_tree.identify_row(event.y)

            if row and hasattr(pool_tree, "_drag_item"):
                if row != pool_tree._drag_item:
                    pool_tree.move(pool_tree._drag_item, "", pool_tree.index(row))

        def on_drag_drop(event):
            refresh_pool_display()

        pool_tree.bind("<ButtonPress-1>", on_drag_start)
        pool_tree.bind("<B1-Motion>", on_drag_motion)
        pool_tree.bind("<ButtonRelease-1>", on_drag_drop)

        pool_scroll.pack(side="right", fill="y")
        pool_tree.pack(fill="both", expand=True)

        return pool_tree


    # --- MID CONTROLS ---
    def create_mid_controls(lists_frame):
        mid_frame = tk.Frame(lists_frame)
        mid_frame.pack(side="left", padx=10)

        tk.Button(mid_frame, text=">", width=4, command=add_to_pool).pack(pady=5)
        tk.Button(mid_frame, text="<", width=4, command=remove_from_pool).pack(pady=5)


    # --- RESULTS VIEW ---
    def create_results_view():
        control_frame = tk.Frame(parent)
        control_frame.pack(pady=10)

        # --- tolerance description ---
        tk.Label(
            control_frame,
            text="Tolerance:",
            font=("Segoe UI", 9)
        ).pack(side="left", padx=(0, 5))

        # --- tolerance value ---
        tolerance_label = tk.Label(
            control_frame,
            text=str(tolerance_var.get()),
            width=5
        )
        tolerance_label.pack(side="left", padx=(0, 5))

        # --- tolerance slider ---
        tolerance_slider = tk.Scale(
            control_frame,
            from_=0,
            to=5000,
            orient="horizontal",
            variable=tolerance_var,
            showvalue=False,
            length=100
        )
        tolerance_slider.pack(side="left", padx=5)

        def update_tolerance_label(val):
            tolerance_label.config(text=str(int(val)))

        tolerance_slider.config(command=update_tolerance_label)

        # --- generate button ---
        tk.Button(control_frame, text="Generate Teams", command=run_balancer).pack(side="left", padx=10)

        result_frame = tk.Frame(parent)
        result_frame.pack(fill="both", padx=10, pady=10)

        team_a_frame = tk.LabelFrame(result_frame, text="Counter Terrorists", bg="#bfd7ff", padx=5, pady=5)
        team_a_frame.pack(side="left", fill="both", expand=True, padx=5)

        team_b_frame = tk.LabelFrame(result_frame, text="Terrorists", bg="#ffc4c4", padx=5, pady=5)
        team_b_frame.pack(side="left", fill="both", expand=True, padx=5)

        team_a_tree = ttk.Treeview(team_a_frame, columns=("name", "rating"), show="headings", height=6)
        team_b_tree = ttk.Treeview(team_b_frame, columns=("name", "rating"), show="headings", height=6)

        for tree in (team_a_tree, team_b_tree):
            tree.heading("name", text="Player")
            tree.heading("rating", text="Rating")
            tree.pack(fill="both", expand=True)

        team_a_total = tk.Label(team_a_frame, text="Total: 0", bg="#e8f1ff", font=("Segoe UI", 9, "bold"))
        team_a_total.pack(pady=4)

        team_b_total = tk.Label(team_b_frame, text="Total: 0", bg="#ffecec", font=("Segoe UI", 9, "bold"))
        team_b_total.pack(pady=4)

        balance_frame = tk.Frame(parent)
        balance_frame.pack(pady=(0, 10))

        ttk.Separator(balance_frame, orient="horizontal").pack(fill="x", pady=5)

        diff_label = tk.Label(balance_frame, text="Rating Difference: 0", font=("Segoe UI", 10, "bold"))
        diff_label.pack()

        return team_a_tree, team_b_tree, team_a_total, team_b_total, diff_label


    # --- POOL REFRESH ---
    def refresh_pool_display():
        for i, item in enumerate(pool_tree.get_children(), start=1):
            values = pool_tree.item(item)["values"]

            tag = "even" if i % 2 == 0 else "odd"

            pool_tree.item(
                item,
                values=(i, values[1], values[2]),
                tags=(tag,)
            )


    # --- BUILD UI ---
    entry, add_button, update_button = create_top_controls()

    lists_frame = tk.Frame(parent)
    lists_frame.pack(fill="both", expand=True, padx=10, pady=5)

    db_tree = create_database_view(lists_frame)
    create_mid_controls(lists_frame)
    pool_tree = create_pool_view(lists_frame)

    team_a_tree, team_b_tree, team_a_total, team_b_total, diff_label = create_results_view()

    refresh_players()