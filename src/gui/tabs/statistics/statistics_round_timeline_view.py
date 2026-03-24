from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout


WIN_COLOR_TOP = "#63C2FF"
WIN_COLOR_BOTTOM = "#F4C04E"
MUTED_COLOR = "#8DA0B4"

def _is_match(name_a, name_b):
    return str(name_a or "").strip().lower() == str(name_b or "").strip().lower()


def _build_round_cell(top_win, bottom_win, tooltip):
    cell = QFrame()
    cell.setToolTip(tooltip)

    layout = QVBoxLayout(cell)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(1)

    top = QFrame()
    top.setFixedHeight(8)
    top_color = WIN_COLOR_TOP if top_win else MUTED_COLOR
    top.setStyleSheet(f"background: {top_color}; border: none;")

    bottom = QFrame()
    bottom.setFixedHeight(8)
    bottom_color = WIN_COLOR_BOTTOM if bottom_win else MUTED_COLOR
    bottom.setStyleSheet(f"background: {bottom_color}; border: none;")

    layout.addWidget(top)
    layout.addWidget(bottom)
    return cell


def render_round_timeline(layout, timeline, top_team_name, bottom_team_name):
    if not isinstance(timeline, dict):
        return

    rounds = timeline.get("rounds") or []
    if not rounds:
        return

    team1_name = str(timeline.get("team1_name") or "").strip()
    team2_name = str(timeline.get("team2_name") or "").strip()

    wrapper = QFrame()
    wrapper.setStyleSheet("QFrame { background: transparent; border: none; }")

    body = QVBoxLayout(wrapper)
    body.setContentsMargins(0, 2, 0, 2)
    body.setSpacing(4)

    title = QLabel("Round Timeline (demo)")
    title.setStyleSheet("font-size: 11px; font-weight: 700; color: #5A6B7C;")
    body.addWidget(title)

    grid_frame = QFrame()
    grid = QGridLayout(grid_frame)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(2)
    grid.setVerticalSpacing(0)

    col = 0
    for idx, entry in enumerate(rounds):
        winner_name = entry.get("winner_team_name")
        top_win = _is_match(winner_name, top_team_name)
        bottom_win = _is_match(winner_name, bottom_team_name)

        team1_side = entry.get("team1_side") or "?"
        team2_side = entry.get("team2_side") or "?"

        if _is_match(top_team_name, team1_name):
            top_side = team1_side
        elif _is_match(top_team_name, team2_name):
            top_side = team2_side
        else:
            top_side = "?"

        if _is_match(bottom_team_name, team1_name):
            bottom_side = team1_side
        elif _is_match(bottom_team_name, team2_name):
            bottom_side = team2_side
        else:
            bottom_side = "?"

        tooltip = (
            f"Round {entry.get('round_no', '?')}\n"
            f"Winner: {winner_name or '?'}\n"
            f"{top_team_name}: {top_side} | {bottom_team_name}: {bottom_side}"
        )

        cell = _build_round_cell(
            top_win=top_win,
            bottom_win=bottom_win,
            tooltip=tooltip,
        )
        cell.setFixedWidth(24)

        grid.addWidget(cell, 0, col)
        col += 1

        if entry.get("switch_after") and idx < len(rounds) - 1:
            switch_line = QFrame()
            switch_line.setFixedWidth(4)
            switch_line.setStyleSheet("background: #B9C8D8; border: none;")
            grid.addWidget(switch_line, 0, col)
            col += 1

    body.addWidget(grid_frame)

    layout.addWidget(wrapper)
