"""Player profile fetching from Steam and Leetify.

Resolves player names from Steam and premier ratings from Leetify.
Names always come from Steam (authoritative). Ratings come from Leetify
with a multi-tier fallback chain.

Rating resolution flow (per player):
  1. _get_steam_name()             -> resolve display name via Steam XML API
  2. get_leetify_player()          -> attempt Leetify REST API (10s timeout)
     |  circuit breaker skips API after 3 consecutive failures
     |  on success: return rating + per-match history (source="api")
     |  on failure / 404 / no premier rank:
     v
  3. _get_leetify_profile_fallback()
     3a. _fetch_leetify_profile_html()  -> single Selenium page load (#rank-summary)
     3b. _parse_leetify_profile_current(soup)  -> current rating from profile header
         uses .label-large/.label-small outside #rank-summary, then regex on visible text
     3c. _parse_leetify_profile(soup)   -> max season rating from rank-summary table
         iterates seasons newest-first, picks rightmost (max) Premier cell
     3d. _build_result() with settings.default_rating (source="default")

Public API:
  fetch_player(url)                      -> single player from Steam URL
  fetch_players_bulk(steam_ids, ...)     -> bulk fetch with progress callback
  reset_api_circuit_breaker()            -> reset failure counter between cycles
  get_driver() / close_driver()          -> Selenium lifecycle (reused in bulk)
"""

import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from threading import Lock

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import services.logger as logger
from core.pathing import data_path
from core.security.secret_store import (
    load_bootstrap_leetify_api,
    load_leetify_api,
    save_leetify_api,
)
from core.settings.settings import settings

# Globals
FETCH_DELAY = 0.5
_driver = None
_driver_lock = Lock()
_cached_leetify_api = None
_api_consecutive_failures = 0
_API_FAILURE_THRESHOLD = 3

_SEASON_WORD_MAP = {
    "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5,
    "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10,
    "Eleven": 11, "Twelve": 12, "Thirteen": 13, "Fourteen": 14, "Fifteen": 15,
    "Sixteen": 16, "Seventeen": 17, "Eighteen": 18, "Nineteen": 19, "Twenty": 20,
}


def _load_env_file():
    candidates = [data_path(".env"), Path.cwd() / ".env"]
    for env_path in candidates:
        env_path = Path(env_path).resolve()
        if env_path.is_file():
            load_dotenv(env_path)
            logger.log(f"[ENV] Loaded .env from {env_path}", level="DEBUG")
            return str(env_path)
    logger.log("[ENV_WARNING] No .env file found in expected locations", level="INFO")
    return None


_load_env_file()


# -- API key resolution --

def _resolve_leetify_api_key():
    global _cached_leetify_api
    if _cached_leetify_api:
        return _cached_leetify_api

    env_api = os.getenv("LEETIFY_API", "").strip()
    if env_api:
        _cached_leetify_api = env_api
        try:
            save_leetify_api(env_api)
            logger.log("[SECRET] LEETIFY_API stored in Windows encrypted local store", level="DEBUG")
        except Exception as exc:
            logger.log(f"[SECRET_WARNING] Could not persist encrypted LEETIFY_API locally: {exc}", level="DEBUG")
        return _cached_leetify_api

    stored_api = load_leetify_api()
    if stored_api:
        _cached_leetify_api = stored_api
        return _cached_leetify_api

    bootstrap_api = load_bootstrap_leetify_api()
    if bootstrap_api:
        _cached_leetify_api = bootstrap_api
        try:
            save_leetify_api(bootstrap_api)
            logger.log("[SECRET] Migrated bundled bootstrap key into Windows encrypted local store", level="INFO")
        except Exception as exc:
            logger.log(f"[SECRET_WARNING] Could not persist bootstrap LEETIFY_API locally: {exc}", level="DEBUG")
        return _cached_leetify_api

    raise RuntimeError(
        "Missing LEETIFY_API. Set LEETIFY_API once or configure encrypted local secret via installer."
    )


# -- Steam helpers --

def _normalize_steam64_id(value):
    steam_id = str(value or "").strip()
    if not steam_id:
        raise ValueError("Missing Steam ID")
    if not steam_id.isdigit():
        raise ValueError(f"Steam ID is not numeric: {steam_id}")
    return steam_id


