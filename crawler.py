import re
import sys
import time
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from dotenv import load_dotenv
import logger

# ENV & CONFIG
def resource_path(relative_path):
    """Get absolute path to resource for dev and PyInstaller"""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

env_path = resource_path(".env")
load_dotenv(env_path)

# CONSTANTS
DEFAULT_RATING = 10000  # fallback rating for players without data
LEETIFY_API = os.getenv("LEETIFY_API")

if not LEETIFY_API:
    raise RuntimeError("Missing LEETIFY_API in .env file")

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

    url = f"https://steamcommunity.com/id/{identifier}?xml=1"

    r = requests.get(url, timeout=5)

    if r.status_code != 200:
        raise Exception("Failed to resolve Steam vanity URL")

    root = ET.fromstring(r.text)

    steamid64 = root.findtext("steamID64")

    if not steamid64:
        raise ValueError("Could not resolve Steam vanity URL")

    return steamid64

# LEETIFY API

def get_leetify_player(steam_id):

    url = "https://api-public.cs-prod.leetify.com/v3/profile"

    params = {"steam64_id": steam_id}
    headers = {"Authorization": f"Bearer {LEETIFY_API}"}

    r = requests.get(url, params=params, headers=headers, timeout=5)

    # Player not available in API
    if r.status_code == 404: 
        logger.log_event("API_FALLBACK", {"steam_id": steam_id})
        return _get_leetify_profile_fallback(steam_id)

    if r.status_code != 200:
        raise Exception(f"Leetify API error ({r.status_code})")

    data = r.json()

    premier = data.get("ranks", {}).get("premier")
    leetify = data.get("ranks", {}).get("leetify")

    # If player has no premier rating yet
    if premier is None:
        logger.log_event("NO_PREMIER_FALLBACK", {"steam_id": steam_id})
        return _get_leetify_profile_fallback(steam_id)

    return {
        "steam64_id": steam_id,
        "leetify_id": data.get("id"),
        "name": data.get("name", steam_id),
        "premier_rating": premier,
        "leetify_rating": leetify,
        "total_matches": data.get("total_matches"),
        "winrate": data.get("winrate")
    }

# Fallback method using web scraping for players not having a profile
def _create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    return webdriver.Chrome(options=options)

def _fetch_leetify_profile_html(steam_id):

    url = f"https://leetify.com/app/profile/{steam_id}#rank-summary"

    driver = _create_driver()

    try:
        driver.get(url)

        # wait until rank summary section loads
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "rank-summary"))
            )
        except:
            pass

        html = driver.page_source

    finally:
        driver.quit()

    return html

def _get_steam_name(steam_id):

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

    html = _fetch_leetify_profile_html(steam_id)

    try:
        player = _parse_leetify_profile(html, steam_id)
    except Exception:
        player = None

    #  case - alex
    if not player:
        logger.log_warning(f"Fallback failed, using default rating for {steam_id}")
        # try to get player name from steam profile as a last resort
        name = _get_steam_name(steam_id)
        print(f"Using name '{name}' for steam ID {steam_id}")
        if not name:
            name = steam_id

        return {
            "steam64_id": steam_id,
            "leetify_id": None,
            "name": name,
            "premier_rating": DEFAULT_RATING, 
            "leetify_rating": None,
            "total_matches": None,
            "winrate": None
        }
    # return last seasons max rank
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
        "One": 1,
        "Two": 2,
        "Three": 3,
        "Four": 4,
        "Five": 5,
        "Six": 6,
        "Seven": 7,
        "Eight": 8,
        "Nine": 9,
        "Ten": 10
    }

    # Player name
    name = steam_id
    title = soup.find("title")

    if title:
        name = title.text.split(" - ")[0].strip()

    # find seasons
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

    # Find most recent season with a Premier rank and extract rating
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


    # if nothing found, return
    raise Exception("Premier rank not found in profile")

# Fetching stuff
def fetch_player(url):
    steam_id = get_player_identifier(url)
    return get_leetify_player(steam_id)

def fetch_players_bulk(steam_ids, delay=1, on_progress=None, on_player=None):
    results = []
    logger.log_event("BULK_FETCH_START", {"count": len(steam_ids)})
    for i, steam_id in enumerate(steam_ids, start=1):
        try:
            player = get_leetify_player(steam_id)
            results.append(player)

            if on_player:
                on_player(player)  # 🔑 immediate update

        except Exception as e:
            logger.log_error(f"Failed for {steam_id}: {e}")
            results.append(None)

        if on_progress:
            on_progress(i, len(steam_ids))

        time.sleep(delay)

    logger.log_event("BULK_FETCH_DONE", {"count": len(results)})
    return results