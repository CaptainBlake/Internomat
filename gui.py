import tkinter as tk
from tkinter import messagebox, ttk

import core
import db
import threading
import time

update_running = False

def start_gui():

    root = tk.Tk()
    root.title("Internomat")
    root.geometry("900x700")


    def update_players():

        global update_running

        if update_running:
            messagebox.showinfo("Update", "Update already running")
            return

        update_running = True

        update_button.config(state="disabled")
        update_button.config(text="Updating...")

        def worker():

            global update_running

            try:
                steam_ids = db.get_players_to_update()
                total = len(steam_ids)
                for steam_id in steam_ids:
                    root.after(0, lambda i=i, total=total:
                        update_button.config(text=f"Updating {i}/{total}")
                    )
                    try:
                        player = core.get_leetify_player(steam_id)
                        db.update_player(player)

                    except Exception as e:
                        print(f"Update failed for {steam_id}: {e}")

                    time.sleep(1)

            finally:

                def finish():
                    global update_running
                    update_running = False
                    update_button.config(state="normal")
                    update_button.config(text="Update")
                    refresh_players()

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


    def sort_treeview(tree, col, reverse):

        data = [(tree.set(k, col), k) for k in tree.get_children('')]

        data.sort(reverse=reverse)

        for index, (val, k) in enumerate(data):
            tree.move(k, '', index)

        tree.heading(col, command=lambda: sort_treeview(tree, col, not reverse))


    def add_player():

        url = entry.get().strip()

        if not url:
            messagebox.showerror("Error", "Enter Steam profile URL")
            return

        try:

            steam_id = core.get_player_identifier(url)

            player = core.get_leetify_player(steam_id)

            
            if db.player_exists(steam_id):
                db.update_player(player)
            else:
                db.insert_player(player)

            refresh_players()

            entry.delete(0, tk.END)

        except Exception as e:
            messagebox.showerror("Error", str(e))

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

            # also remove from pool if present
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

        output.delete("1.0", tk.END)

        output.insert(tk.END, "TEAM A\n\n")

        sum_a = 0
        for p in team_a:
            output.insert(tk.END, f"{p[1]} ({p[2]})\n")
            sum_a += p[2]

        output.insert(tk.END, f"\nTotal: {sum_a}\n\n")

        output.insert(tk.END, "TEAM B\n\n")

        sum_b = 0
        for p in team_b:
            output.insert(tk.END, f"{p[1]} ({p[2]})\n")
            sum_b += p[2]

        output.insert(tk.END, f"\nTotal: {sum_b}\n")
        output.insert(tk.END, f"\nDifference: {diff}")


    # ADD PLAYER UI

    top_frame = tk.Frame(root)
    top_frame.pack(fill="x", padx=10, pady=10)

    # limit entry to 80 chars
    def limit_length(new_value):
        return len(new_value) <= 80
    
    vcmd = root.register(limit_length)

    entry = tk.Entry(
        top_frame,
        validate="key",
        validatecommand=(vcmd, "%P")
    )

    entry.pack(side="left", fill="x", expand=True, padx=(0,10))

    tk.Button(
        top_frame,
        text="Add Player",
        command=add_player
    ).pack(side="left", padx=5)

    tk.Button(
        top_frame,
        text="Remove Player",
        command=remove_player
    ).pack(side="left", padx=5)

    update_button = tk.Button(
        top_frame,
        text="Update",
        command=update_players
    )

    update_button.pack(side="left", padx=5)


    # SPLIT SCREEN


    lists_frame = tk.Frame(root)
    lists_frame.pack(fill="both", expand=True, padx=10, pady=5)

    # ---------- DATABASE LIST ----------

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

    
    
    db_scroll = ttk.Scrollbar(db_frame, orient="vertical", command=db_tree.yview)
    db_tree.configure(yscrollcommand=db_scroll.set)

    db_scroll.pack(side="right", fill="y")
    db_tree.pack(fill="both", expand=True)

    # ---------- BUTTONS ----------

    mid_frame = tk.Frame(lists_frame)
    mid_frame.pack(side="left", padx=10)

    tk.Button(mid_frame, text=">", width=4, command=add_to_pool).pack(pady=5)
    tk.Button(mid_frame, text="<", width=4, command=remove_from_pool).pack(pady=5)

    # ---------- PLAYER POOL ----------

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

    pool_scroll.pack(side="right", fill="y")
    pool_tree.pack(fill="both", expand=True)

    # GENERATE TEAMS BUTTON


    tk.Button(
        root,
        text="Generate Teams",
        command=run_balancer
    ).pack(pady=10)


    # OUTPUT


    output = tk.Text(root, height=15)
    output.pack(fill="both", padx=10, pady=10)

    # initial load
    refresh_players()

    root.mainloop()