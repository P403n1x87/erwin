from abc import ABC, abstractmethod
from copy import deepcopy
import pickle


class File(ABC):
    def __init__(self, path, md5, is_folder, modified_date):
        self.path = path
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
    def __init__(self, new: list = None, renamed: list = None, removed: list = None):
        self._new = new or []
        self._renamed = renamed or []
        self._removed = removed or []

    @property
    def new(self):
        return sorted(self._new, key=lambda file: file.path)

    @property
    def renamed(self):
        return sorted(self._renamed, key=lambda x: x[0].path)

    @property
    def removed(self):
        return sorted(self._removed, key=lambda file: file.path, reverse=True)

    def conflicts(self, other) -> tuple:
        # TODO: This is not checking for file content mismatch so it is
        # calculating path conflicts only. Enhance to return only those paths
        # where files actually differ
        self_new = {f.path for f in self.new} | {f.path for _, f in self.renamed}
        self_rem = {f.path for f in self.removed} | {f.path for f, _ in self.renamed}

        other_new = {f.path for f in other.new} | {f.path for _, f in other.renamed}

        other_rem = {f.path for f in other.removed} | {f.path for f, _ in other.renamed}

        return (
            self_new & (other_new | other_rem),
            other_new & (self_new | self_rem),
        )

    def __bool__(self):
        return bool(self._new or self._renamed or self._removed)

    def __str__(self):
        new = "\n".join([f"+ {f}" for f in self.new])
        removed = "\n".join([f"- {f}" for f in self.removed])
        renamed = "\n".join([f"M {s} -> {d}" for s, d in self.renamed])

        return "\n".join([l for l in [new, removed, renamed] if l])


class State(ABC):
    def __init__(self):
        self._data = {"by_id": {}, "by_path": {}}

    def __getitem__(self, path):
        return self._data["by_path"].get(path, None)

    def __setitem__(self, path, file):
        new_file = deepcopy(file)
        new_file.path = path
        self._data["by_id"][new_file.id] = self._data["by_path"][path] = new_file

    @classmethod
    def from_file_list(cls, files):
        state = cls()
        for file in files:
            state.add_file(file)
        return state

    def set(self, state: dict):
        self._data = state

    def get(self):
        return self._data

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

    def add_file(self, file):
        # Check if we have the same file at a different path
        prev_file = self._data["by_id"].get(file.id, None)
        if prev_file and file.path != prev_file.path:
            # Move it
            self._data["by_path"][file.path] = file
            return

        # Check whether we have different files at the same path
        prev_file = self._data["by_path"].get(file.path, None)
        if prev_file and file.id != prev_file.id:
            # Remove old file and add the new one
            del self._data["by_id"][prev_file.id]

        self._data["by_id"][file.id] = self._data["by_path"][file.path] = file

    def remove_file(self, file):
        if not file:
            return

        try:
            del self._data["by_id"][file.id]
            del self._data["by_path"][file.path]
        except KeyError:
            pass

    def move_file(self, file, dst):
        try:
            new_file = deepcopy(self._data["by_path"].pop(file.path))
            del self._data["by_id"][file.id]
        except KeyError:
            new_file = deepcopy(file)

        new_file.path = dst

        self._data["by_id"][new_file.id] = self._data["by_path"][
            new_file.path
        ] = new_file

    def __sub__(self, prev):
        curr_state, prev_state = self.get(), prev.get()

        curr_ids = curr_state.get("by_id", {})
        prev_ids = prev_state.get("by_id", {})

        new = {f for _id, f in curr_ids.items() if not f == prev_ids.get(_id, None)}
        deleted = {f for _id, f in prev_ids.items() if not f == curr_ids.get(_id, None)}
        renamed = set()

        for _id in {i for i, f in prev_ids.items() if f == curr_ids.get(i, None)}:
            curr_file = curr_state["by_id"][_id]
            prev_file = prev_state["by_id"][_id]

            if curr_file == prev_file:
                if curr_file.path != prev_file.path:
                    renamed.add((prev_file, curr_file))
            else:
                if curr_file.path == prev_file.path:
                    new.add(curr_file)
                else:
                    deleted.add(prev_file)
                    new.add(curr_file)

        return Delta(new=new, renamed=renamed, removed=deleted)


class FileSystem(ABC):
    def __init__(self, root: File):
        self._root = root

    @property
    def root(self):
        return self._root

    @abstractmethod
    def get_changes(self):
        pass

    @abstractmethod
    def get_state(self):
        pass

    @abstractmethod
    def read(self, file: File):
        pass

    @abstractmethod
    def write(self, stream, file: File):
        pass

    @abstractmethod
    def list(self, recursive: bool = False) -> list:
        pass

    @abstractmethod
    def search(self, path: str) -> File:
        pass

    @abstractmethod
    def makedirs(self, path: str):
        pass

    @abstractmethod
    def remove(self, file: File):
        pass

    @abstractmethod
    def move(self, file: File, dst: str):
        pass

    @abstractmethod
    def conflict(self, file: File):
        pass

    @abstractmethod
    def copy(self, file: File, dst: str):
        pass