def get_player_identifier(url):
    identifier = _extract_steam_identifier(url)
    if identifier.isdigit():
        return identifier
    return _resolve_vanity(identifier)


def _extract_steam_identifier(url):
    url = url.strip()
    if url.isdigit():
        return url
    match = re.search(r"steamcommunity\.com/(?:id|profiles)/([^/?]+)", url)
    if not match:
        raise ValueError("Invalid Steam profile URL")
    return match.group(1)


def _resolve_vanity(identifier):
    redacted = logger.redact(identifier)
    logger.log(f"[FETCH] Resolve vanity {redacted}", level="DEBUG")

    r = requests.get(f"https://steamcommunity.com/id/{identifier}?xml=1", timeout=5)
    if r.status_code != 200:
        logger.log(f"[FETCH_ERROR] Vanity resolve failed {redacted}", level="INFO")
        raise Exception("Failed to resolve Steam vanity URL")

    root = ET.fromstring(r.text)
    steamid64 = root.findtext("steamID64")
    if not steamid64:
        raise ValueError("Could not resolve Steam vanity URL")
    return steamid64


def _get_steam_name(steam_id):
    redacted = logger.redact(steam_id)
    logger.log(f"[FETCH] Steam name lookup {redacted}", level="DEBUG")
    try:
        r = requests.get(f"https://steamcommunity.com/profiles/{steam_id}?xml=1", timeout=5)
        if r.status_code != 200:
            return steam_id
        root = ET.fromstring(r.text)
        name = root.findtext("steamID")
        return name if name else steam_id
    except Exception:
        return steam_id


# -- Result builder --

def _build_result(steam_id, name, premier_rating, *, rating_source, leetify_id=None,
                  leetify_rating=None, total_matches=None, winrate=None,
                  rating_season=None, rating_history=None):
    result = {
        "steam64_id": steam_id,
        "leetify_id": leetify_id,
        "name": name or steam_id,
        "premier_rating": premier_rating,
        "leetify_rating": leetify_rating,
        "total_matches": total_matches,
        "winrate": winrate,
        "rating_source": rating_source,
        "rating_season": rating_season,
    }
    if rating_history is not None:
        result["rating_history"] = rating_history
    return result


# -- Leetify API --

def reset_api_circuit_breaker():
    global _api_consecutive_failures
    _api_consecutive_failures = 0


def get_leetify_player(steam_id, auto_close=False):
    """Fetch player rating. auto_close=True cleans up the Selenium driver after the call."""
    global _api_consecutive_failures

    steam_id = _normalize_steam64_id(steam_id)
    redacted = logger.redact(steam_id)
    name = _get_steam_name(steam_id)

    # Circuit breaker: skip API after repeated failures
    if _api_consecutive_failures >= _API_FAILURE_THRESHOLD:
        logger.log(f"[FETCH] API circuit-breaker active, direct fallback {redacted}", level="DEBUG")
        try:
            return _get_leetify_profile_fallback(steam_id, name)
        finally:
            if auto_close:
                close_driver()

    api_key = _resolve_leetify_api_key()
    logger.log(f"[FETCH] Leetify API start {redacted}", level="DEBUG")

    try:
        r = requests.get(
            "https://api-public.cs-prod.leetify.com/v3/profile",
            params={"steam64_id": steam_id},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )

        if r.status_code == 404:
            logger.log(f"[FETCH_FALLBACK] API 404 -> fallback {redacted}", level="INFO")
            _api_consecutive_failures += 1
            return _get_leetify_profile_fallback(steam_id, name)

        if r.status_code != 200:
            logger.log(f"[FETCH_ERROR] API error {r.status_code} for {redacted}", level="INFO")
            _api_consecutive_failures += 1
            raise Exception(f"Leetify API error ({r.status_code})")

        data = r.json()
        premier = data.get("ranks", {}).get("premier")

        if premier is None:
            logger.log(f"[FETCH_FALLBACK] No premier -> fallback {redacted}", level="INFO")
            return _get_leetify_profile_fallback(steam_id, name)

        _api_consecutive_failures = 0
        logger.log(f"[FETCH_SUCCESS] API success {redacted}", level="DEBUG")

        # Per-match premier ratings from recent_matches
        history = []
        for rm in data.get("recent_matches") or []:
            rank = rm.get("rank")
            if rank and int(rank) > 0:
                history.append({
                    "leetify_match_id": rm.get("id"),
                    "premier_rating": int(rank),
                    "map_name": rm.get("map_name"),
                    "outcome": rm.get("outcome"),
                    "game_played_at": rm.get("finished_at"),
                })

        return _build_result(
            steam_id, name, premier,
            rating_source="api",
            leetify_id=data.get("id"),
            leetify_rating=data.get("ranks", {}).get("leetify"),
            total_matches=data.get("total_matches"),
            winrate=data.get("winrate"),
            rating_history=history,
        )
    except Exception as e:
        logger.log(f"[FETCH_ERROR] API fetch failed {redacted}: {e}", level="INFO")
        _api_consecutive_failures += 1
        return _get_leetify_profile_fallback(steam_id, name)
    finally:
        if auto_close:
            close_driver()


