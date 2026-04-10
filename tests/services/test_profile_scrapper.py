"""Tests for services.profile_scrapper — Steam/Leetify player fetching with mocked HTTP."""

import os
from unittest.mock import patch, Mock, MagicMock

import pytest
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Canned XML/JSON responses
# ---------------------------------------------------------------------------

STEAM_XML_PROFILE = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<profile>
    <steamID64>76561198000000099</steamID64>
    <steamID>TestPlayer</steamID>
</profile>
"""

STEAM_XML_VANITY = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<profile>
    <steamID64>76561198000000099</steamID64>
</profile>
"""

LEETIFY_API_SUCCESS = {
    "id": "leet-id-123",
    "name": "TestPlayer",
    "ranks": {
        "premier": 18500,
        "leetify": 1.15,
    },
    "total_matches": 250,
    "winrate": 0.54,
}

LEETIFY_API_NO_PREMIER = {
    "id": "leet-id-456",
    "name": "NoPremier",
    "ranks": {
        "premier": None,
        "leetify": 0.90,
    },
    "total_matches": 50,
    "winrate": 0.48,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_env_leetify_api(monkeypatch):
    """Ensure LEETIFY_API env var is set for all tests."""
    monkeypatch.setenv("LEETIFY_API", "fake-api-key-12345")
    import services.profile_scrapper as ps
    ps.reset_api_circuit_breaker()
    ps._cached_leetify_api = None


@pytest.fixture
def mock_get(mock_http_response):
    """Patch ``requests.get`` globally in the profile_scrapper module."""
    with patch("services.profile_scrapper.requests.get") as m:
        yield m


@pytest.fixture
def mock_driver():
    """Patch Selenium driver creation to prevent real browser launch."""
    driver = MagicMock()
    driver.page_source = "<html></html>"
    with patch("services.profile_scrapper.get_driver", return_value=driver):
        with patch("services.profile_scrapper.close_driver"):
            yield driver


# ---------------------------------------------------------------------------
# Tests: _normalize_steam64_id
# ---------------------------------------------------------------------------

class TestNormalizeSteam64Id:

    def test_valid_id(self):
        from services.profile_scrapper import _normalize_steam64_id
        assert _normalize_steam64_id("76561198000000001") == "76561198000000001"

    def test_strips_whitespace(self):
        from services.profile_scrapper import _normalize_steam64_id
        assert _normalize_steam64_id("  76561198000000001  ") == "76561198000000001"

    def test_empty_raises(self):
        from services.profile_scrapper import _normalize_steam64_id
        with pytest.raises(ValueError, match="Missing Steam ID"):
            _normalize_steam64_id("")

    def test_none_raises(self):
        from services.profile_scrapper import _normalize_steam64_id
        with pytest.raises(ValueError, match="Missing Steam ID"):
            _normalize_steam64_id(None)

    def test_non_numeric_raises(self):
        from services.profile_scrapper import _normalize_steam64_id
        with pytest.raises(ValueError, match="not numeric"):
            _normalize_steam64_id("abc123")


# ---------------------------------------------------------------------------
# Tests: _extract_steam_identifier / get_player_identifier
# ---------------------------------------------------------------------------

class TestExtractSteamIdentifier:

    def test_raw_steamid64(self):
        from services.profile_scrapper import _extract_steam_identifier
        assert _extract_steam_identifier("76561198000000001") == "76561198000000001"

    def test_profiles_url(self):
        from services.profile_scrapper import _extract_steam_identifier
        result = _extract_steam_identifier(
            "https://steamcommunity.com/profiles/76561198000000001"
        )
        assert result == "76561198000000001"

    def test_id_url_returns_vanity(self):
        from services.profile_scrapper import _extract_steam_identifier
        result = _extract_steam_identifier(
            "https://steamcommunity.com/id/myvanity"
        )
        assert result == "myvanity"

    def test_invalid_url_raises(self):
        from services.profile_scrapper import _extract_steam_identifier
        with pytest.raises(ValueError, match="Invalid Steam profile URL"):
            _extract_steam_identifier("https://example.com/notsteam")

    def test_strips_whitespace(self):
        from services.profile_scrapper import _extract_steam_identifier
        result = _extract_steam_identifier("  76561198000000001  ")
        assert result == "76561198000000001"


# ---------------------------------------------------------------------------
# Tests: _resolve_vanity
# ---------------------------------------------------------------------------

class TestResolveVanity:

    def test_resolves_vanity_name(self, mock_get):
        from services.profile_scrapper import _resolve_vanity

        resp = Mock(status_code=200, text=STEAM_XML_VANITY)
        mock_get.return_value = resp

        result = _resolve_vanity("myvanity")
        assert result == "76561198000000099"

    def test_failed_http_raises(self, mock_get):
        from services.profile_scrapper import _resolve_vanity

        resp = Mock(status_code=500, text="")
        mock_get.return_value = resp

        with pytest.raises(Exception, match="Failed to resolve"):
            _resolve_vanity("badvanity")

    def test_missing_steamid64_raises(self, mock_get):
        from services.profile_scrapper import _resolve_vanity

        xml_no_id = '<?xml version="1.0"?><profile></profile>'
        resp = Mock(status_code=200, text=xml_no_id)
        mock_get.return_value = resp

        with pytest.raises(ValueError, match="Could not resolve"):
            _resolve_vanity("nouser")


# ---------------------------------------------------------------------------
# Tests: get_player_identifier
# ---------------------------------------------------------------------------

class TestGetPlayerIdentifier:

    def test_numeric_id_returned_directly(self, mock_get):
        from services.profile_scrapper import get_player_identifier
        result = get_player_identifier("76561198000000001")
        mock_get.assert_not_called()
        assert result == "76561198000000001"

    def test_vanity_url_resolved(self, mock_get):
        from services.profile_scrapper import get_player_identifier

        resp = Mock(status_code=200, text=STEAM_XML_VANITY)
        mock_get.return_value = resp

        result = get_player_identifier(
            "https://steamcommunity.com/id/myvanity"
        )
        assert result == "76561198000000099"


# ---------------------------------------------------------------------------
# Tests: get_leetify_player (API path)
# ---------------------------------------------------------------------------

class TestGetLeetifyPlayer:

    def test_api_success(self, mock_get):
        from services.profile_scrapper import get_leetify_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        api_resp = Mock(status_code=200)
        api_resp.json.return_value = LEETIFY_API_SUCCESS
        # First call: _get_steam_name, second call: Leetify API
        mock_get.side_effect = [steam_name_resp, api_resp]

        result = get_leetify_player("76561198000000001")

        assert result["steam64_id"] == "76561198000000001"
        assert result["premier_rating"] == 18500
        assert result["leetify_rating"] == 1.15
        assert result["name"] == "TestPlayer"  # From Steam XML
        assert result["total_matches"] == 250

    def test_api_404_triggers_fallback(self, mock_get, mock_driver):
        from services.profile_scrapper import get_leetify_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        resp_404 = Mock(status_code=404)
        # First: _get_steam_name, second: Leetify API 404
        mock_get.side_effect = [steam_name_resp, resp_404]

        result = get_leetify_player("76561198000000099")

        # Fallback with empty HTML won't find premier, so returns default
        assert result is not None
        assert result["steam64_id"] == "76561198000000099"

    def test_api_non_200_triggers_fallback(self, mock_get, mock_driver):
        from services.profile_scrapper import get_leetify_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        resp_500 = Mock(status_code=500)
        mock_get.side_effect = [steam_name_resp, resp_500]

        result = get_leetify_player("76561198000000099")
        assert result is not None
        assert result["steam64_id"] == "76561198000000099"

    def test_api_no_premier_triggers_fallback(self, mock_get, mock_driver):
        from services.profile_scrapper import get_leetify_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        resp = Mock(status_code=200)
        resp.json.return_value = LEETIFY_API_NO_PREMIER
        mock_get.side_effect = [steam_name_resp, resp]

        result = get_leetify_player("76561198000000099")
        assert result is not None
        # Falls back → default rating path
        assert result["steam64_id"] == "76561198000000099"

    def test_auto_close_calls_close_driver(self, mock_get):
        from services.profile_scrapper import get_leetify_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        api_resp = Mock(status_code=200)
        api_resp.json.return_value = LEETIFY_API_SUCCESS
        mock_get.side_effect = [steam_name_resp, api_resp]

        with patch("services.profile_scrapper.close_driver") as mock_close:
            get_leetify_player("76561198000000001", auto_close=True)
            mock_close.assert_called_once()

    def test_invalid_steam_id_raises(self, mock_get):
        from services.profile_scrapper import get_leetify_player

        with pytest.raises(ValueError, match="not numeric"):
            get_leetify_player("not-a-number")


# ---------------------------------------------------------------------------
# Tests: _get_steam_name
# ---------------------------------------------------------------------------

class TestGetSteamName:

    def test_returns_name_on_success(self, mock_get):
        from services.profile_scrapper import _get_steam_name

        resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        mock_get.return_value = resp

        result = _get_steam_name("76561198000000099")
        assert result == "TestPlayer"

    def test_returns_steamid_on_http_error(self, mock_get):
        from services.profile_scrapper import _get_steam_name

        resp = Mock(status_code=500, text="")
        mock_get.return_value = resp

        result = _get_steam_name("76561198000000099")
        assert result == "76561198000000099"

    def test_returns_steamid_on_exception(self, mock_get):
        from services.profile_scrapper import _get_steam_name

        mock_get.side_effect = Exception("Network error")

        result = _get_steam_name("76561198000000099")
        assert result == "76561198000000099"


# ---------------------------------------------------------------------------
# Tests: fetch_player (end-to-end with mock)
# ---------------------------------------------------------------------------

class TestFetchPlayer:

    def test_fetch_player_from_url(self, mock_get):
        from services.profile_scrapper import fetch_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        api_resp = Mock(status_code=200)
        api_resp.json.return_value = LEETIFY_API_SUCCESS
        mock_get.side_effect = [steam_name_resp, api_resp]

        with patch("services.profile_scrapper.close_driver"):
            result = fetch_player("76561198000000001")

        assert result["premier_rating"] == 18500
        assert result["steam64_id"] == "76561198000000001"

    def test_fetch_player_from_profiles_url(self, mock_get):
        from services.profile_scrapper import fetch_player

        steam_name_resp = Mock(status_code=200, text=STEAM_XML_PROFILE)
        api_resp = Mock(status_code=200)
        api_resp.json.return_value = LEETIFY_API_SUCCESS
        mock_get.side_effect = [steam_name_resp, api_resp]

        with patch("services.profile_scrapper.close_driver"):
            result = fetch_player(
                "https://steamcommunity.com/profiles/76561198000000001"
            )

        assert result["steam64_id"] == "76561198000000001"

    def test_fetch_player_invalid_url(self, mock_get):
        from services.profile_scrapper import fetch_player

        with pytest.raises(ValueError, match="Invalid Steam profile URL"):
            fetch_player("https://example.com/nope")


# ---------------------------------------------------------------------------
# Tests: _parse_leetify_profile (HTML parsing)
# ---------------------------------------------------------------------------

class TestParseLeetifyProfile:

    def test_parses_premier_rating(self):
        from services.profile_scrapper import _parse_leetify_profile

        html = """
        <html>
        <head><title>TestPlayer - Leetify</title></head>
        <body>
        <section class="season">
            <h4>Season One</h4>
            <table class="rank-groups">
                <tbody>
                    <tr>
                        <th>Premier</th>
                        <td>Some</td>
                        <td><span class="label-large">15</span><span class="label-small">234</span></td>
                    </tr>
                </tbody>
            </table>
        </section>
        </body></html>
        """

        result = _parse_leetify_profile(BeautifulSoup(html, "html.parser"))
        assert result is not None
        assert result["premier_rating"] == 15234
        assert result["season"] == 1

    def test_picks_latest_season(self):
        from services.profile_scrapper import _parse_leetify_profile

        html = """
        <html><head><title>Player - Leetify</title></head><body>
        <section class="season">
            <h4>Season One</h4>
            <table class="rank-groups"><tbody>
                <tr><th>Premier</th><td>x</td>
                <td><span class="label-large">10</span><span class="label-small">000</span></td></tr>
            </tbody></table>
        </section>
        <section class="season">
            <h4>Season Two</h4>
            <table class="rank-groups"><tbody>
                <tr><th>Premier</th><td>x</td>
                <td><span class="label-large">12</span><span class="label-small">500</span></td></tr>
            </tbody></table>
        </section>
        </body></html>
        """

        result = _parse_leetify_profile(BeautifulSoup(html, "html.parser"))
        assert result["premier_rating"] == 12500
        assert result["season"] == 2

    def test_no_seasons_returns_none(self):
        from services.profile_scrapper import _parse_leetify_profile

        html = "<html><body><p>No data</p></body></html>"
        result = _parse_leetify_profile(BeautifulSoup(html, "html.parser"))
        assert result is None

    def test_no_premier_row_raises(self):
        from services.profile_scrapper import _parse_leetify_profile

        html = """
        <html><head><title>Player - Leetify</title></head><body>
        <section class="season">
            <h4>Season One</h4>
            <table class="rank-groups"><tbody>
                <tr><th>Wingman</th><td>x</td>
                <td><span class="label-large">5</span><span class="label-small">000</span></td></tr>
            </tbody></table>
        </section>
        </body></html>
        """

        with pytest.raises(Exception, match="Premier rank not found"):
            _parse_leetify_profile(BeautifulSoup(html, "html.parser"))

    def test_prefers_max_over_min(self):
        """When both min and max cells have labels, the MAX (rightmost) is used."""
        from services.profile_scrapper import _parse_leetify_profile

        html = """
        <html><head><title>Player - Leetify</title></head><body>
        <section class="season">
            <h4>Season Four</h4>
            <table class="rank-groups"><tbody>
                <tr>
                    <th>Premier</th>
                    <td><span class="label-large">18</span><span class="label-small">000</span></td>
                    <td><span class="label-large">22</span><span class="label-small">500</span></td>
                </tr>
            </tbody></table>
        </section>
        </body></html>
        """

        result = _parse_leetify_profile(BeautifulSoup(html, "html.parser"))
        assert result["premier_rating"] == 22500
        assert result["season"] == 4


# ---------------------------------------------------------------------------
# Tests: _parse_leetify_profile_current (profile top-section rating)
# ---------------------------------------------------------------------------

class TestParseLeetifyProfileCurrent:

    def test_parses_label_large_small_outside_rank_summary(self):
        from services.profile_scrapper import _parse_leetify_profile_current

        html = """
        <html><head><title>Sunflower - Leetify</title></head><body>
        <div class="profile-header">
            <span class="label-large">24</span><span class="label-small">,777</span>
        </div>
        <div id="rank-summary">
            <span class="label-large">18</span><span class="label-small">,000</span>
        </div>
        </body></html>
        """

        result = _parse_leetify_profile_current(BeautifulSoup(html, "html.parser"))
        assert result == 24777

    def test_ignores_labels_inside_rank_summary(self):
        from services.profile_scrapper import _parse_leetify_profile_current

        html = """
        <html><head><title>Player - Leetify</title></head><body>
        <div id="rank-summary">
            <span class="label-large">18</span><span class="label-small">,500</span>
        </div>
        </body></html>
        """

        result = _parse_leetify_profile_current(BeautifulSoup(html, "html.parser"))
        assert result is None

    def test_returns_none_when_no_rating(self):
        from services.profile_scrapper import _parse_leetify_profile_current

        html = "<html><head><title>Player - Leetify</title></head><body></body></html>"
        result = _parse_leetify_profile_current(BeautifulSoup(html, "html.parser"))
        assert result is None

    def test_ignores_small_label_numbers(self):
        from services.profile_scrapper import _parse_leetify_profile_current

        html = """
        <html><head><title>Player - Leetify</title></head><body>
        <span class="label-large">0</span><span class="label-small">42</span>
        </body></html>
        """

        result = _parse_leetify_profile_current(BeautifulSoup(html, "html.parser"))
        assert result is None

    def test_broad_fallback_finds_comma_number(self):
        from services.profile_scrapper import _parse_leetify_profile_current

        html = """
        <html><head><title>Sunflower - Leetify</title></head><body>
        <p>Some text 24,777 more text</p>
        <div id="rank-summary">season data here</div>
        </body></html>
        """

        result = _parse_leetify_profile_current(BeautifulSoup(html, "html.parser"))
        assert result == 24777

    def test_ignores_css_rgb_color_values(self):
        """Regression: rgb(255, 255, 255) in CSS must NOT be parsed as 255,255."""
        from services.profile_scrapper import _parse_leetify_profile_current

        html = """
        <html><head><title>Player - Leetify</title></head><body>
        <style>.foo { color: rgb(255, 255, 255); }</style>
        <div style="background: rgba(255, 255, 0, 1);">No rating here</div>
        <div id="rank-summary">season data</div>
        </body></html>
        """

        result = _parse_leetify_profile_current(html)
        assert result is None
