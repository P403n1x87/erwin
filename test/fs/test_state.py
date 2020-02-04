from test.fs import TestDir, TestFile, TestState


def test_state():
    s, t = TestState(), TestState()

    s.add_file(TestFile("a", 1))
    s.add_file(TestFile("b", 2))
    s.add_file(TestFile("c", 3))

    t.add_file(TestFile("b", 1))
    t.add_file(TestDir("z", 99))

    assert str(s - t) == "+ None a\n+ None c\n- None z\nM a -> b"
