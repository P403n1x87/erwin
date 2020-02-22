from copy import deepcopy
from datetime import datetime
import hashlib
import os
from queue import Queue
from time import time

from shutil import copy, copyfileobj, move

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.inotify_buffer import InotifyBuffer


# Monkey-patch watchdog to reduce enqueuing delay
InotifyBuffer.delay = 0


from erwin.flow import atomic
from erwin.fs import Delta, File, FileSystem, State
from erwin.logging import LOGGER


def _md5(path):
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


class LocalFile(File):
    @property
    def id(self):
        return self.md5, self.modified_date


class LocalFSState(State):
    pass


class LocalFSEventHandler(FileSystemEventHandler):
    def __init__(self, fs):
        super().__init__()

        self._fs = fs
        self._state = fs.state

    @atomic()
    def on_any_event(self, event):
        pass

    def on_created(self, event):
        abs_path = event.src_path

        file = self._fs._to_file(abs_path)
        path = self._fs._rel_path(abs_path)

        self._state.add(file, path)

        self._fs._queue.put(Delta(added=[(file, path)]))

    def on_modified(self, event):
        if event.is_directory:
            return
        self.on_created(event)

    def on_deleted(self, event):
        path = self._fs._rel_path(event.src_path)
        self._state.remove(path)
        self._fs._queue.put(Delta(removed=[path]))

    def on_moved(self, event):
        src = self._fs._rel_path(event.src_path)
        dst = self._fs._rel_path(event.dest_path)
        self._state.move(src, dst)

        self._fs._queue.put(Delta(moved=[(src, dst)]))


class LocalFS(FileSystem):
    def __init__(self, root):
        abs_root = os.path.abspath(root)
        os.makedirs(abs_root, exist_ok=True)
        super().__init__(abs_root)

        self._state = {}
        self._watchdog = Observer()
        self._watchdog.schedule(LocalFSEventHandler(self), abs_root, recursive=True)
        self._queue = Queue()

    def _abs_path(self, path):
        return os.path.abspath(os.path.join(self._root, path))

    def _rel_path(self, path):
        return os.path.relpath(path, start=self.root)

    def _to_file(self, abs_path):
        is_folder = os.path.isdir(abs_path)
        rel_path = self._rel_path(abs_path)
        return LocalFile(
            md5=_md5(abs_path) if not is_folder else rel_path,
            is_folder=is_folder,
            modified_date=datetime.fromtimestamp(round(os.path.getmtime(abs_path), 3))
            if not is_folder
            else None,
        )

    @property
    def state(self):
        if self._state:
            return self._state

        self._state = LocalFSState.from_file_list(self._list())
        self._watchdog.start()

        return self._state

    def get_changes(self):
        while True:
            yield self._queue.get()

    @atomic()
    def makedirs(self, path):
        os.makedirs(self._abs_path(path), exist_ok=True)

    def read(self, path):
        return open(self._abs_path(path), "rb")

    def search(self, path):
        return self.state[path]

    def _list(self):
        return [
            (self._rel_path(os.path.join(dp, f)), self._to_file(os.path.join(dp, f)))
            for dp, dn, filenames in os.walk(self.root)
            for f in dn + filenames
        ]

    def list(self):
        return iter(self.state)

    @atomic()
    def remove(self, path):
        abs_path = self._abs_path(path)
        try:
            os.remove(abs_path)
        except IsADirectoryError:
            os.rmdir(abs_path)
        except FileNotFoundError:
            pass

    @atomic()
    def move(self, src: str, dst: str):
        try:
            move(self._abs_path(src), self._abs_path(dst))
        except FileNotFoundError:
            pass

    @atomic()
    def write(self, stream, path, modified_date):
        abs_path = self._abs_path(path)

        with open(abs_path, "wb") as fout:
            copyfileobj(stream, fout)
            stream.close()

        mtime = datetime.timestamp(modified_date)
        os.utime(abs_path, (mtime, mtime))

    def conflict(self, path: str) -> str:
        head, tail = os.path.split(path)
        return os.path.join(
            head, f"conflict_{hex(int(time())).replace('0x', '')}_{tail}"
        )

    @atomic()
    def copy(self, src: str, dst: str):
        try:
            copy(self._abs_path(src), self._abs_path(dst))
        except FileNotFoundError:
            pass

    def __del__(self):
        self._watchdog.stop()
        self._watchdog.join()

        super().__del__()
