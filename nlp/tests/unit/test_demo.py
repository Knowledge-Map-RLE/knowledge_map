def add(a, b):
    return a + b


def test_add_positive_numbers():
    assert add(2, 3) == 5


def test_add_negative_numbers():
    assert add(-1, -4) == -5


def test_add_zero():
    assert add(10, 0) == 10
