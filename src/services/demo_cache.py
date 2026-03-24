import pickle
from datetime import datetime
from pathlib import Path

import gzip

import pandas as pd
import polars as pl

from services.IO_manager import IOManager
import services.logger as logger


_INDEX_NAME = "index.json"


def _default_cache_dir():
    base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "demos" / "parsed"


def _to_path(path_value):
    return Path(path_value)


def load_parsed_demo_default(match_id, map_number):
    return load_parsed_demo(_default_cache_dir(), match_id, map_number)


def list_cached_demos_default():
    return list_cached_demos(_default_cache_dir())


def list_existing_cached_demos(cache_dir):
    rows = list_cached_demos(cache_dir)
    existing = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        match_id = row.get("match_id")
        map_number = row.get("map_number")
        if match_id is None or map_number is None:
            continue

        payload_path = _resolve_payload_path(
            cache_dir=cache_dir,
            match_id=match_id,
            map_number=map_number,
            filename=row.get("filename"),
        )

        if IOManager.file_exists(str(payload_path)):
            existing.append(row)

    return existing


def list_existing_cached_demos_default():
    return list_existing_cached_demos(_default_cache_dir())


def cached_match_ids_default():
    rows = list_existing_cached_demos_default()
    ids = set()
    for row in rows:
        match_id = row.get("match_id") if isinstance(row, dict) else None
        if match_id is None:
            continue
        ids.add(str(match_id))
    return ids


def reconcile_db_demo_flags_default():
    from db.matches_db import set_demo_flags_by_match_ids

    ids = cached_match_ids_default()
    set_demo_flags_by_match_ids(ids)
    logger.log_info(f"[CACHE] Reconciled DB demo flags from cache entries={len(ids)}")
    return len(ids)


def _iter_rows(table):
    if isinstance(table, pd.DataFrame):
        if table.empty:
            return []
        return table.to_dict("records")

    if isinstance(table, pl.DataFrame):
        if table.height == 0:
            return []
        return table.to_dicts()

    if isinstance(table, list):
        return [r for r in table if isinstance(r, dict)]

    return []


def load_round_rows(match_id, map_number):
    payload = load_parsed_demo_default(match_id, map_number)
    if not isinstance(payload, dict):
        return []

    rows = _iter_rows(payload.get("rounds"))
    if rows:
        return rows

    return _iter_rows(payload.get("rounds_stats"))


def _ensure_cache_dir(cache_dir):
    cache_dir = _to_path(cache_dir)
    IOManager.ensure_dir(str(cache_dir))
    return cache_dir


def _cache_key(match_id, map_number):
    return f"match_{int(match_id)}_map_{int(map_number)}"


def _cache_filename(match_id, map_number, source_file=None):
    if source_file is not None:
        source_stem = Path(source_file).stem
        if source_stem:
            return f"{source_stem}.pkl"

    return f"{_cache_key(match_id, map_number)}.pkl"


def _open_for_write(path):
    return open(path, "wb")


def _open_for_read(path):
    if str(path).endswith(".pkl"):
        return open(path, "rb")
    return gzip.open(path, "rb")


def _resolve_payload_path(cache_dir, match_id, map_number, filename=None):
    cache_dir = _ensure_cache_dir(cache_dir)

    if filename:
        path = cache_dir / filename
        if IOManager.file_exists(str(path)):
            return path

    preferred = cache_dir / _cache_filename(match_id, map_number)
    fallback_gzip = cache_dir / f"{_cache_key(match_id, map_number)}.pkl.gz"

    if IOManager.file_exists(str(preferred)):
        return preferred
    if IOManager.file_exists(str(fallback_gzip)):
        return fallback_gzip

    return preferred


def _index_path(cache_dir):
    return _ensure_cache_dir(cache_dir) / _INDEX_NAME


def load_index(cache_dir):
    index_file = _index_path(cache_dir)
    if not IOManager.file_exists(str(index_file)):
        return {}

    try:
        data = IOManager.read_json(str(index_file))
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.log_error(f"[CACHE] Failed reading index: {e}")

    return {}


def save_index(cache_dir, index_data):
    index_file = _index_path(cache_dir)
    IOManager.write_json(str(index_file), index_data)


def save_parsed_demo(cache_dir, match_id, map_number, data, source_file=None):
    cache_dir = _ensure_cache_dir(cache_dir)
    filename = _cache_filename(match_id, map_number, source_file=source_file)
    payload_path = cache_dir / filename

    with _open_for_write(payload_path) as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    key = _cache_key(match_id, map_number)
    index_data = load_index(cache_dir)

    index_data[key] = {
        "match_id": int(match_id),
        "map_number": int(map_number),
        "cache_key": key,
        "filename": filename,
        "compression": "none",
        "source_file": str(source_file) if source_file else None,
        "updated_at": datetime.utcnow().isoformat(),
        "header": data.get("header", {}) if isinstance(data, dict) else {},
    }

    save_index(cache_dir, index_data)
    logger.log_info(f"[CACHE] Saved parsed demo {key}")

    return index_data[key]


def load_parsed_demo(cache_dir, match_id, map_number):
    cache_dir = _ensure_cache_dir(cache_dir)
    manifest = get_cached_manifest(cache_dir, match_id, map_number)
    payload_path = _resolve_payload_path(
        cache_dir=cache_dir,
        match_id=match_id,
        map_number=map_number,
        filename=(manifest or {}).get("filename"),
    )

    if not IOManager.file_exists(str(payload_path)):
        return None

    with _open_for_read(payload_path) as f:
        data = pickle.load(f)

    logger.log_debug(f"[CACHE] Loaded parsed demo match={match_id} map={map_number}")
    return data


def get_cached_manifest(cache_dir, match_id, map_number):
    key = _cache_key(match_id, map_number)
    return load_index(cache_dir).get(key)


def list_cached_demos(cache_dir):
    rows = list(load_index(cache_dir).values())
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return rows


def payload_table_stats(data):
    stats = {}
    if not isinstance(data, dict):
        return stats

    for key, value in data.items():
        if isinstance(value, pd.DataFrame):
            stats[key] = {
                "type": "pandas",
                "rows": int(len(value)),
                "cols": int(len(value.columns)),
            }
        elif isinstance(value, pl.DataFrame):
            stats[key] = {
                "type": "polars",
                "rows": int(value.height),
                "cols": int(len(value.columns)),
            }
        elif isinstance(value, dict):
            stats[key] = {
                "type": "dict",
                "keys": int(len(value)),
            }
        elif isinstance(value, list):
            stats[key] = {
                "type": "list",
                "items": int(len(value)),
            }
        elif value is None:
            stats[key] = {
                "type": "none",
            }
        else:
            stats[key] = {
                "type": type(value).__name__,
            }

    return stats
