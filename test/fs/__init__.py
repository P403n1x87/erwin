from copy import deepcopy
from erwin.fs import Delta, File, FileSystem, State


class MockFile(File):
    def __init__(self, md5):
        super().__init__(md5, is_folder=False, modified_date=None)

    @property
    def id(self):
        return self.md5, self.modified_date


class MockDir(File):
    def __init__(self, md5):
        super().__init__(md5, is_folder=True, modified_date=None)

    @property
    def id(self):
        return self.md5


class MockFileSystem(FileSystem):
    def __init__(self, root):
        super().__init__(root)

        self._state = TestState()

    @property
    def state(self):
        return self._state

    def read(self, path):
        return self.state[path]

    def write(self, stream, path, modified_date):
        self.state[path] = stream

    def list(self):
        return self.state

    def search(self, path):
        return self.state[path]

    def makedirs(self, path):
        self.state[path] = MockDir(path)

    def remove(self, path):
        self.state.remove(path)
