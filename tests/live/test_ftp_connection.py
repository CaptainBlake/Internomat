"""Live smoke test: FTP connectivity.

Reads FTP credentials from environment variables (SERVER_IP, FTP_PORT,
FTP_USER, FTP_PASSWORD) loaded via .env or set externally.
Skipped unless INTERNOMAT_LIVE_TESTS=1.
"""

import os
from ftplib import FTP

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.live


@pytest.fixture
def ftp_creds():
    host = os.getenv("SERVER_IP")
    port = int(os.getenv("FTP_PORT", 21))
    user = os.getenv("FTP_USER")
    password = os.getenv("FTP_PASSWORD")
    if not all([host, user, password]):
        pytest.skip("FTP credentials not configured in environment")
    return host, port, user, password


def test_ftp_connect_and_list(require_live, ftp_creds):
    """Connect to FTP, list remote directory, verify non-empty listing."""
    host, port, user, password = ftp_creds

    ftp = FTP()
    try:
        ftp.connect(host, port, timeout=10)
        ftp.login(user, password)

        remote_dir = os.getenv("DEMO_REMOTE_PATH", "/cs2/game/csgo/MatchZy")
        ftp.cwd(remote_dir)

        listing = ftp.nlst()
        assert isinstance(listing, list)
        assert len(listing) > 0, "Remote directory listing is empty"
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def test_ftp_clean_disconnect(require_live, ftp_creds):
    """Verify FTP connection can be established and closed cleanly."""
    host, port, user, password = ftp_creds

    ftp = FTP()
    ftp.connect(host, port, timeout=10)
    ftp.login(user, password)

    # QUIT should return a 2xx response
    response = ftp.quit()
    assert response.startswith("2"), f"Unexpected QUIT response: {response}"
