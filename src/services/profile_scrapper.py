import re
import time
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from dotenv import load_dotenv
import services.logger as logger
from core.settings.settings import settings
from threading import Lock
from core.pathing import data_path, resource_path


def load_env_file():
    candidates = [
        data_path(".env"),
        Path.cwd() / ".env",
        resource_path(".env"),
    ]

    for env_path in candidates:
        env_path = Path(env_path).resolve()
        if env_path.is_file():
            load_dotenv(env_path)
            logger.log(f"[ENV] Loaded .env from {env_path}", level="DEBUG")
            return str(env_path)

    logger.log("[ENV_WARNING] No .env file found in expected locations", level="INFO")
    return None


load_env_file()

# CONSTANTS & GLOBALS
FETCH_DELAY = 0.5  # seconds between bulk fetches to avoid rate limits
_driver = None
_driver_lock = Lock()


def _normalize_steam64_id(value):
    steam_id = str(value or "").strip()
    if not steam_id:
        raise ValueError("Missing Steam ID")
    if not steam_id.isdigit():
        raise ValueError(f"Steam ID is not numeric: {steam_id}")
    return steam_id


# STEAM PARSING

def get_player_identifier(url):
    identifier = _extract_steam_identifier(url)

    if identifier.isdigit():
        return identifier

    return _resolve_vanity(identifier)


def _extract_steam_identifier(url):
    url = url.strip()

    if url.isdigit():
        return url

    pattern = r"steamcommunity\.com/(?:id|profiles)/([^/?]+)"
    match = re.search(pattern, url)

    if not match:
        raise ValueError("Invalid Steam profile URL")

    return match.group(1)


def _resolve_vanity(identifier):
    redacted = logger.redact(identifier)
    logger.log(f"[FETCH] Resolve vanity {redacted}", level="DEBUG")

    url = f"https://steamcommunity.com/id/{identifier}?xml=1"
    r = requests.get(url, timeout=5)

    if r.status_code != 200:
        logger.log(f"[FETCH_ERROR] Vanity resolve failed {redacted}", level="INFO")
        raise Exception("Failed to resolve Steam vanity URL")

    root = ET.fromstring(r.text)
    steamid64 = root.findtext("steamID64")

    if not steamid64:
        raise ValueError("Could not resolve Steam vanity URL")

    return steamid64


# LEETIFY API

def get_leetify_player(steam_id, auto_close=False):
    """
    auto_close = False (default): keeps driver alive (used for bulk)
    auto_close = True: ensures driver cleanup after call
    """

    LEETIFY_API = os.getenv("LEETIFY_API")
    if not LEETIFY_API:
        raise RuntimeError("Missing LEETIFY_API in .env file")

    steam_id = _normalize_steam64_id(steam_id)
    redacted = logger.redact(steam_id)
    logger.log(f"[FETCH] Leetify API start {redacted}", level="DEBUG")

    try:
        url = "https://api-public.cs-prod.leetify.com/v3/profile"
        params = {"steam64_id": steam_id}
        headers = {"Authorization": f"Bearer {LEETIFY_API}"}

        r = requests.get(url, params=params, headers=headers, timeout=10)

        if r.status_code == 404:
            logger.log(f"[FETCH_FALLBACK] API 404 -> fallback {redacted}", level="INFO")
            return _get_leetify_profile_fallback(steam_id)

        if r.status_code != 200:
            logger.log(f"[FETCH_ERROR] API error {r.status_code} for {redacted}", level="INFO")
            raise Exception(f"Leetify API error ({r.status_code})")

        data = r.json()

        premier = data.get("ranks", {}).get("premier")
        leetify = data.get("ranks", {}).get("leetify")

        if premier is None:
            logger.log(f"[FETCH_FALLBACK] No premier -> fallback {redacted}", level="INFO")
            return _get_leetify_profile_fallback(steam_id)

        logger.log(f"[FETCH_SUCCESS] API success {redacted}", level="DEBUG")

        return {
            "steam64_id": steam_id,
            "leetify_id": data.get("id"),
            "name": data.get("name", steam_id),
            "premier_rating": premier,
            "leetify_rating": leetify,
            "total_matches": data.get("total_matches"),
            "winrate": data.get("winrate")
        }
    except Exception as e:
        logger.log(f"[FETCH_ERROR] API fetch failed {redacted}: {e}", level="INFO")
        return _get_leetify_profile_fallback(steam_id)
    finally:
        if auto_close:
            close_driver()


