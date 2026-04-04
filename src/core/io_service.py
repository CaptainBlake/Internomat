"""Core-level facades for data import/export and cache management.

GUI should use these instead of importing db modules directly.
"""
from db import IO_db
from db import matches_db


def get_players_payload():
    return IO_db.get_players_payload()


def import_players_payload(players):
    return IO_db.import_players_payload(players)


def get_maps_payload():
    return IO_db.get_maps_payload()


def import_maps_payload(maps_data):
    return IO_db.import_maps_payload(maps_data)


def clear_demo_flags():
    matches_db.set_demo_flags_by_match_ids(set())
