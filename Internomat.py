import tkinter as tk
from tkinter import messagebox
import random
import json
import os

# Config
FILE_NAME = "players.json"
DEFAULT_ITERATIONS = 1000

# Helper
def parse_players_from_text(text):
    players = []
    seen = set()

    for line in text.strip().splitlines():
        parts = line.split(",")
        if len(parts) != 2:
            raise ValueError(f"Ungültiges Format: {line}")

        name = parts[0].strip()
        rating_str = parts[1].strip()

        # Prüfen, ob es ein Bereich ist: z.B. "8000-10000"
        if "-" in rating_str:
            try:
                low, high = map(int, rating_str.split("-"))
            except ValueError:
                raise ValueError(f"Ungültiger Rating-Bereich: {line}")
            if not (0 < low <= high <= 30000):
                raise ValueError(f"Rating-Bereich außerhalb des gültigen Bereichs: {line}")
            rating = (low, high)  # als Tuple speichern, wird später gewürfelt
        else:
            rating = int(rating_str)
            if not (0 < rating <= 30000):
                raise ValueError(f"Rating außerhalb des gültigen Bereichs: {name}")

        if name.lower() in seen:
            raise ValueError(f"Doppelter Spielername: {name}")

        seen.add(name.lower())
        players.append((name, rating))

    return players

def get_player_rating(rating):
    """Gibt das Rating als Zahl zurück, würfelt bei Bereich"""
    if isinstance(rating, tuple):
        low, high = rating
        return random.randint(low, high)
    return rating

def save_players(players):
    with open(FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(
            [{"name": name, "rating": rating} for name, rating in players],
            f,
            indent=2,
            ensure_ascii=False
        )

def load_players():
    if not os.path.exists(FILE_NAME):
        return []

    with open(FILE_NAME, "r", encoding="utf-8") as f:
        data = json.load(f)
        return [(p["name"], p["rating"]) for p in data]


def load_into_textbox():
    input_text.delete("1.0", tk.END)
    for name, rating in load_players():
        input_text.insert(tk.END, f"{name},{rating}\n")


# Core logic
def balance_teams(players, iterations, max_diff=None, strict=True):
    best_result = None
    best_diff = float("inf")

    for _ in range(iterations):
        shuffled = players[:]
        random.shuffle(shuffled)

        if strict:
            half = len(players) // 2
            team_a = shuffled[:half]
            team_b = shuffled[half:]
        else:
            split = random.randint(1, len(players) - 1)
            team_a = shuffled[:split]
            team_b = shuffled[split:]

        sum_a = sum(get_player_rating(r) for _, r in team_a)
        sum_b = sum(get_player_rating(r) for _, r in team_b)

        diff = abs(sum_a - sum_b)

        if diff < best_diff:
            best_diff = diff
            best_result = (team_a.copy(), team_b.copy())

            if max_diff is not None and diff <= max_diff:
                break

    return best_result, best_diff

def run_balancer():
    try:
        players = parse_players_from_text(
            input_text.get("1.0", tk.END)
        )

        if len(players) < 2:
            messagebox.showerror("Fehler", "Zu wenige Spieler.")
            return

        strict = strict_var.get()

        if strict and len(players) % 2 != 0:
            messagebox.showerror(
                "Fehler",
                "Bei gleicher Teamgröße muss die Spieleranzahl gerade sein."
            )
            return

        try:
            max_diff = int(max_diff_entry.get())
        except ValueError:
            raise ValueError("Max. Differenz muss eine Zahl sein.")

        if not (0 < max_diff <= 30000):
            raise ValueError("Max. Differenz muss zwischen 1 und 30000 liegen.")

        try:
            iterations = int(iter_entry.get())
        except ValueError:
            raise ValueError("Iterationen müssen eine Zahl sein.")

        if not (0 <= iterations <= 10000):
            raise ValueError("Iterationen müssen zwischen 0 und 10000 liegen.")

        teams, diff = balance_teams(
            players,
            iterations=iterations,
            max_diff=max_diff,
            strict=strict
        )

        team_a, team_b = teams

        output.delete("1.0", tk.END)

        output.insert(tk.END, "TEAM A\n")
        for name, rating in team_a:
            real_rating = get_player_rating(rating)
            output.insert(tk.END, f"{name} ({real_rating})\n")
        output.insert(tk.END, f"\nSumme: {sum(get_player_rating(r) for _, r in team_a)}\n\n")

        output.insert(tk.END, "TEAM B\n")
        for name, rating in team_b:
            real_rating = get_player_rating(rating)
            output.insert(tk.END, f"{name} ({real_rating})\n")
        output.insert(tk.END, f"\nSumme: {sum(get_player_rating(r) for _, r in team_b)}\n")
        output.insert(tk.END, f"\nDifferenz: {diff}")


    except Exception as e:
        messagebox.showerror("Fehler", str(e))

# I/O
def save_from_textbox():
    try:
        players = parse_players_from_text(
            input_text.get("1.0", tk.END)
        )
        save_players(players)
        messagebox.showinfo("Gespeichert", "Spieler erfolgreich gespeichert.")
    except Exception as e:
        messagebox.showerror("Fehler", str(e))


# GUI
root = tk.Tk()
root.title("Internomat")
root.geometry("350x700")
root.minsize(350, 700)
# Set Icon

# Grid
root.columnconfigure(0, weight=0)
root.columnconfigure(1, weight=0)
root.columnconfigure(2, weight=0)
root.columnconfigure(3, weight=1)

root.rowconfigure(1, weight=1)
root.rowconfigure(6, weight=1)

tk.Label(root, text="Spieler (Name,Rating):").grid(
    row=0, column=0, columnspan=4, sticky="w", padx=10
)

input_text = tk.Text(root, height=15)
input_text.grid(
    row=1,
    column=0,
    columnspan=4,
    sticky="nsew",
    padx=10,
    pady=5
)


# Max Diff 
tk.Label(root, text="Max. Differenz:").grid(
    row=2, column=0, sticky="e", padx=5
)

max_diff_entry = tk.Entry(root, width=8)
max_diff_entry.insert(0, "500")
max_diff_entry.grid(row=2, column=1, sticky="w", padx=5)

tk.Label(root, text="Iterationen:").grid(
    row=2, column=2, sticky="e", padx=5
)

iter_entry = tk.Entry(root, width=6)
iter_entry.insert(0, str(DEFAULT_ITERATIONS))
iter_entry.grid(row=2, column=3, sticky="w", padx=5)

# Checkbox – eigene Zeile

strict_var = tk.BooleanVar(value=True)
tk.Checkbutton(
    root,
    text="Gleiche Teamgröße",
    variable=strict_var
).grid(
    row=3, column=0, columnspan=4, sticky="w", pady=5, padx=10
)
# Info-Label rechts neben der Checkbox
tk.Label(
    root,
    text="1 = random, 1000 = balanced",
    fg="gray"
).grid(
    row=3, column=2, columnspan=3, sticky="w", padx=10
)

# Buttons
tk.Button(root, text="Teams losen", command=run_balancer)\
    .grid(row=4, column=0, padx=10, pady=5)

tk.Button(root, text="Spieler speichern", command=save_from_textbox)\
    .grid(row=4, column=3, padx=10, pady=5)

# Output
output = tk.Text(root, height=20)
output.grid(
    row=6,
    column=0,
    columnspan=4,
    sticky="nsew",
    padx=10,
    pady=5
)

load_into_textbox()
root.mainloop()