# -- Selenium driver management --

def _create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    logger.log("[CRAWLER] Selenium driver created", level="DEBUG")
    return webdriver.Chrome(options=options)


def get_driver():
    global _driver
    if _driver is None:
        _driver = _create_driver()
    return _driver


def close_driver():
    global _driver
    if _driver:
        logger.log("[CRAWLER] Closing Selenium driver", level="DEBUG")
        _driver.quit()
        _driver = None


# -- Selenium fallback --

def _fetch_leetify_profile_html(steam_id):
    """Load the Leetify profile page via Selenium (contains header rating + rank-summary)."""
    redacted = logger.redact(steam_id)
    with _driver_lock:
        driver = get_driver()
        logger.log(f"[FETCH] Selenium load profile {redacted}", level="DEBUG")
        driver.get(f"https://leetify.com/app/profile/{steam_id}#rank-summary")
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.ID, "rank-summary"))
            )
        except Exception:
            logger.log(f"[FETCH_WARNING] Profile page timeout {redacted}", level="DEBUG")
        return driver.page_source


def _get_leetify_profile_fallback(steam_id, name=None):
    """Scrape Leetify profile for premier rating (current -> season max -> default)."""
    redacted = logger.redact(steam_id)
    logger.log(f"[FETCH_FALLBACK] Start fallback {redacted}", level="INFO")
    if not name:
        name = steam_id

    # Single page load with one retry
    html = None
    for attempt in range(1, 3):
        try:
            html = _fetch_leetify_profile_html(steam_id)
        except Exception as e:
            logger.log(f"[FETCH_WARNING] Selenium load failed {redacted} attempt={attempt}: {e}", level="DEBUG")
            html = None
        if html:
            break
        if attempt < 2:
            time.sleep(1.0)

    if not html:
        logger.log(f"[FETCH_FALLBACK] Default rating used (no HTML) {redacted}", level="INFO")
        return _build_result(steam_id, name, settings.default_rating, rating_source="default")

    soup = BeautifulSoup(html, "html.parser")

    # Step 1: current rating from profile header
    try:
        rating = _parse_leetify_profile_current(soup)
    except Exception as e:
        logger.log(f"[FETCH_WARNING] Profile current-rating parse failed {redacted}: {e}", level="DEBUG")
        rating = None

    if rating is not None:
        logger.log(f"[FETCH_SUCCESS] Profile current-rating {redacted}", level="DEBUG")
        return _build_result(steam_id, name, rating, rating_source="fallback")

    # Step 2: max season rating from rank-summary
    try:
        season_result = _parse_leetify_profile(soup)
    except Exception as e:
        logger.log(f"[FETCH_WARNING] Season parse failed {redacted}: {e}", level="DEBUG")
        season_result = None

    if season_result is not None:
        logger.log(f"[FETCH_SUCCESS] Season fallback {redacted} season={season_result['season']}", level="DEBUG")
        return _build_result(
            steam_id, name, season_result["premier_rating"],
            rating_source="fallback", rating_season=season_result["season"],
        )

    # Step 3: default rating from settings
    logger.log(f"[FETCH_FALLBACK] Default rating used {redacted}", level="INFO")
    return _build_result(steam_id, name, settings.default_rating, rating_source="default")


