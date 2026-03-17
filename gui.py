import tkinter as tk
from tkinter import ttk

from tabs.team_builder import build_team_tab
from tabs.map_roulette import build_map_tab


def start_gui():

    root = tk.Tk()
    root.title("Internomat")
    root.geometry("900x700")
    root.minsize(850, 650)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    team_tab = tk.Frame(notebook)
    map_tab = tk.Frame(notebook)

    notebook.add(team_tab, text="Team Builder")
    notebook.add(map_tab, text="Map Roulette")

    build_team_tab(root, team_tab)
    build_map_tab(map_tab)

    root.mainloop()