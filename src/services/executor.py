# services/executor.py

# handles threading and async execution for various tasks, like player updates, balancer runs, etc.

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional


_executor = ThreadPoolExecutor(max_workers=2)

def submit(fn, *args, **kwargs):
    return _executor.submit(fn, *args, **kwargs)


def run_async(task, lock: Optional[Lock] = None, on_error=None):

    if lock and not lock.acquire(blocking=False):
        return False

    def wrapper():
        try:
            task()
        except Exception as e:
            import services.logger as logger
            logger.log_error(f"[EXECUTOR] Task failed: {e}", exc=e)

            if on_error:
                on_error(e)
        finally:
            if lock:
                lock.release()

    _executor.submit(wrapper)
    return True

def shutdown():
    _executor.shutdown(wait=False)