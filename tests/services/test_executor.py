"""Tests for services.executor — thread pool submission and async helpers."""

import time
import threading
from unittest.mock import MagicMock, patch
from concurrent.futures import Future

import pytest


# ---------------------------------------------------------------------------
# The executor module uses module-level globals (_executor, _is_shutdown).
# We must reset them between tests so each test starts clean.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_executor():
    """Reset the executor module state before each test."""
    import services.executor as mod
    from concurrent.futures import ThreadPoolExecutor

    mod._is_shutdown = False
    mod._executor = ThreadPoolExecutor(max_workers=2)
    yield
    # Best-effort cleanup
    try:
        mod._executor.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# submit()
# ---------------------------------------------------------------------------

class TestSubmit:

    def test_submit_runs_callable(self):
        from services.executor import submit

        future = submit(lambda: 42)
        assert isinstance(future, Future)
        assert future.result(timeout=5) == 42

    def test_submit_passes_args(self):
        from services.executor import submit

        future = submit(lambda x, y: x + y, 3, 7)
        assert future.result(timeout=5) == 10

    def test_submit_passes_kwargs(self):
        from services.executor import submit

        future = submit(lambda a=0, b=0: a * b, a=4, b=5)
        assert future.result(timeout=5) == 20

    def test_submit_returns_none_after_shutdown(self):
        import services.executor as mod
        mod.shutdown()

        result = mod.submit(lambda: 1)
        assert result is None


# ---------------------------------------------------------------------------
# run_async()
# ---------------------------------------------------------------------------

class TestRunAsync:

    def test_run_async_executes_task(self):
        from services.executor import run_async

        flag = threading.Event()
        started = run_async(flag.set)
        assert started is True
        assert flag.wait(timeout=5)

    def test_run_async_with_lock_acquires_and_releases(self):
        from services.executor import run_async

        lock = threading.Lock()
        done = threading.Event()

        def task():
            done.set()

        started = run_async(task, lock=lock)
        assert started is True
        done.wait(timeout=5)
        # Give the wrapper time to release the lock
        time.sleep(0.1)
        assert lock.acquire(blocking=False), "Lock should be released after task completes"
        lock.release()

    def test_run_async_returns_false_if_lock_held(self):
        from services.executor import run_async

        lock = threading.Lock()
        lock.acquire()

        started = run_async(lambda: None, lock=lock)
        assert started is False

        lock.release()

    def test_run_async_on_error_fires_on_exception(self):
        from services.executor import run_async

        error_holder = {}
        done = threading.Event()

        def failing_task():
            raise ValueError("boom")

        def on_error(exc):
            error_holder["exc"] = exc
            done.set()

        started = run_async(failing_task, on_error=on_error)
        assert started is True
        done.wait(timeout=5)
        assert "exc" in error_holder
        assert isinstance(error_holder["exc"], ValueError)
        assert str(error_holder["exc"]) == "boom"

    def test_run_async_releases_lock_on_exception(self):
        from services.executor import run_async

        lock = threading.Lock()
        done = threading.Event()

        def failing_task():
            done.set()
            raise RuntimeError("oops")

        run_async(failing_task, lock=lock)
        done.wait(timeout=5)
        time.sleep(0.1)
        assert lock.acquire(blocking=False), "Lock should be released even after exception"
        lock.release()

    def test_run_async_returns_false_after_shutdown(self):
        import services.executor as mod
        mod.shutdown()

        started = mod.run_async(lambda: None)
        assert started is False


# ---------------------------------------------------------------------------
# shutdown()
# ---------------------------------------------------------------------------

class TestShutdown:

    def test_shutdown_prevents_new_submissions(self):
        import services.executor as mod
        mod.shutdown()

        result = mod.submit(lambda: 1)
        assert result is None

    def test_shutdown_is_idempotent(self):
        import services.executor as mod
        mod.shutdown()
        mod.shutdown()  # Should not raise
        assert mod._is_shutdown is True

    def test_shutdown_releases_lock_of_pending_run_async(self):
        import services.executor as mod

        lock = threading.Lock()
        mod.shutdown()

        started = mod.run_async(lambda: None, lock=lock)
        assert started is False
        # Lock should not remain held
        assert lock.acquire(blocking=False)
        lock.release()
