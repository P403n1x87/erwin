from copy import deepcopy
from datetime import datetime
import os
import hashlib
import os.path

from shutil import copy, copyfileobj, move

from erwin.fs import Delta, File, FileSystem, State


def _md5(path):
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


class LocalFile(File):
    def __init__(self, path, md5, is_folder, modified_date, created_date):
        super().__init__(path, md5, is_folder, modified_date)
        self.created_date = created_date

    @property
    def id(self):
        return self.path if self.is_folder else (self.md5, self.modified_date)


class LocalFSState(State):
    pass


class LocalFS(FileSystem):
    def __init__(self, root):
        # TODO: Validate root!
        super().__init__(os.path.abspath(root))
        self._state = {}

    def _abs_path(self, path):
        return os.path.abspath(os.path.join(self._root, path))

    def _to_file(self, path):
        is_folder = os.path.isdir(path)
        rel_path = os.path.relpath(path, start=self.root)
        return LocalFile(
            path=rel_path,
            md5=_md5(path) if not is_folder else rel_path,
            is_folder=is_folder,
            created_date=datetime.fromtimestamp(os.path.getctime(path)),
            modified_date=datetime.fromtimestamp(os.path.getmtime(path)),
        )

    def get_state(self):
        self._state = self._state or LocalFSState.from_file_list(self._list())
        return self._state

    def makedirs(self, file):
        abs_path = self._abs_path(file.path)
        os.makedirs(abs_path, exist_ok=True)

        mtime = datetime.timestamp(file.modified_date)
        os.utime(abs_path, (mtime, mtime))

        self.get_state().add_file(file)

    def read(self, file):
        return open(self._abs_path(file.path), "rb")

    def search(self, path):
        return self.get_state().get()["by_path"].get(path, None)

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

        os.remove(abs_path) if not file.is_folder else os.rmdir(abs_path)

        self.get_state().remove_file(file)

    def move(self, src: LocalFile, dst: str):
        abs_dst = self._abs_path(dst)
        move(self._abs_path(src.path), abs_dst)

        src.created_date = datetime.fromtimestamp(os.path.getctime(abs_dst))
        self.get_state().move_file(src, dst)

    def write(self, stream, file):
        abs_path = self._abs_path(file.path)

        with open(abs_path, "wb") as fout:
            copyfileobj(stream, fout)
            stream.close()

        mtime = datetime.timestamp(file.modified_date)
        os.utime(abs_path, (mtime, mtime))

        file = self._to_file(abs_path)

        self.get_state().add_file(file)

    def copy(self, file: LocalFile, dst: str):
        abs_dst = self._abs_path(dst)
        copy(self._abs_path(file.path), abs_dst)

        dst_file = deepcopy(file)
        dst_file.path = dst
        dst_file.created_time = datetime.fromtimestamp(os.path.getctime(abs_dst))
        dst_file.modified_date = datetime.fromtimestamp(os.path.getmtime(abs_dst))

        self.get_state().add_file(dst_file)
