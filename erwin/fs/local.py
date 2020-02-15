from copy import deepcopy
from datetime import datetime
import hashlib
import os
from time import time

from shutil import copy, copyfileobj, move

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.inotify_buffer import InotifyBuffer


# Monkey-patch watchdog to reduce enqueuing delay
InotifyBuffer.delay = 0


from erwin.flow import GLOBAL_LOCK
from erwin.fs import Delta, File, FileSystem, State
from erwin.logging import LOGGER


def _md5(path):
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


class LocalFile(File):
    # def __init__(self, path, md5, is_folder, modified_date, created_date):
    #     super().__init__(path, md5, is_folder, modified_date)
    #     self.created_date = created_date

    @property
    def id(self):
        return self.path if self.is_folder else (self.md5, self.modified_date)


class LocalFSState(State):
    pass


class LocalFSEventHandler(FileSystemEventHandler):
    def __init__(self, fs, cb):
        super().__init__()

        self._fs = fs
        self._cb = cb
        self._state = fs.get_state()

    def _get_file(self, abs_path):
        return self._fs.search(self._fs._rel_path(abs_path))

    def on_any_event(self, event):
        with GLOBAL_LOCK:
            pass

    def on_created(self, event):
        file = self._fs._to_file(event.src_path)
        LOGGER.debug(f"Created {file}")
        self._state.add_file(file)

        self._cb(event)

    def on_modified(self, event):
        if event.is_directory:
            return
        self.on_created(event)

    def on_deleted(self, event):
        self._state.remove_file(self._get_file(event.src_path))
        self._cb(event)

    def on_moved(self, event):
        self._state.move_file(
            file=self._fs.search(self._get_file(event.src_path)),
            dst=self._fs._rel_path(event.dest_path),
        )
        self._cb(event)


class LocalFS(FileSystem):
    def __init__(self, root, change_callback):
        # TODO: Validate root!
        abs_root = os.path.abspath(root)
        super().__init__(abs_root, change_callback)

        self._state = {}
        self._watchdog = Observer()
        self._watchdog.schedule(
            LocalFSEventHandler(self, change_callback), abs_root, recursive=True
        )

    def _abs_path(self, path):
        return os.path.abspath(os.path.join(self._root, path))

    def _rel_path(self, path):
        return os.path.relpath(path, start=self.root)

    def _to_file(self, path):
        is_folder = os.path.isdir(path)
        rel_path = self._rel_path(path)
        return LocalFile(
            path=rel_path,
            md5=_md5(path) if not is_folder else rel_path,
            is_folder=is_folder,
            # created_date=datetime.fromtimestamp(os.path.getctime(path)),
            modified_date=datetime.fromtimestamp(os.path.getmtime(path)),
        )

    def get_state(self):
        if self._state:
            return self._state

        self._state = LocalFSState.from_file_list(self._list())
        self._watchdog.start()

        return self._state

    def makedirs(self, file):
        abs_path = self._abs_path(file.path)

        with GLOBAL_LOCK:
            os.makedirs(abs_path, exist_ok=True)

            mtime = datetime.timestamp(file.modified_date)
            os.utime(abs_path, (mtime, mtime))

        return self._to_file(abs_path)

    def read(self, file):
        return open(self._abs_path(file.path), "rb")

    def search(self, path):
        return self.get_state()[path]

    def _list(self):
        return [
            self._to_file(os.path.join(dp, f))
            for dp, dn, filenames in os.walk(self.root)
            for f in dn + filenames
        ]

    def list(self, recursive=False):
        return [f for _, f in self.get_state().get()["by_path"].items()]

    def remove(self, file):
        abs_path = self._abs_path(file.path)

        with GLOBAL_LOCK:
            os.remove(abs_path) if not file.is_folder else os.rmdir(abs_path)

    def move(self, src: LocalFile, dst: str):
        abs_dst = self._abs_path(dst)
        with GLOBAL_LOCK:
            move(self._abs_path(src.path), abs_dst)

        # src.created_date = datetime.fromtimestamp(os.path.getctime(abs_dst))

    def write(self, stream, file):
        abs_path = self._abs_path(file.path)

        with GLOBAL_LOCK:
            with open(abs_path, "wb") as fout:
                copyfileobj(stream, fout)
                stream.close()

            mtime = datetime.timestamp(file.modified_date)
            os.utime(abs_path, (mtime, mtime))

        return self._to_file(abs_path)

    def conflict(self, file: LocalFile) -> str:
        head, tail = os.path.split(file.path)
        return os.path.join(
            head, f"conflict_{hex(int(time())).replace('0x', '')}_{tail}"
        )

    def copy(self, file: LocalFile, dst: str):
        abs_dst = self._abs_path(dst)
        copy(self._abs_path(file.path), abs_dst)

        dst_file = deepcopy(file)
        dst_file.path = dst
        dst_file.created_time = datetime.fromtimestamp(os.path.getctime(abs_dst))
        dst_file.modified_date = datetime.fromtimestamp(os.path.getmtime(abs_dst))

    def __del__(self):
        self._watchdog.stop()
        self._watchdog.join()

        super().__del__()
