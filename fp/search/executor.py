"""Keep native-search workers warm between decisions and games."""

import atexit
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from threading import Lock

_lock = Lock()
_executor = None
_worker_count = None


def get_search_executor(workers: int) -> ProcessPoolExecutor:
    global _executor, _worker_count
    if workers < 1:
        raise ValueError("Search parallelism must be at least one")
    with _lock:
        if _executor is not None and _worker_count != workers:
            _executor.shutdown(wait=True, cancel_futures=True)
            _executor = None
        if _executor is None:
            # Search is dispatched from an asyncio executor thread. Spawn avoids
            # forking a multithreaded process and also matches macOS behavior.
            _executor = ProcessPoolExecutor(
                max_workers=workers, mp_context=get_context("spawn")
            )
            _worker_count = workers
        return _executor


def shutdown_search_executor():
    global _executor, _worker_count
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=True, cancel_futures=True)
            _executor = None
            _worker_count = None


atexit.register(shutdown_search_executor)
