from threading import RLock


GLOBAL_LOCK = RLock()


def atomic(lock=GLOBAL_LOCK):
    def atomic_wrapper(f):
        def func_wrapper(*args, **kwargs):
            with lock:
                f(*args, **kwargs)

        return func_wrapper

    return atomic_wrapper
