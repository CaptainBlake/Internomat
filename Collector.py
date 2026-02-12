# login_and_fetch.py

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta


async def load_last_12_months(page):

    target_date = datetime.now() - timedelta(days=365)

    print("Target cutoff:", target_date.date())

    while True:
        # Get the oldest visible match date
        # get ALL dates and find the oldest one
        
        date_elements = await page.query_selector_all("text=/\\d{4}-\\d{2}-\\d{2}/")
        dates = []
        for date_element in date_elements:
            date_text = await date_element.inner_text()
            date_only = date_text.strip().split(" ")[0]
            dates.append(datetime.strptime(date_only, "%Y-%m-%d"))
        oldest_date = min(dates)

        print("Oldest currently loaded:", oldest_date.date())

        if oldest_date <= target_date:
            print("✅ Loaded enough history")
            break

        # Click "Weiteren Verlauf laden"
        button = await page.query_selector("text=WEITEREN VERLAUF LADEN")
        if not button:
            print("⚠ No more history available")
            break

        await button.click()

        # Wait for new content to load
        await page.wait_for_timeout(1500)  # small delay for ajax load


async def get_authenticated_session():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://steamcommunity.com/login")

        print("👉 Scan QR code with Steam mobile app...")

        # Wait until steamLoginSecure cookie appears
        while True:
            cookies = await context.cookies()
            if any(c["name"] == "steamLoginSecure" for c in cookies):
                break
            await asyncio.sleep(1)

        print("✅ Login detected")

        # Go to /my to resolve real profile URL
        await page.goto("https://steamcommunity.com/my")
        await page.wait_for_load_state("networkidle")

        profile_url = page.url
        print("Resolved profile URL:", profile_url)

        # Remove trailing slash if present
        profile_url = profile_url.rstrip("/")

        # Now build the match history URL dynamically
        gcpd_url = f"{profile_url}/gcpd/730/?tab=matchhistoryscrimmage"
        print("Opening:", gcpd_url)

        await page.goto(gcpd_url)
        await page.wait_for_load_state("networkidle")

        await load_last_12_months(page)

        html = await page.content()
        await browser.close()

        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.generic_kv_table.csgo_scoreboard_root")

        print("Table found:", table is not None)

        with open("scoreboard_table.html", "w", encoding="utf-8") as f:
            f.write(str(table))


async def main():
    session = await get_authenticated_session()

asyncio.run(main())
