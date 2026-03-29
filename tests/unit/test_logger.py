"""Tests for services.logger — log(), subscribe(), redact(), filtering."""

import services.logger as logger


def setup_function():
    """Reset logger state before each test."""
    logger.clear_log_history()
    logger._subscribers.clear()
    # Ensure logging is enabled with DEBUG level for most tests.
    logger.LOG_ENABLED = True
    logger.LOG_LEVEL = "DEBUG"


def teardown_function():
    """Restore defaults after each test."""
    logger.LOG_ENABLED = True
    logger.LOG_LEVEL = "DEBUG"
    logger._subscribers.clear()


# -- log() appends to history --

def test_log_appends_to_history():
    logger.log("hello world")
    history = logger.get_log_history()
    assert len(history) == 1
    assert "hello world" in history[0]


def test_log_multiple_entries():
    logger.log("msg1")
    logger.log("msg2")
    logger.log("msg3")
    assert len(logger.get_log_history()) == 3


# -- subscribe / unsubscribe --

def test_subscribe_callback_fires():
    received = []
    logger.subscribe(lambda entry: received.append(entry))
    logger.log("test message")
    assert len(received) == 1
    assert "test message" in received[0]


def test_unsubscribe_stops_callback():
    received = []
    cb = lambda entry: received.append(entry)
    logger.subscribe(cb)
    logger.log("msg1")
    logger.unsubscribe(cb)
    logger.log("msg2")
    assert len(received) == 1


def test_multiple_subscribers():
    r1, r2 = [], []
    logger.subscribe(lambda e: r1.append(e))
    logger.subscribe(lambda e: r2.append(e))
    logger.log("broadcast")
    assert len(r1) == 1
    assert len(r2) == 1


# -- redact() --

def test_redact_masks_after_keep():
    assert logger.redact("mysecretpassword", keep=4) == "myse****"


def test_redact_short_string():
    assert logger.redact("ab", keep=4) == "ab****"


def test_redact_none():
    assert logger.redact(None) is None


def test_redact_empty_string():
    assert logger.redact("") == ""


def test_redact_default_keep():
    result = logger.redact("abcdefgh")
    assert result == "abcd****"


# -- log level filtering --

def test_log_level_info_filters_debug():
    logger.LOG_LEVEL = "INFO"
    logger.log("debug msg", level="DEBUG")
    assert len(logger.get_log_history()) == 0


def test_log_level_info_passes_info():
    logger.LOG_LEVEL = "INFO"
    logger.log("info msg", level="INFO")
    assert len(logger.get_log_history()) == 1


def test_log_level_info_passes_error():
    logger.LOG_LEVEL = "INFO"
    logger.log("error msg", level="ERROR")
    assert len(logger.get_log_history()) == 1


def test_log_disabled():
    logger.LOG_ENABLED = False
    logger.log("should not appear")
    assert len(logger.get_log_history()) == 0


def test_log_level_off_blocks_everything():
    logger.LOG_LEVEL = "OFF"
    logger.log("msg", level="ERROR")
    assert len(logger.get_log_history()) == 0


# -- max history cap --

def test_max_history_cap():
    original_max = logger.MAX_HISTORY
    logger.MAX_HISTORY = 5
    try:
        for i in range(10):
            logger.log(f"msg {i}")
        assert len(logger.get_log_history()) == 5
    finally:
        logger.MAX_HISTORY = original_max


# -- clear_log_history --

def test_clear_log_history():
    logger.log("something")
    assert len(logger.get_log_history()) > 0
    logger.clear_log_history()
    assert len(logger.get_log_history()) == 0


# -- timestamp in DEBUG mode --

def test_debug_level_includes_timestamp():
    logger.LOG_LEVEL = "DEBUG"
    logger.log("ts test", level="INFO")
    entry = logger.get_log_history()[0]
    # DEBUG mode adds [HH:MM:SS.mmm] prefix
    assert entry.startswith("[")
