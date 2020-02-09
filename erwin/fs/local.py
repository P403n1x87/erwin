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
    def __hash__(self):
        return hash(self.path + str(self.md5))


class LocalFSState(State):
    @classmethod
    def from_file_list(cls, files):
        state = cls()
        state.set(
            {
                "by_path": {f.path: f for f in files},
                "by_hash": {f.md5: f for f in files},
            }
        )
        return state

    def empty(self):
        return {"by_path": {}, "by_hash": {}}

    def add_file(self, file):
        state = self.get()
        state["by_path"][file.path] = file
        state["by_hash"][file.md5] = file

    def remove_file(self, file):
        state = self.get()
        try:
            state["by_path"].pop(file.path)
            state["by_hash"].pop(file.md5)
        except KeyError:
            pass

    def rename_file(self, file: LocalFile, dst: str):
        state = self.get()
        try:
            new_file = deepcopy(state["by_path"].pop(file.path))
            new_file.path = dst
            state["by_path"][dst] = new_file
        except KeyError:
            pass

    def __sub__(self, prev):
        curr_state, prev_state = self.get(), prev.get()

        curr_hashes = curr_state.get("by_hash", {})
        prev_hashes = prev_state.get("by_hash", {})

        new = {
            f for _id, f in curr_hashes.items() if not f @ prev_hashes.get(_id, None)
        }
        deleted = {
            f for _id, f in prev_hashes.items() if not f @ curr_hashes.get(_id, None)
        }
        renamed = set()

        for _id in {
            _id for _id, f in prev_hashes.items() if f @ curr_hashes.get(_id, None)
        }:
            curr_file = curr_state["by_hash"][_id]
            prev_file = prev_state["by_hash"][_id]

            if curr_file.is_folder != prev_file.is_folder:
                deleted.add(prev_file)
                new.add(curr_file)

            elif not curr_file.is_folder and not prev_file.is_folder:
                if (
                    curr_file.modified_date == prev_file.modified_date
                    and curr_file.path != prev_file.path
                ):
                    # Probably the file has been moved
                    renamed.add((prev_file, curr_file))
                elif (
                    curr_file.path == prev_file.path
                    and curr_file.modified_date != prev_file.modified_date
                    and not curr_file.is_folder
                    and not prev_file.is_folder
                ):
                    # File has been modified
                    new.add(curr_file)
                elif curr_file != prev_file:
                    # Possibly a hash collision
                    new.add(curr_file)
                    deleted.add(prev_file)

        return Delta(new=new, renamed=renamed, removed=deleted)


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
        self.get_state().rename_file(src, dst)

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
        dst_file.creation_time = datetime.fromtimestamp(os.path.getctime(abs_dst))
        dst_file.modified_date = datetime.fromtimestamp(os.path.getmtime(abs_dst))

        self.get_state().add_file(dst_file)