# -- HTML parsers --

def _parse_leetify_profile_current(soup):
    """Extract CURRENT premier rating from the profile header section.

    Looks for .label-large/.label-small pairs outside #rank-summary.
    Falls back to regex on visible text above rank-summary.
    Returns int or None.
    """
    rank_summary = soup.find(id="rank-summary")

    # Identify labels inside rank-summary so we can skip them
    season_label_ids = set()
    if rank_summary:
        season_label_ids = {id(el) for el in rank_summary.select(".label-large")}

    for large in soup.select(".label-large"):
        if id(large) in season_label_ids:
            continue
        small = large.find_next_sibling(class_="label-small")
        if not small:
            parent = large.parent
            if parent:
                small = parent.select_one(".label-small")
        if not small:
            continue
        number = (large.text + small.text).replace(",", "").strip()
        if number.isdigit() and int(number) >= 1000:
            return int(number)

    # Regex fallback on visible text (avoids matching CSS color values)
    if rank_summary:
        text_parts = []
        for sibling in rank_summary.previous_siblings:
            t = sibling.get_text(separator=" ", strip=True) if hasattr(sibling, "get_text") else str(sibling).strip()
            if t:
                text_parts.append(t)
        text_before = " ".join(reversed(text_parts))
    else:
        text_before = soup.get_text(separator=" ", strip=True)

    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:,\d{3}))(?!\d)", text_before):
        raw = m.group(1).replace(",", "")
        if raw.isdigit() and int(raw) >= 1000:
            return int(raw)

    return None


def _parse_leetify_profile(soup):
    """Extract MAX premier rating from the rank-summary season tables.

    Iterates seasons newest-first. Picks the rightmost (max) Premier cell.
    Returns {"premier_rating": int, "season": int} or None.
    Raises if seasons exist but no Premier row is found.
    """
    seasons = []
    for section in soup.select("section.season"):
        header = section.find("h4")
        if not header:
            continue
        match = re.search(r"Season\s+([A-Za-z]+)", header.text)
        if not match or match.group(1) not in _SEASON_WORD_MAP:
            continue
        seasons.append((_SEASON_WORD_MAP[match.group(1)], section))

    if not seasons:
        return None

    seasons.sort(reverse=True, key=lambda x: x[0])

    for season_number, section in seasons:
        for row in section.select("table.rank-groups tbody tr"):
            th = row.find("th")
            if not th or "Premier" not in th.text:
                continue
            cells = row.find_all("td")
            if not cells:
                continue
            # Reversed: pick max (rightmost) cell first
            for cell in reversed(cells):
                large = cell.select_one(".label-large")
                small = cell.select_one(".label-small")
                if not large or not small:
                    continue
                number = (large.text + small.text).replace(",", "").strip()
                if number.isdigit():
                    return {"premier_rating": int(number), "season": season_number}
                break

    raise Exception("Premier rank not found in profile")


# -- Public API --

def fetch_player(url):
    logger.log("[USER] Fetch player from URL", level="INFO")
    steam_id = get_player_identifier(url)
    return get_leetify_player(steam_id, auto_close=True)


def fetch_players_bulk(steam_ids, delay=FETCH_DELAY, on_progress=None, on_player=None):
    total = len(steam_ids)
    logger.log(f"[FETCH] Bulk start count={total}", level="INFO")
    results = []

    for i, steam_id in enumerate(steam_ids, start=1):
        redacted = logger.redact(steam_id)
        try:
            player = get_leetify_player(steam_id, auto_close=False)
            results.append(player)
            if on_player:
                on_player(player)
        except Exception as e:
            logger.log(f"[FETCH_ERROR] Bulk failed {redacted}: {e}", level="INFO")
            results.append(None)
        if on_progress:
            on_progress(i, total)
        if delay > 0:
            time.sleep(delay)

    close_driver()
    logger.log(f"[FETCH] Bulk done success={sum(p is not None for p in results)} total={total}", level="INFO")
    return results