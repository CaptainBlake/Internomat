import requests
import random
import re
import xml.etree.ElementTree as ET
import os
import asyncio

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

load_dotenv()

# CONSTANTS
ITERATIONS = 1000
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
        return _get_leetify_profile_fallback(steam_id)

    if r.status_code != 200:
        raise Exception(f"Leetify API error ({r.status_code})")

    data = r.json()

    premier = data.get("ranks", {}).get("premier")
    leetify = data.get("ranks", {}).get("leetify")

    # If player has no premier rating yet
    if premier is None:
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
async def _fetch_leetify_profile_html(steam_id):

    url = f"https://leetify.com/app/profile/{steam_id}#rank-summary"

    async with async_playwright() as p:

        browser = await p.chromium.launch(headless=True)

        page = await browser.new_page()

        await page.goto(url)

        # Wait until rank summary exists instead of sleeping
        try:
            await page.wait_for_selector("#rank-summary", timeout=10000)
        except:
            pass

        html = await page.content()

        await browser.close()

    return html


def _get_leetify_profile_fallback(steam_id):

    html = asyncio.run(_fetch_leetify_profile_html(steam_id))

    player = _parse_leetify_profile(html, steam_id)

    if not player:
        raise Exception("Failed to parse Leetify profile")

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


# TEAM BALANCER
# TODO: implement something smarter than thousand random shuffles and compare them...
def balance_teams(players):

    best = None
    best_diff = float("inf")

    for _ in range(ITERATIONS):

        shuffled = players[:]
        random.shuffle(shuffled)

        half = len(players) // 2

        team_a = shuffled[:half]
        team_b = shuffled[half:]

        sum_a = sum(p[2] for p in team_a)
        sum_b = sum(p[2] for p in team_b)

        diff = abs(sum_a - sum_b)

        if diff < best_diff:

            best_diff = diff
            best = (team_a.copy(), team_b.copy())

    return best, best_diff