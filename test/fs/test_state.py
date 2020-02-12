from erwin.fs import State

from test.fs import TestDir, TestFile


def test_state():
    s, t = State(), State()

    a1 = TestFile("a", 1)
    b2 = TestFile("b", 2)
    c3 = TestFile("c", 3)

    b1 = TestFile("b", 1)
    d4 = TestFile("d", 4)
    z99 = TestFile("z", 99)

    s.add_file(a1)
    s.add_file(b2)
    s.add_file(c3)

    t.add_file(b1)
    t.add_file(d4)
    t.add_file(z99)

    delta = s - t

    assert set(delta.new) == {b2, c3}
    assert set(delta.renamed) == {(b1, a1)}
    assert set(delta.removed) == {d4, z99}
