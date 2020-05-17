# This file is part of "erwin" which is released under GPL.
#
# See file LICENCE or go to http://www.gnu.org/licenses/ for full license
# details.
#
# Erwin is a cloud storage synchronisation service.
#
# Copyright (c) 2020 Gabriele N. Tornetta <phoenix1987@gmail.com>.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

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
