"""Live smoke test: Leetify public API.

Reads the LEETIFY_API bearer token from environment (.env or external).
Skipped unless INTERNOMAT_LIVE_TESTS=1.
"""

import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.live

# A well-known public Steam64 ID for testing (s1mple)
KNOWN_STEAM64_ID = "76561198034202275"

LEETIFY_API_URL = "https://api-public.cs-prod.leetify.com/v3/profile"


@pytest.fixture
def leetify_api_key():
    key = os.getenv("LEETIFY_API")
    if not key:
        pytest.skip("LEETIFY_API key not configured in environment")
    return key


def test_leetify_api_returns_200(require_live, leetify_api_key):
    """Fetch a known player profile from the Leetify API and verify HTTP 200."""
    r = requests.get(
        LEETIFY_API_URL,
        params={"steam64_id": KNOWN_STEAM64_ID},
        headers={"Authorization": f"Bearer {leetify_api_key}"},
        timeout=15,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"


def test_leetify_api_response_shape(require_live, leetify_api_key):
    """Verify the API response contains expected top-level keys."""
    r = requests.get(
        LEETIFY_API_URL,
        params={"steam64_id": KNOWN_STEAM64_ID},
        headers={"Authorization": f"Bearer {leetify_api_key}"},
        timeout=15,
    )
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, dict)
    # The profile response must have at least these keys
    assert "ranks" in data, f"Missing 'ranks' in response keys: {list(data.keys())}"
    assert "name" in data, f"Missing 'name' in response keys: {list(data.keys())}"
