from db import statistics_db as statistics_repo
from services import demo_cache
import services.logger as logger
import threading


_PARSED_PAYLOAD_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX_SIZE = 200


def _safe_row_count(value):
    if value is None:
        return 0

    if hasattr(value, "__len__"):
        try:
            return int(len(value))
        except Exception:
            return 0

    return 0


def _build_cache_manifest_map(cache_rows):
    by_key = {}
    for row in cache_rows:
        match_id = str(row.get("match_id"))
        map_number = int(row.get("map_number") or 0)
        by_key[(match_id, map_number)] = row
    return by_key


def _manifest_fingerprint(manifest):
    if not isinstance(manifest, dict):
        return None, None
    return manifest.get("filename"), manifest.get("updated_at")


def _prune_payload_cache(valid_keys):
    with _CACHE_LOCK:
        stale = [k for k in _PARSED_PAYLOAD_CACHE.keys() if k not in valid_keys]
        for key in stale:
            _PARSED_PAYLOAD_CACHE.pop(key, None)


def _get_cached_payload(match_id, map_number, manifest):
    key = (str(match_id), int(map_number))
    fingerprint = _manifest_fingerprint(manifest)

    with _CACHE_LOCK:
        cached = _PARSED_PAYLOAD_CACHE.get(key)
        if cached and cached.get("fingerprint") == fingerprint:
            return cached.get("payload"), True

    payload = demo_cache.load_parsed_demo_default(match_id, map_number)

    with _CACHE_LOCK:
        if len(_PARSED_PAYLOAD_CACHE) >= _CACHE_MAX_SIZE:
            _PARSED_PAYLOAD_CACHE.pop(next(iter(_PARSED_PAYLOAD_CACHE)), None)
        _PARSED_PAYLOAD_CACHE[key] = {
            "fingerprint": fingerprint,
            "payload": payload,
        }
    return payload, False


def _extract_demo_metrics(parsed_payload):
    if not isinstance(parsed_payload, dict):
        return {
            "demo_rounds": None,
            "demo_kills": None,
            "demo_damages": None,
        }

    return {
        "demo_rounds": _safe_row_count(parsed_payload.get("rounds")),
        "demo_kills": _safe_row_count(parsed_payload.get("kills")),
        "demo_damages": _safe_row_count(parsed_payload.get("damages")),
    }


def get_overview():
    row = statistics_repo.fetch_overview()

    result = {
        "total_matches": int(row["total_matches"] or 0),
        "total_maps": int(row["total_maps"] or 0),
        "unique_players": int(row["unique_players"] or 0),
        "demo_matches": int(row["demo_matches"] or 0),
        "maps_with_stats": int(row["maps_with_stats"] or 0),
        "total_rounds_played": int(row["total_rounds_played"] or 0),
        "top_map_name": str(row["top_map_name"] or ""),
        "top_map_count": int(row["top_map_count"] or 0),
    }

    logger.log(
        "[STATISTICS] "
        f"overview matches={result['total_matches']} "
        f"maps={result['total_maps']} players={result['unique_players']} "
        f"demo_matches={result['demo_matches']} maps_with_stats={result['maps_with_stats']} "
        f"rounds={result['total_rounds_played']} "
        f"top_map={result['top_map_name']}({result['top_map_count']})",
        level="DEBUG",
    )

    return result


def get_recent_maps(limit=10):
    rows = statistics_repo.fetch_recent_maps(limit)
    cache_rows = demo_cache.list_existing_cached_demos_default()
    cache_by_key = _build_cache_manifest_map(cache_rows)
    _prune_payload_cache(set(cache_by_key.keys()))

    cache_loaded = 0
    cache_reused = 0

    result = []
    for r in rows:
        match_id = str(r["match_id"])
        map_number = int(r["map_number"] or 0)
        key = (match_id, map_number)
        manifest = cache_by_key.get(key)

        demo_cached = manifest is not None
        demo_metrics = {
            "demo_rounds": None,
            "demo_kills": None,
            "demo_damages": None,
        }

        if demo_cached:
            parsed_payload, reused = _get_cached_payload(match_id, map_number, manifest)
            if reused:
                cache_reused += 1
            else:
                cache_loaded += 1
            demo_metrics = _extract_demo_metrics(parsed_payload)

        result.append(
            {
                "match_id": match_id,
                "map_number": map_number,
                "map_name": str(r["map_name"] or "?"),
                "winner": str(r["winner"] or "?"),
                "team1_score": int(r["team1_score"] or 0),
                "team2_score": int(r["team2_score"] or 0),
                "played_at": str(r["played_at"] or ""),
                "db_has_data": True,
                "db_demo_flag": int(r["has_demo"] or 0) == 1,
                "cached_demo": demo_cached,
                "demo_rounds": (
                    demo_metrics["demo_rounds"]
                    if demo_metrics["demo_rounds"] is not None
                    else (int(r["db_rounds"]) if r["db_rounds"] is not None else None)
                ),
                "demo_kills": (
                    demo_metrics["demo_kills"]
                    if demo_metrics["demo_kills"] is not None
                    else (int(r["db_kills"]) if r["db_kills"] is not None else None)
                ),
                "demo_damages": demo_metrics["demo_damages"],
            }
        )

    logger.log(f"[STATISTICS] recent maps size={len(result)}", level="DEBUG")
    logger.log(
        f"[STATISTICS] cache payloads loaded={cache_loaded} reused={cache_reused}",
        level="DEBUG",
    )

    return result
