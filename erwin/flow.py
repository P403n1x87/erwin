from threading import RLock
from time import sleep

from erwin.fs import FSNotReady
from erwin.logging import LOGGER


GLOBAL_LOCK = RLock()


def atomic(lock=GLOBAL_LOCK):
    def atomic_wrapper(f):
        def func_wrapper(*args, **kwargs):
            with lock:
                return f(*args, **kwargs)

        return func_wrapper

    return atomic_wrapper


def backoff(delay=5, ratio=1.618, cap=60):
    def wrapper(f):
        def func_wrapper(*args, **kwargs):
            backoff = delay
            while True:
                try:
                    error = False
                    return f(*args, **kwargs)
                except FSNotReady as e:
                    LOGGER.error(f"A file system is not ready yet: {e}")
                    LOGGER.info(
                        f"A new start attempt will be made in {int(backoff)} seconds"
                    )
                    sleep(backoff)
                    backoff = min(cap, backoff * ratio)
                    error = True
                finally:
                    if not error:
                        backoff = delay

        return func_wrapper

    return wrapper
