from abc import ABC, abstractmethod
import pickle


class File:
    def __init__(self, path, md5, is_folder, created_date, modified_date):
        self.path = path
        self.md5 = md5
        self.is_folder = is_folder
        # self.created_date = created_date
        self.modified_date = modified_date

    def __eq__(self, other):
        common_attributes = [a for a in self.__dict__ if a in other.__dict__]
        return {a: self.__dict__[a] for a in common_attributes} == {
            a: other.__dict__[a] for a in common_attributes
        }

    def __matmul__(self, other):
        if not other:
            return False
        return self.md5 == other.md5 and (
            self.is_folder == other.is_folder
            or self.modified_date == other.modified_date
        )


class Delta:
    def __init__(self, new: list, renamed: list, removed: list):
        self._new = new
        self._renamed = renamed
        self._removed = removed

    @property
    def new(self):
        return sorted(self._new, key=lambda file: file.path)

    @property
    def renamed(self):
        return sorted(self._renamed, key=lambda x: x[0].path)

    @property
    def removed(self):
        return sorted(
            self._removed, key=lambda file: file.path, reverse=True
        )

    def conflicts(self, other) -> tuple:
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
        new = "\n".join([f"+ {f.modified_date} {f.path}" for f in self.new])
        removed = "\n".join([f"- {f.modified_date} {f.path}" for f in self.removed])
        renamed = "\n".join([f"M {s.path} -> {d.path}" for s, d in self.renamed])

        return "\n".join([l for l in [new, removed, renamed] if l])


class State(ABC):
    def __init__(self):
        self._data = self.empty()

    @abstractmethod
    def empty(self):
        pass

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

    @abstractmethod
    def add_file(self, file):
        pass

    @abstractmethod
    def remove_file(self, file):
        pass

    @abstractmethod
    def rename_file(self, file, dst):
        pass

    @abstractmethod
    def __sub__(self, other):
        pass


class FileSystem(ABC):
    def __init__(self, root: File):
        self._root = root

    @property
    def root(self):
        return self._root

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
    def makedirs(self, file: File):
        pass

    @abstractmethod
    def remove(self, file: File):
        pass

    @abstractmethod
    def move(self, file: File, dst: str):
        pass

    @abstractmethod
    def copy(self, file: File, dst: str):
        pass