# FALLBACK (SELENIUM)

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


def _fetch_leetify_profile_html(steam_id):
    redacted = logger.redact(steam_id)

    with _driver_lock:
        driver = get_driver()

        logger.log(f"[FETCH] Selenium load {redacted}", level="DEBUG")

        url = f"https://leetify.com/app/profile/{steam_id}#rank-summary"
        driver.get(url)

        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.ID, "rank-summary"))
            )
        except:
            logger.log(f"[FETCH_WARNING] Timeout {redacted}", level="DEBUG")

        return driver.page_source


def _get_steam_name(steam_id):
    redacted = logger.redact(steam_id)
    logger.log(f"[FETCH] Steam name lookup {redacted}", level="DEBUG")

    url = f"https://steamcommunity.com/profiles/{steam_id}?xml=1"

    try:
        r = requests.get(url, timeout=5)

        if r.status_code != 200:
            return steam_id

        root = ET.fromstring(r.text)
        name = root.findtext("steamID")

        return name if name else steam_id

    except Exception:
        return steam_id


def _get_leetify_profile_fallback(steam_id):
    redacted = logger.redact(steam_id)
    logger.log(f"[FETCH_FALLBACK] Start fallback {redacted}", level="INFO")

    player = None
    for attempt in range(1, 3):
        html = _fetch_leetify_profile_html(steam_id)

        try:
            player = _parse_leetify_profile(html, steam_id)
        except Exception as e:
            logger.log(f"[FETCH_WARNING] Parse failed {redacted} attempt={attempt}: {e}", level="DEBUG")
            player = None

        if player:
            break

        if attempt < 2:
            time.sleep(1.0)

    if not player:
        logger.log(f"[FETCH_FALLBACK] Default rating used {redacted}", level="INFO")

        name = _get_steam_name(steam_id)

        return {
            "steam64_id": steam_id,
            "leetify_id": None,
            "name": name if name else steam_id,
            "premier_rating": settings.default_rating,
            "leetify_rating": None,
            "total_matches": None,
            "winrate": None
        }

    logger.log(f"[FETCH_SUCCESS] Fallback success {redacted}", level="DEBUG")

    return {
        "steam64_id": steam_id,
        "leetify_id": None,
        "name": player["name"],
        "premier_rating": player["premier_rating"],
        "leetify_rating": None,
        "total_matches": None,
        "winrate": None
    }


def _parse_leetify_profile(html, steam_id):
    soup = BeautifulSoup(html, "html.parser")

    season_map = {
        "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5,
        "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10
    }

    name = steam_id
    title = soup.find("title")

    if title:
        name = title.text.split(" - ")[0].strip()

    seasons = []

    for season in soup.select("section.season"):
        header = season.find("h4")
        if not header:
            continue

        match = re.search(r"Season\s+([A-Za-z]+)", header.text)
        if not match:
            continue

        word = match.group(1)
        if word not in season_map:
            continue

        seasons.append((season_map[word], season))

    if not seasons:
        return None

    seasons.sort(reverse=True, key=lambda x: x[0])

    for season_number, season in seasons:
        rows = season.select("table.rank-groups tbody tr")

        for row in rows:
            th = row.find("th")
            if not th or "Premier" not in th.text:
                continue

            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            max_rank_cell = cells[1]
            large = max_rank_cell.select_one(".label-large")
            small = max_rank_cell.select_one(".label-small")

            if not large or not small:
                continue

            number = (large.text + small.text).replace(",", "").strip()

            if number.isdigit():
                return {
                    "steam64_id": steam_id,
                    "name": name,
                    "premier_rating": int(number),
                    "season": season_number
                }

    raise Exception("Premier rank not found in profile")


# PUBLIC API

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
        finally:
            close_driver()

        if on_progress:
            on_progress(i, total)

        if delay > 0:
            time.sleep(delay)

    logger.log(f"[FETCH] Bulk done success={sum(p is not None for p in results)} total={total}", level="INFO")

    return results
