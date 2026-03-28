from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QTableWidget, QTableWidgetItem, QHeaderView

from gui.tabs.statistics import statistics_round_timeline_view


class SortableTableItem(QTableWidgetItem):
    def __init__(self, text, sort_value=None):
        super().__init__(str(text))
        self._sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, SortableTableItem):
            a = self._sort_value
            b = other._sort_value
            if a is not None and b is not None:
                try:
                    return a < b
                except Exception:
                    return str(a) < str(b)
        return super().__lt__(other)


def _build_team_scoreboard_table(rows):
    table = QTableWidget(0, 12)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setGridStyle(Qt.PenStyle.SolidLine)
    table.verticalHeader().setVisible(False)
    table.setStyleSheet(
        """
        QTableWidget {
            background: rgba(255, 255, 255, 0.92);
            alternate-background-color: rgba(241, 246, 252, 0.88);
            gridline-color: #D2DCE8;
            border: 1px solid #D6DEE9;
            border-radius: 6px;
        }
        QHeaderView::section {
            background: #EAF2FB;
            color: #22384D;
            border: 1px solid #D2DCE8;
            padding: 6px;
            font-weight: 700;
        }
        QTableWidget::item {
            padding: 6px;
            border: none;
        }
        """
    )

    headers = ["Player", "K", "D", "A", "K/D", "ADR", "HS%", "ACC%", "Entry", "Clutch", "UDMG", "DMG"]
    header_tooltips = {
        "Player": "Player name stored in match player stats.",
        "K": "Kills made by the player.",
        "D": "Deaths of the player.",
        "A": "Assists by the player.",
        "K/D": "Kill/death ratio (kills divided by deaths).",
        "ADR": "Average damage per round (damage / map rounds).",
        "HS%": "Headshot kill percentage of all kills.",
        "ACC%": "Shot accuracy (shots on target / shots fired).",
        "Entry": "Entry duel wins over entry attempts (wins/attempts).",
        "Clutch": "1vX clutch wins over clutch attempts (wins/attempts).",
        "UDMG": "Utility damage dealt (grenades and similar).",
        "DMG": "Total damage dealt.",
    }
    for i, text in enumerate(headers):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(header_tooltips.get(text, ""))
        table.setHorizontalHeaderItem(i, item)

    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)

    table.setSortingEnabled(False)

    for row in rows:
        idx = table.rowCount()
        table.insertRow(idx)

        values = [
            row["player_name"],
            row["kills"],
            row["deaths"],
            row["assists"],
            f"{row['kd_ratio']:.2f}",
            "n/a" if row["adr"] is None else f"{row['adr']:.1f}",
            f"{row['hs_pct']:.0f}%",
            f"{row['acc_pct']:.0f}%",
            f"{row['entry_wins']}/{row['entry_count']}",
            f"{row['clutch_wins']}/{row['clutch_count']}",
            row["utility_damage"],
            row["damage"],
        ]

        sort_values = [
            str(row["player_name"] or "").lower(),
            int(row["kills"] or 0),
            int(row["deaths"] or 0),
            int(row["assists"] or 0),
            float(row["kd_ratio"] or 0.0),
            -1.0 if row["adr"] is None else float(row["adr"]),
            float(row["hs_pct"] or 0.0),
            float(row["acc_pct"] or 0.0),
            float(row["entry_pct"] or 0.0),
            float(row["clutch_pct"] or 0.0),
            int(row["utility_damage"] or 0),
            int(row["damage"] or 0),
        ]

        for col, value in enumerate(values):
            item = SortableTableItem(value, sort_values[col])
            if col == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            else:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(idx, col, item)

    table.setSortingEnabled(True)
    table.sortItems(1, Qt.SortOrder.DescendingOrder)
    return table


def render_split_scoreboard(layout, summary, rows, timeline=None):
    team_groups = {}
    for row in rows:
        key = str(row.get("team") or "?")
        team_groups.setdefault(key, []).append(row)

    team1_name = str(summary.get("team1_name") or "").strip()
    team2_name = str(summary.get("team2_name") or "").strip()
    team1_score = int(summary.get("team1_score") or 0)
    team2_score = int(summary.get("team2_score") or 0)
    winner = str(summary.get("winner") or "").strip().lower()

    # Legacy restored rows can carry generic TeamA/TeamB labels while summary uses
    # concrete team names. Remap groups so score and timeline winner matching works.
    if team1_name and team2_name:
        generic_map = {}
        for label, members in team_groups.items():
            norm = str(label or "").strip().lower()
            if norm == "teama":
                generic_map["TeamA"] = members
            elif norm == "teamb":
                generic_map["TeamB"] = members

        if "TeamA" in generic_map or "TeamB" in generic_map:
            remapped = {}
            if "TeamA" in generic_map:
                remapped[team1_name] = generic_map["TeamA"]
            if "TeamB" in generic_map:
                remapped[team2_name] = generic_map["TeamB"]

            for label, members in team_groups.items():
                norm = str(label or "").strip().lower()
                if norm in {"teama", "teamb"}:
                    continue
                remapped[label] = members

            team_groups = remapped

    ordered_team_names = []
    if team1_name and team2_name:
        if team1_score >= team2_score:
            ordered_team_names.extend([team1_name, team2_name])
        else:
            ordered_team_names.extend([team2_name, team1_name])

    for known_name in list(ordered_team_names):
        if known_name not in team_groups:
            ordered_team_names.remove(known_name)

    for name in sorted(team_groups.keys()):
        if name not in ordered_team_names:
            ordered_team_names.append(name)

    for idx, team_name in enumerate(ordered_team_names):
        team_rows = team_groups.get(team_name, [])
        if not team_rows:
            continue

        team_score = "?"
        if team_name == team1_name:
            team_score = str(team1_score)
        elif team_name == team2_name:
            team_score = str(team2_score)

        team_header = f"{team_name} ({team_score})"
        if winner and winner == team_name.lower():
            team_header += "  WIN"

        title = QLabel(team_header)
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #22384D; padding-top: 2px; padding-bottom: 2px;")
        layout.addWidget(title)

        layout.addWidget(_build_team_scoreboard_table(team_rows), 1)

        # Render timeline between team A and team B when demo rounds are available.
        if idx == 0 and len(ordered_team_names) >= 2 and timeline:
            spacer = QFrame()
            spacer.setFixedHeight(8)
            spacer.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(spacer)

            statistics_round_timeline_view.render_round_timeline(
                layout=layout,
                timeline=timeline,
                top_team_name=ordered_team_names[0],
                bottom_team_name=ordered_team_names[1],
            )

            spacer = QFrame()
            spacer.setFixedHeight(8)
            spacer.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(spacer)

        if idx < len(ordered_team_names) - 1:
            spacer = QFrame()
            spacer.setFixedHeight(10)
            spacer.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(spacer)

            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            divider.setFrameShadow(QFrame.Shadow.Plain)
            divider.setStyleSheet("color: #BFCDDE; background: #BFCDDE; min-height: 1px; max-height: 1px;")
            layout.addWidget(divider)

            spacer = QFrame()
            spacer.setFixedHeight(10)
            spacer.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(spacer)
