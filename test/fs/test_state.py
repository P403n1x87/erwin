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

from erwin.fs import State

from test.fs import MockDir, MockFile


def test_state():
    s, t = State(), State()

    a1 = MockFile(1)
    b2 = MockFile(2)
    c3 = MockFile(3)

    b1 = MockFile(1)
    d4 = MockFile(4)
    z99 = MockFile(99)

    s.add(a1, "a")
    s.add(b2, "b")
    s.add(c3, "c")

    t.add(b1, "b")
    t.add(d4, "d")
    t.add(z99, "z")

    delta = s - t

    assert set(delta.added) == {(b2, "b"), (c3, "c")}
    assert set(delta.moved) == {("b", "a")}
    assert set(delta.removed) == {"d", "z"}
