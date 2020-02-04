from copy import deepcopy
from erwin.fs import Delta, File, FileSystem, State


class TestFile(File):
    def __init__(self, path, md5):
        super().__init__(
            path, md5, is_folder=False, created_date=None, modified_date=None
        )


class TestDir(File):
    def __init__(self, path, md5):
        super().__init__(
            path, md5, is_folder=True, created_date=None, modified_date=None
        )


class TestState(State):
    def empty(self):
        return {}

    def add_file(self, file):
        self.get()[file.path] = file

    def remove_file(self, file):
        del self.get()[file.path]

    def rename_file(self, src, dst):
        data = self.get()
        new_file = deepcopy(data.pop(src.path))
        new_file.path = dst
        self.add_file(new_file)

    def __sub__(self, other):
        new = [f for p, f in self.get().items() if p not in other.get()]
        removed = [f for p, f in other.get().items() if p not in self.get()]

        self_by_md5 = {file.md5: file for _, file in self.get().items()}
        other_by_md5 = {file.md5: file for _, file in other.get().items()}

        common_md5 = {md5 for md5 in self_by_md5 if md5 in other_by_md5}
        renamed = [
            (self_by_md5[md5], other_by_md5[md5])
            for md5 in common_md5
            if self_by_md5[md5].path != other_by_md5[md5].path
        ]

        return Delta(new, renamed, removed)


class TestFileSystem(FileSystem):
    def __init__(self, root):
        super().__init__(root)

        self._state = TestState()

    def get_state(self):
        return self._state

    def read(self, file):
        return file.path

    def write(self, stream, file):
        self.get_state().add_file(file)

    def list(self, recursive=False):
        return self.get_state().list()

    def search(self, path):
        return self.get_state().get_by_path(path)

    def makedirs(self, file):
        self.get_state().add_file(file)

    def remove(self, file):
        self.get_state().remove_file(file)
