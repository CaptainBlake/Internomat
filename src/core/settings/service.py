import json


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value or "").strip().lower()
    return text in ("1", "true", "yes", "on")


SETTINGS_SCHEMA = {
    "update_cooldown_minutes": int,
    "log_level": str,
    "dist_weight": float,
    "default_rating": int,
    "allow_uneven_teams": _to_bool,
    "maproulette_use_history": _to_bool,
    "matchzy_host": str,
    "matchzy_port": int,
    "matchzy_user": str,
    "matchzy_password": str,
    "matchzy_database": str,
    "auto_import_match_players": _to_bool,
    "demo_ftp_host": str,
    "demo_ftp_port": int,
    "demo_ftp_user": str,
    "demo_ftp_password": str,
    "demo_remote_path": str,
}


def normalize_settings_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid settings payload format")

    normalized = {}
    for key, caster in SETTINGS_SCHEMA.items():
        if key not in payload:
            continue

        value = payload[key]
        try:
            normalized[key] = caster(value)
        except Exception as exc:
            raise ValueError(f"Invalid value for '{key}': {value}") from exc

    return normalized


def import_settings_payload(path):
    if str(path).lower().endswith(".cfg"):
        payload = _read_cfg(path)
    else:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

    return normalize_settings_payload(payload)


def export_settings_payload(path, payload):
    normalized = normalize_settings_payload(payload)

    if str(path).lower().endswith(".cfg"):
        _write_cfg(path, normalized)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)


def settings_to_payload(settings_obj):
    return {key: getattr(settings_obj, key) for key in SETTINGS_SCHEMA.keys()}


def apply_payload_to_settings(settings_obj, payload):
    normalized = normalize_settings_payload(payload)
    for key, value in normalized.items():
        setattr(settings_obj, key, value)

    return normalized


def _read_cfg(path):
    payload = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith(";"):
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            payload[key] = value.strip()

    return payload


def _write_cfg(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Internomat settings export\n")
        f.write("# Format: key=value\n\n")
        for key in sorted(payload.keys()):
            value = payload[key]
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            else:
                rendered = "" if value is None else str(value)
            f.write(f"{key}={rendered}\n")