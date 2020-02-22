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
