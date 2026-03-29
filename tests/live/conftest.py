import pytest
import os

LIVE_ENABLED = os.environ.get("INTERNOMAT_LIVE_TESTS", "0") == "1"


def pytest_collection_modifyitems(config, items):
    if not LIVE_ENABLED:
        skip = pytest.mark.skip(reason="Live tests disabled (set INTERNOMAT_LIVE_TESTS=1)")
        for item in items:
            if "live" in str(item.fspath):
                item.add_marker(skip)


@pytest.fixture
def require_live():
    if not LIVE_ENABLED:
        pytest.skip("Live tests disabled")
