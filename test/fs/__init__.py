from copy import deepcopy
from erwin.fs import Delta, File, FileSystem, State


class TestFile(File):
    def __init__(self, path, md5):
        super().__init__(path, md5, is_folder=False, modified_date=None)

    @property
    def id(self):
        return (self.md5, self.modified_date)

    def __repr__(self):
        return f"TestFile({self.path}, {self.md5})"

class TestDir(File):
    def __init__(self, path, md5):
        super().__init__(path, md5, is_folder=True, modified_date=None)

    @property
    def id(self):
        return self.path


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
        return self.get_state()[path]

    def makedirs(self, file):
        self.get_state().add_file(file)

    def remove(self, file):
        self.get_state().remove_file(file)
