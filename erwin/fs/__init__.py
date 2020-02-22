from abc import ABC, abstractmethod
from collections import defaultdict
from copy import deepcopy
import pickle
from time import sleep


class File(ABC):
    def __init__(self, md5, is_folder, modified_date):
        self.md5 = md5
        self.is_folder = is_folder
        self.modified_date = modified_date

    @property
    @abstractmethod
    def id(self):
        pass

    def __eq__(self, other):
        if not other:
            return False
        return self.id == other.id

    def __and__(self, other):
        if not other:
            return False

        for a in [a for a in self.__dict__ if a in other.__dict__]:
            if self.__dict__[a] != other.__dict__[a]:
                return False

        return True

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"{type(self).__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items())})"


class Delta:
    def __init__(self, added: list = None, moved: list = None, removed: list = None):
        self.added = added or []
        self.moved = moved or []
        self.removed = removed or []

    def __and__(self, other) -> tuple:
        self_new = {p for _, p in self.added} | {p for _, p in self.moved}
        self_rem = {p for p in self.removed} | {p for p, _ in self.moved}

        other_new = {p for _, p in other.added} | {p for _, p in other.moved}
        other_rem = set(other.removed) | {p for p, _ in other.moved}

        return (self_new & (other_new | other_rem), other_new & (self_new | self_rem))

    def __bool__(self):
        return bool(self.added or self.moved or self.removed)

    def __str__(self):
        added = "\n".join([f"+ {f} (at {p})" for f, p in self.added])
        moved = "\n".join([f"M {s} -> {d}" for s, d in self.moved])
        removed = "\n".join([f"- {p}" for p in self.removed])

        return "\n".join([l for l in [added, moved, removed] if l])

    def apply(self, source, dest):
        source_fs, source_state = source
        dest_fs, dest_state = dest

        for path in self.removed:
            dest_fs.remove(path)

            dest_state.remove(path)
            source_state.remove(path)

        for file, path in self.added:
            dest_file = dest_fs.search(path)

            if not (file & dest_file):
                if file.is_folder:
                    dest_fs.makedirs(path)
                else:
                    dest_fs.write(source_fs.read(path), path, file.modified_date)
                while not (file & dest_file):
                    sleep(0.001)
                    dest_file = dest_fs.search(path)

            dest_state.add(dest_file, path)
            source_state.add(file, path)

        for src, dst in self.moved:
            # src file has been moved/removed
            source_src_file = source_state[src]
            if not source_src_file:
                raise RuntimeError(
                    "Source file is unexpectedly missing from previous source FS state."
                )
            source_dst_file = source_fs.search(dst)
            if not source_src_file:
                raise RuntimeError(
                    "Destination file is unexpectedly missing from source FS."
                )

            dest_src_file = dest_fs.search(src)
            dest_dst_file = dest_fs.search(dst)

            if dest_src_file:
                if source_src_file & dest_src_file:
                    dest_fs.move(src, dst)
                    dest_state.move_file(src, dst)
                else:
                    dest_fs.remove(src)

            if not (source_dst_file & dest_dst_file):
                if source_dst_file.is_folder:
                    dest_fs.makedirs(dst)
                else:
                    dest_fs.write(
                        source_fs.read(dst), dst, source_dst_file.modified_date
                    )
                while not (source_dst_file & dest_dst_file):
                    sleep(0.001)
                    dest_dst_file = dest_fs.search(path)

            dest_state.add(dest_dst_file, dst)
            dest_state.remove(src)

            source_state.move(src, dst)


class State(ABC):
    def __init__(self):
        self._data = {"by_id": defaultdict(dict), "by_path": {}}

    def __getitem__(self, path):
        return self._data["by_path"].get(path, None)

    def __setitem__(self, path, file):
        self.add(file, path)

    def __iter__(self):
        return iter(self._data["by_path"].items())

    def _del_by_id(self, file, path):
        bucket = self._data["by_id"][file.id]
        del bucket[path]
        if not bucket:
            del self._data["by_id"][file.id]

    @classmethod
    def from_file_list(cls, files):
        state = cls()
        for path, file in files:
            state.add(file, path)
        return state

    @classmethod
    def load(cls, statefile):
        try:
            with open(statefile, "rb") as fo:
                return pickle.load(fo)
        except FileNotFoundError:
            return cls()

    def save(self, statefile):
        with open(statefile, "wb") as fo:
            pickle.dump(self, fo)

    def add(self, file, path):
        self.remove(path)  # Remove any existing file at path
        self._data["by_id"][file.id][path] = self._data["by_path"][path] = file

    def remove(self, path):
        try:
            self._del_by_id(self._data["by_path"].pop(path), path)
        except KeyError:
            pass

    def move(self, src, dst):
        try:
            self.add(self._data["by_path"][src], dst)
            self.remove(src)
        except KeyError:
            pass

    def __sub__(self, prev):
        curr_state, prev_state = self._data, prev._data

        curr_ids = curr_state["by_id"]
        prev_ids = prev_state["by_id"]

        added = {
            (f, p)
            for _id, l in curr_ids.items()
            for p, f in l.items()
            if not prev_ids[_id]
        }
        removed = {
            p for _id, l in prev_ids.items() for p, _ in l.items() if not curr_ids[_id]
        }
        moved = []

        for _id in {i for i in prev_ids if i in curr_ids}:
            curr_files = curr_ids[_id]
            prev_files = prev_ids[_id]

            new_files = [(f, p) for p, f in curr_files.items() if p not in prev_files]
            deleted_files = [p for p, _ in prev_files.items() if p not in curr_files]

            while new_files and deleted_files:
                moved.append((deleted_files.pop(), new_files.pop()[1]))

            added |= set(new_files)
            removed |= set(deleted_files)

        return Delta(
            added=sorted(added, key=lambda x: x[1]),
            moved=moved,
            removed=sorted(removed, reverse=True),
        )


class FileSystem(ABC):
    def __init__(self, root: File):
        self._root = root

    @property
    def root(self):
        return self._root

    @abstractmethod
    def get_changes(self):
        pass

    @property
    @abstractmethod
    def state(self):
        pass

    @abstractmethod
    def list(self) -> list:
        pass

    @abstractmethod
    def search(self, path: str) -> File:
        pass

    @abstractmethod
    def copy(self, src: str, dst: str):
        pass

    @abstractmethod
    def read(self, path: str):
        pass

    @abstractmethod
    def write(self, stream, path: str, modified_date):
        pass

    @abstractmethod
    def move(self, src: str, dst: str):
        pass

    @abstractmethod
    def remove(self, file: File):
        pass

    @abstractmethod
    def makedirs(self, path: str):
        pass

    @abstractmethod
    def conflict(self, file: File):
        pass
