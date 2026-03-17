import tkinter as tk
from tkinter import messagebox, ttk

import db
import core


def build_map_tab(parent):

    # --- DATA FUNCTIONS ---

    def refresh_maps():
        for row in map_list.get_children():
            map_list.delete(row)

        for m in db.get_maps():
            map_list.insert("", "end", iid=m, values=(m,))


    def add_map():
        name = entry.get().strip()

        if not name:
            return

        db.add_map(name)
        entry.delete(0, tk.END)
        refresh_maps()


    def remove_map():
        selected = map_list.selection()

        if not selected:
            return

        for item in selected:
            db.delete_map(item)

        refresh_maps()


    def spin():
        maps = db.get_maps()

        try:
            winner = core.choose_random_map(maps)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        result_label.config(text=f"Selected Map: {winner}")


    # --- WHEEL AREA ---

    def create_wheel_area():
        wheel_frame = tk.Frame(parent)
        wheel_frame.pack(pady=20)

        tk.Label(
            wheel_frame,
            text="Map Roulette",
            font=("Segoe UI", 11, "bold")
        ).pack()

        canvas = tk.Canvas(
            wheel_frame,
            width=350,
            height=350,
            bg="white"
        )
        canvas.pack(pady=10)

        canvas.create_text(
            175,
            175,
            text="Wheel\n(coming soon)",
            font=("Segoe UI", 11),
            justify="center"
        )

        tk.Button(
            wheel_frame,
            text="Spin",
            command=spin
        ).pack(pady=5)

        result_label = tk.Label(
            wheel_frame,
            text="Selected Map: -",
            font=("Segoe UI", 10, "bold")
        )
        result_label.pack()

        return canvas, result_label


    # --- MAP POOL ---

    def create_map_pool(bottom_frame):
        pool_frame = tk.Frame(bottom_frame)
        pool_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            pool_frame,
            text="Map Pool",
            font=("Segoe UI", 10)
        ).pack()

        map_list = ttk.Treeview(
            pool_frame,
            columns=("name",),
            show="headings",
            height=6,
            selectmode="extended"
        )

        map_list.heading("name", text="Map")

        scroll = ttk.Scrollbar(pool_frame, orient="vertical", command=map_list.yview)
        map_list.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        map_list.pack(fill="both", expand=True)

        return map_list


    # --- MAP CONTROLS ---

    def create_map_controls(bottom_frame):
        control_frame = tk.Frame(bottom_frame)
        control_frame.pack(side="left", padx=20)

        tk.Label(
            control_frame,
            text="Add Map",
            font=("Segoe UI", 10)
        ).pack(pady=(0, 5))

        entry = tk.Entry(control_frame, width=20)
        entry.pack(pady=5)

        tk.Button(
            control_frame,
            text="Add",
            width=12,
            command=add_map
        ).pack(pady=5)

        tk.Button(
            control_frame,
            text="Remove",
            width=12,
            command=remove_map
        ).pack(pady=5)

        return entry


    # --- BOTTOM AREA ---

    def create_bottom_area():
        bottom_frame = tk.Frame(parent)
        bottom_frame.pack(fill="both", expand=True, padx=20, pady=10)

        map_list = create_map_pool(bottom_frame)
        entry = create_map_controls(bottom_frame)

        return map_list, entry


    # --- BUILD UI ---

    canvas, result_label = create_wheel_area()
    map_list, entry = create_bottom_area()

    refresh_maps()