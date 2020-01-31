from queue import Queue

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class ErwinEventHandler(PatternMatchingEventHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._queue = Queue()

    def get_event(self):
        return self._queue.get()
